"""Background jobs, run from cron on app VM 1 only (hp-app-01).

    hallpass-worker <job>

Crontab (lives in the infra repo, copied here so people stop asking):

    * * * * *     hallpass-worker dispatch_outbox
    */2 * * * *   hallpass-worker release_holds
    */5 * * * *   hallpass-worker submit_refunds
    */5 * * * *   hallpass-worker sweep_waitlist
    0 * * * *     hallpass-worker schedule_reminders
    10 0 * * *    hallpass-worker expire_waitlist
    15 2 1 * *    hallpass-worker monthly_invoices
    30 3 * * *    hallpass-worker reconcile_paybridge
    0 4 * * 0     hallpass-worker retention_sweep

Cron's clock on the VM is UTC. Jobs that care about local dates (reminders,
invoices, reconciliation) work that out themselves via hallpass.core.clock.
NB the invoice run at 02:15 UTC on the 1st is 03:15 local in summer; both are
after midnight local, which is all that matters.

Each job takes a Postgres advisory lock so an overrunning run doesn't overlap
the next one. If the lock is taken we just exit 0 and log it.

There's no retry loop in here: if a job fails it exits non-zero, cron mails
the ops mailbox, and the next scheduled run picks up where it left off. Jobs
must therefore be safe to re-run. (Mostly true. The SMS one is the exception
we know about, see docs/known-issues/accounts-and-notifications.md.)
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable
from datetime import date

from hallpass.core import clock, db, flags
from hallpass.core.clock import system_clock

log = logging.getLogger("hallpass.worker")

JobFn = Callable[[object], int]


def release_holds(conn) -> int:
    from hallpass.bookings import jobs

    return jobs.release_expired_holds(conn)


def sweep_waitlist(conn) -> int:
    if not flags.is_enabled("waitlist"):
        # Fast path when it's off everywhere. The flag is facility-scoped,
        # so sweep_waitlist still checks per facility.
        return 0
    from hallpass.bookings import jobs

    return jobs.sweep_waitlist(conn)


def expire_waitlist(conn) -> int:
    from hallpass.bookings import jobs

    return jobs.expire_waitlist(conn)


def dispatch_outbox(conn) -> int:
    from hallpass.core.config import get_settings
    from hallpass.notifications.email_sender import SmtpEmailSender
    from hallpass.notifications.senders import NullSender
    from hallpass.notifications.sms_sender import TextHubSmsSender

    settings = get_settings()
    email_sender = SmtpEmailSender() if settings.email_backend == "smtp" else NullSender()
    # Outside production SMS always goes to the NullSender, whatever the flag
    # says. Staging has real-looking mobiles in it.
    sms_sender = TextHubSmsSender() if settings.is_production else NullSender()
    return outbox_dispatch(conn, email_sender, sms_sender)


def outbox_dispatch(conn, email_sender, sms_sender) -> int:
    from hallpass.notifications import outbox

    total = 0
    # Keep going until the backlog is drained or we've used most of the minute.
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        n = outbox.dispatch_outbox(conn, system_clock, email_sender=email_sender, sms_sender=sms_sender, limit=100)
        total += n
        if n < 100:
            break
    return total


def schedule_reminders(conn) -> int:
    from hallpass.notifications import reminders

    return reminders.schedule_reminders(conn, system_clock)


def submit_refunds(conn) -> int:
    from hallpass.billing import refunds

    return refunds.submit_pending_refunds(conn, limit=50)


def monthly_invoices(conn) -> int:
    if not flags.is_enabled("org_invoicing"):
        return 0
    from hallpass.billing import invoices

    today = clock.today_local()
    first_of_this_month = today.replace(day=1)
    last_month = (first_of_this_month.replace(year=today.year - 1, month=12) if today.month == 1
                  else first_of_this_month.replace(month=today.month - 1))
    # run_monthly_invoicing manages its own transactions; conn only holds the lock
    return len(invoices.run_monthly_invoicing(last_month, today))


def reconcile_paybridge(conn, day: date | None = None) -> int:
    from hallpass.billing import reconciliation

    # Yesterday, local. Paybridge settlement files for "today" aren't final
    # until ~02:00 UTC the next day.
    target = day or date.fromordinal(clock.today_local().toordinal() - 1)
    return len(reconciliation.reconcile_day(target))


def retention_sweep(conn) -> int:
    """ADR 0010. Anonymises, never deletes financial rows."""
    from hallpass.accounts import residents, retention

    counts = retention.sweep(conn, system_clock)
    counts["unverified_purged"] = residents.purge_unverified(conn, system_clock)
    log.info("retention sweep: %s", counts)
    return sum(counts.values())


JOBS: dict[str, Callable[..., int]] = {
    "release_holds": release_holds,
    "sweep_waitlist": sweep_waitlist,
    "expire_waitlist": expire_waitlist,
    "dispatch_outbox": dispatch_outbox,
    "schedule_reminders": schedule_reminders,
    "submit_refunds": submit_refunds,
    "monthly_invoices": monthly_invoices,
    "reconcile_paybridge": reconcile_paybridge,
    "retention_sweep": retention_sweep,
}

# Stable lock keys. Never renumber; new jobs get the next free number.
# (7100-7102 were expire_holds / dispatch_outbox / queue_reminders before the
# 3.2 rename. Left unused on purpose so an old crontab can't collide.)
LOCK_KEYS: dict[str, int] = {
    "release_holds": 7103,
    "sweep_waitlist": 7104,
    "expire_waitlist": 7105,
    "dispatch_outbox": 7106,
    "schedule_reminders": 7107,
    "submit_refunds": 7108,
    "monthly_invoices": 7109,
    "reconcile_paybridge": 7110,
    "retention_sweep": 7111,
}


def run(job_name: str) -> int:
    fn = JOBS[job_name]
    started = time.monotonic()
    with db.connection() as conn:
        with db.advisory_lock(conn, LOCK_KEYS[job_name]) as got_lock:
            if not got_lock:
                log.info("job %s already running elsewhere, skipping", job_name)
                return 0
            # Jobs manage their own transactions (most commit per batch);
            # this commit just closes anything left open.
            count = fn(conn)
            conn.commit()
    log.info("job %s done: %s items in %.1fs", job_name, count, time.monotonic() - started)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hallpass-worker")
    parser.add_argument("job", choices=sorted(JOBS))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        run(args.job)
    except Exception:
        log.exception("job %s failed", args.job)
        return 1
    finally:
        db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(main())
