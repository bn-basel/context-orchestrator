---
kind: doc
status: unverified
---

# Runbook: restore from backup

> Last actually rehearsed: 2024-10-15 (Gareth, onto the DR VM). The 2025
> rehearsal was postponed twice. Commands below are from that rehearsal; the
> pgBackRest stanza name may have changed since infra rebuilt the repo host.

Backups are owned by Digital Infrastructure, not us. We do not have
superuser on the DB hosts. A restore is always a joint job: raise a P1/P2
ticket with infra and get the DBA on a call. This page is what *we* need to
know and do around it.

## What exists

- pgBackRest, stanza `hallpass`, repo on the council object store.
- Full backup Sunday 01:30, differential every other night 01:30.
- Continuous WAL archiving, so point-in-time recovery (PITR) to within a few
  minutes is possible.
- Retention: 4 full backups (~1 month) plus WAL for that period.
- Streaming replica hp-db-02. **The replica is not a backup**: a bad `DELETE`
  replicates in milliseconds.

## Decide what you actually need

| Situation | Do this |
|---|---|
| Primary host dead, data fine | Infra promote hp-db-02. No restore. Update `HALLPASS_DATABASE_URL` only if they don't move the DNS name `hallpass-db.internal`. |
| Someone deleted/updated rows by mistake | PITR to a **scratch** instance just before the mistake, copy the rows back. Don't restore over prod. |
| Bad migration corrupted data | Usually fix-forward. PITR only if fix-forward is impossible. |
| Ransomware / storage loss | Full restore, infra-led. Follow the council DR plan. |

The second row is by far the most common (twice so far, both via the staff
SQL console that we have since removed).

## Restoring to a scratch instance (row recovery)

Infra run something like:

```bash
pgbackrest --stanza=hallpass --type=time \
  --target="2024-10-15 10:42:00+01" --target-action=promote \
  --pg1-path=/var/lib/pgsql/16/scratch restore
```

Note the target time is local with offset. Get the time of the mistake from
`audit_log` if it was done through the app, or the Postgres log if not.

Then we:

1. Connect read-only to the scratch instance.
2. `\copy (SELECT ... ) TO 'recovered.csv'` the rows we need.
3. Write the re-insert as a one-off SQL script, reviewed by a second
   developer, run in a transaction on prod. Include an `audit_log` insert
   saying what was restored and why (`actor_type = 'system'`, action
   `data.restore`).
4. Ask infra to drop the scratch instance.

Watch out for:

- `bookings_no_overlap`: restored bookings may now clash with bookings made
  after the mistake. Those need a human decision (usually the later booking
  gets moved or refunded by staff).
- Payments/refunds: check against Paybridge before re-inserting; a refund may
  have been issued in between.
- `notifications_outbox`: do **not** restore pending rows, or people get old
  emails.

## Full restore of prod

Infra-led. Our part:

1. Stop the worker (comment out `/etc/cron.d/hallpass-worker` on hp-app-01)
   and take both app VMs out of the F5 pool. Put up the maintenance page
   (`switch.sh maintenance`).
2. After infra say the DB is up: run `python -m hallpass.core.db migrate
   --dry-run` with the release's venv to confirm schema_migrations matches the
   code.
3. Anything Paybridge sent us after the recovery point is lost from our
   side. Pull the Paybridge transaction list for the gap (dashboard export),
   ask Paybridge to redeliver those webhooks, and reconcile with finance.
   `pending` refunds in the restored data will be re-sent by `submit_refunds`
   (check they weren't already paid out before re-enabling the worker).
4. Bring web back, then re-enable the worker.
5. Tell Leisure Services which bookings window was lost so the contact centre
   can phone people.

## TODO

- Rehearse again (overdue).
- Automate the "what changed between recovery point and now" Paybridge diff.
