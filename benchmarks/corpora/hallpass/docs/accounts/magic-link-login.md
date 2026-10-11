---
kind: doc
status: verified
---

# Login: how it works and what to tell people when it doesn't

Background in ADR 0004. Code: `hallpass/accounts/auth.py`, `sessions.py`.

## Short version

1. Customer types their email on the login page.
2. If there's an account, we queue a `magic_link` email. If not, nothing
   happens - the page says the same thing either way.
3. Clicking the link logs them in for 30 days.

A link is good for **20 minutes** and works once. Using any link kills all
older links for that person. Asking for a new link does *not* kill the old
ones until one of them is used.

## Service desk crib sheet

**"I never got the email"**

```sql
SELECT status, attempts, last_error, created_at, sent_at
FROM notifications_outbox
WHERE recipient = '<email>' AND template = 'magic_link'
ORDER BY id DESC LIMIT 5;
```

- `sent` = the relay took it. Spam folder, or slow mail at their end
  (schools, NHS - 10 to 20 minute delays, and the link only lasts 20).
- No rows: no account under that address (typo? registered with a
  different one?), or they hit the limit of 5 links an hour, which is
  silent.
- `dead`/`failed`: read `last_error`; relay problems go to IT.

**"The link says it's expired or already used"**, most likely first:

1. They clicked an older email after using a newer one.
2. More than 20 minutes passed.
3. Opened on the phone, then on the laptop - the first one won.
4. Their organisation's mail security opened the link before they did
   (Outlook Safe Links and similar). We log in on GET, so a scanner opening
   the link uses it up. Common with schools and the hospital trust.

Ask them to request a fresh link and use the newest email. For case 4, a
personal email address works around it.

**"I keep getting logged out"** - resident sessions last 30 days; usually the
browser is clearing cookies (private mode, library PCs). Staff sessions are a
fixed 12 hours.

**"Log me out everywhere / my phone was stolen"** - we can't, for residents.
Sessions are signed cookies with no server-side record. Best we can do is
change the account email (old link mail stops arriving) and wait out the 30
days. Staff are different: disabling the account (`active = false`) takes
effect on the next request.

## Changing someone's email

No self-service. Service desk can change it in the back office after checking
identity over the phone (a recent booking reference plus the postcode on the
account). Never create a second account for the new address - it splits
their booking history and refunds go astray.
