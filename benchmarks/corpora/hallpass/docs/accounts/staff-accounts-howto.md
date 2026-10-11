# How to: add, change or disable a staff account

Superusers only. Staff live in `staff_users` (email, full_name, role,
active). There's no staff self sign-up: if the email isn't in the table, the
login page just pretends to send a link.

## New starter

1. Get the request in writing from their line manager, naming the role:
   facility_staff, finance or superuser. Superuser also needs the Leisure
   Systems Manager's OK.
2. Back office -> Staff -> Add. **Council** email address only, never a
   personal one.
3. They log in from the normal login page with that address. Link expires in
   20 minutes.

If the back office is broken:

```sql
INSERT INTO staff_users (email, full_name, role)
VALUES ('first.last@council.example', 'First Last', 'facility_staff');
```

then add an `audit_log` row by hand (actor_type 'staff', your id, action
'staff.create').

## Changing role

Edit it in the back office. It takes effect on their next request, because
the role is read from the table each time rather than stored in the cookie.
Moving someone to finance or superuser needs the same written approval as a
new starter.

## Leavers

Set `active = false` ("Disable" in the back office). Never delete the row;
bookings, refunds and audit entries point at it. Disabling ends their session
straight away.

Note that a staff login link already sitting in their inbox keeps working
until it expires (staff links aren't single use), but it's useless once the
account is inactive.

HR leaver notices don't reach us automatically. We check quarterly against the
list Leisure HR send round; the last check found two people who had left in
the spring still active.

## Shared reception logins

No. Asked about every six months. Each person gets their own account so the
audit log means something.
