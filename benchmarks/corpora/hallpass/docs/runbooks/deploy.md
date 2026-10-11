---
kind: doc
status: verified
---

# Runbook: deploying Hallpass

## When

- Change window: **Tuesday-Thursday, 08:00-15:00**. Not Fridays, not bank
  holiday eves.
- No deploys in the week bookings open for a new school term (usually the last
  week of August and the first week of January) unless it's a fix for
  something broken. Leisure Services publish the dates; they're also in the
  team calendar.
- Each production deploy needs a change request in the council ITSM tool
  (standard change "Hallpass release", pre-approved, just raise and link it).

## Before

1. `main` is green in CI.
2. CHANGELOG has a section for the version; bump `version` in
   `pyproject.toml`; tag `vX.Y.Z`. CI builds the wheel and attaches it to the
   tag.
3. Any migrations in this release? Check `db/migrations/` against
   `SELECT filename FROM schema_migrations ORDER BY 1` on prod (read-only
   login is fine). Read each new one. If it touches `bookings`, `audit_log` or
   `notifications_outbox` in a way that rewrites the table, talk to the DBA
   first and plan for out-of-hours.
4. Post in the Leisure Services Teams channel: "Hallpass update at HH:MM,
   expect up to 2 minutes of slowness". (They will forget, but we told them.)

## Deploy

Run from the jump host as the `hallpass-deploy` user:

```bash
cd /opt/hallpass-deploy
./release.sh v3.4.2          # downloads wheel, installs into /opt/hallpass/releases/v3.4.2/venv
./migrate.sh v3.4.2          # runs: python -m hallpass.core.db migrate  (against the primary)
./switch.sh v3.4.2 hp-app-02 # symlink + systemctl restart hallpass-web, waits for /health/ready
./switch.sh v3.4.2 hp-app-01
```

Migrations run **before** the code switch, so a migration must be
compatible with the old code still running for a minute or two. Adding a
nullable column: fine. Renaming or dropping: two releases.

`switch.sh` takes each VM out of the F5 pool, restarts gunicorn, waits for
`/health/ready` to return 200 three times, puts it back.

hp-app-01 also runs the worker crontab. The crontab points at
`/opt/hallpass/current/venv/bin/hallpass-worker`, so it picks up the new
release on the next minute. Nothing to restart.

## After

- Smoke test: sign in as the test resident (magic link goes to the team
  mailbox), search availability at Eastfield, hold a slot, cancel it.
- Watch the error log for 15 minutes: `journalctl -u hallpass-web -f` on both
  VMs, and `grep ERROR /var/log/hallpass/worker.log`.
- Check `SELECT count(*) FROM notifications_outbox WHERE status='pending' AND
  not_before < now() - interval '5 minutes'` is ~0 (outbox draining).
- Close the change request.

## Rollback

```bash
./switch.sh v3.4.1 hp-app-02
./switch.sh v3.4.1 hp-app-01
```

Migrations are not rolled back. If a migration is the problem, write a fix-
forward migration, or in the worst case restore (see
`restore-from-backup.md`) - which loses data, so it needs the service manager's
sign-off.

## If hp-app-01 is down

The worker doesn't run anywhere. Holds won't expire and emails won't go.
Enable the crontab on 02:

```bash
sudo cp /opt/hallpass/current/deploy/crontab.worker /etc/cron.d/hallpass-worker
```

Remove it again when 01 is back. Running on both briefly is harmless (advisory
locks) but doubles the log noise.
