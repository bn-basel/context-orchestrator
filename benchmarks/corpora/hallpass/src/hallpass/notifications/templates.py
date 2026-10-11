"""Message templates: src/hallpass/notifications/templates/<name>.<channel>.txt

Plain str.format placeholders. (Jinja was removed in 2024; all it did was
{{ name }}.) Every placeholder must be in the outbox row's context or the
send fails permanently.

SMS: TextHub bills per segment. Keep under ~250 chars with real data and use
GSM-7 only - a pound sign or curly quote switches the whole message to UCS-2
and a segment drops from 153 to 67 chars. Write "12.50", not "£12.50".
"""

from __future__ import annotations

import string
from importlib import resources

from hallpass.core.config import get_settings
from hallpass.notifications.outbox import PermanentSendError

SUBJECTS = {
    "magic_link": "Your login link",
    "staff_magic_link": "Hallpass staff login",
    "booking_confirmed": "Booking confirmed: {space_name}, {date_text}",
    "booking_cancelled": "Booking cancelled: {space_name}, {date_text}",
    "booking_reminder": "Reminder: {space_name} tomorrow",
    "series_confirmed": "Your block booking is confirmed",
    "series_cancelled": "Your block booking has been cancelled",
    "series_sessions_closed": "Some of your sessions can't go ahead",
    "waitlist_offer": "A space has come up",
    "refund_issued": "Your refund",
    "invoice_issued": "Invoice from Leisure Services",
}

GSM7 = set("@$\n\r !\"#%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_")


class _Strict(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str) and key not in kwargs:
            raise PermanentSendError(f"template placeholder {{{key}}} missing")
        return super().get_value(key, args, kwargs)


_fmt = _Strict()


def load(template: str, channel: str) -> str:
    try:
        return resources.files("hallpass.notifications").joinpath(
            "templates", f"{template}.{channel}.txt").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PermanentSendError(f"no template {template}.{channel}") from None


def _with_link(context: dict) -> dict:
    ctx = dict(context)
    if "token" in ctx:
        ctx["link"] = f"{get_settings().base_url}/api/account/magic-link/{ctx['token']}"
    return ctx


def render_email(template: str, context: dict) -> tuple[str, str]:
    ctx = _with_link(context)
    return _fmt.format(SUBJECTS.get(template, "Leisure bookings"), **ctx), _fmt.format(load(template, "email"), **ctx)


def render_sms(template: str, context: dict) -> str:
    return _fmt.format(load(template, "sms"), **_with_link(context)).strip()


def sms_segments(body: str) -> int:
    if all(ch in GSM7 for ch in body):
        per = 160 if len(body) <= 160 else 153
    else:
        per = 70 if len(body) <= 70 else 67
    return max(1, -(-len(body) // per))
