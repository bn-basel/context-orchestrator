# Adding a new notification

Checklist. An hour if nothing's weird.

1. **Name the template.** snake_case; past tense for events
   (`booking_moved`), noun for offers (`waitlist_offer`). It goes into
   `notifications_outbox.template`.
2. **Subject line** in `SUBJECTS` in `notifications/templates.py`.
3. **Template files** in `src/hallpass/notifications/templates/`:
   `<name>.email.txt`, and `<name>.sms.txt` if it can go by text. `{placeholder}`
   style. Every placeholder must exist in the row's context or the send fails
   permanently - no retry. SMS: plain ASCII, no pound sign, under ~250 chars
   with realistic data.
4. **Who gets it** - check `notifications/recipients.py`. If your template
   is keyed on an id it doesn't know (say `closure_id`), add a lookup to
   `_LOOKUPS`. Decide about SMS deliberately: if it's in any way promotional
   it's email only, and only with marketing consent.
5. **Enqueue it** inside the same transaction as the change:

   ```python
   from hallpass.notifications.outbox import enqueue

   enqueue(conn, template="booking_moved", booking_id=booking.id)
   ```

   Extra values go in `context={...}`; they're merged over what recipients.py
   works out. Don't call a sender directly, ever, and don't enqueue after
   commit.
6. **Run twice?** If the calling code is a job or a webhook that can run
   again for the same event, guard it at the caller (see how reminders use
   `bookings.reminder_queued_at`). The outbox has no dedupe of its own.
7. **Tests**: add the SMS template to `SMS_TEMPLATES` in
   `tests/notifications/test_templates.py`.

Dates and times in the context must already be strings in Europe/London
(`hallpass.core.tz.format_local`). In summer 2023 we told everyone their
18:00 booking was at 17:00.
