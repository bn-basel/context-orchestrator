Platform review - 6 Feb 2025
=============================

attendees: Priya, Marcus Doyle (new dev, started Jan), Gareth (infra), Helen
Achebe (Head of Digital, first 20 mins only)

(rough notes, Marcus typing)

**Kubernetes?**
- council is standing up a k8s platform, Helen asked if Hallpass should be an
  early adopter
- Gareth: platform not GA until at least Q4, no Postgres operator agreed yet,
  DB would stay on VMs anyway
- Priya: our deploy is 4 shell scripts and works, main pain is the change
  request admin not the tooling
- => not now. revisit when platform is GA. helen ok with that
- not an ADR because we didn't decide to do anything (priya)

**Python 3.13**
- RHEL AppStream doesn't have it yet. stay on 3.12. pin `<3.13` in pyproject
  so nobody "helpfully" bumps it

**deploy windows**
- Helen wants a freeze around term booking opening. agreed: no deploys in the
  week bookings open for a term (end Aug, early Jan), fixes only. Added to
  deploy runbook
- also no Friday deploys, this was already the unwritten rule

**backups**
- restore rehearsal was due Jan, slipped. gareth to rebook for march.
  (edit Oct 2025: slipped again)
- gareth reminded us replica != backup. someone deleted 30 bookings via the
  staff SQL console last year. Priya: console removed in 2.6, yes

**reports on the replica**
- still not done from last year. Marcus to look at it - needs a second pool in
  core/db.py and a `HALLPASS_REPORTS_DATABASE_URL`. small job
- (didn't happen, marcus got pulled onto the accessibility fixes)

**SMS cost**
- TextHub invoice up 40% since reminders went live. Helen asked if SMS should
  be opt-in rather than on. Priya thinks it is already opt-in? Marcus not sure,
  the consent default is set somewhere in accounts. ACTION nobody, "check".

**monitoring**
- we have journald + cron emails + the F5 health check. that's it
- Gareth: council has a Grafana/Loki stack we can ship logs to for free.
  agreed in principle, needs JSON logs (we have HALLPASS_LOG_JSON) and a
  promtail config from infra
- no date

actions
- gareth: restore rehearsal
- marcus: reports → replica
- priya: pin python, runbook freeze wording
- gareth: promtail
