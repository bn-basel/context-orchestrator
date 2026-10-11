---
kind: known_issue
status: verified
---
# Known issues

## BUG-12: days_overdue counts a partial day as a full day
`loans.days_overdue` uses `math.ceil` on the elapsed seconds, so a book
returned one hour after the due timestamp is charged a full day's fine.
Reproduced with `due_at=2025-03-01T23:59:59Z`, `returned_at=2025-03-02T00:30:00Z`
(expected 0 days, got 1). Not fixed yet.

## BUG-15: renewing an overdue loan clears the fine
`loans.renew` sets a new due date without first recording the fine that had
already accrued. Reproduced manually on 2025-04-20. Not fixed yet.
