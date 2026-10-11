"""SMS via TextHub, v1 REST API.

    POST {texthub_api_base}/v1/messages   (Bearer texthub_api_key)
    {"to": "+447...", "from": <sender id>, "body": "...", "client_ref": "outbox-<id>"}
    -> 201 {"id": "msg_...", "segments": 1}

client_ref is only echoed back on delivery receipts. It is NOT an
idempotency key: post the same client_ref twice and TextHub sends two texts.
v2 has a real Idempotency-Key header (24h window) but also new auth and a
new receipt format; migration is HP-619, not started.

That's the root of the duplicate texts: on a ReadTimeout we don't know if
TextHub accepted the message, we raise TransientSendError, the outbox
retries, and the resident gets it again. See
docs/findings/notifications-sms-duplicate-sends.md.
"""

from __future__ import annotations

import logging

import httpx

from hallpass.accounts import consents
from hallpass.core.config import get_settings
from hallpass.notifications import templates
from hallpass.notifications.outbox import PermanentSendError, TransientSendError

log = logging.getLogger(__name__)

CONNECT_TIMEOUT = 3.0
# Was 10s until Nov 2024, cut to 5s so slow TextHub calls stopped delaying
# login emails in the same batch. Duplicates went up afterwards.
READ_TIMEOUT = 5.0
PERMANENT_CODES = {"invalid_number", "unroutable", "opted_out", "blocked_content"}


class TextHubSender:
    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.sender_id = s.texthub_sender_id
        self.client = client or httpx.Client(
            base_url=s.texthub_api_base,
            headers={"Authorization": f"Bearer {s.texthub_api_key}"},
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        )

    def send(self, *, row_id: int, recipient: str, template: str, context: dict) -> str | None:
        body = templates.render_sms(template, context)
        if templates.sms_segments(body) > 2:
            log.warning("sms outbox %s over 2 segments, truncating", row_id)
            body = body[:300] + "..."
        payload = {"to": recipient, "from": self.sender_id, "body": body, "client_ref": f"outbox-{row_id}"}
        try:
            resp = self.client.post("/v1/messages", json=payload)
        except httpx.ConnectTimeout as exc:
            raise TransientSendError("texthub connect timeout") from exc  # never reached them: safe
        except httpx.ReadTimeout as exc:
            # Unknown outcome. Treated as transient => possible duplicate.
            raise TransientSendError("texthub read timeout") from exc
        except httpx.HTTPError as exc:
            raise TransientSendError(f"texthub: {exc}") from exc

        if resp.status_code in (200, 201, 202):
            msg_id = resp.json().get("id")
            # No column for it (yet); the log is the only place it's kept.
            log.info("sms outbox %s accepted as %s", row_id, msg_id)
            return msg_id
        if resp.status_code == 429 or resp.status_code >= 500:
            raise TransientSendError(f"texthub {resp.status_code}")
        try:
            code = resp.json().get("error", {}).get("code")
        except ValueError:
            code = None
        if code in PERMANENT_CODES or resp.status_code in (400, 404, 422):
            raise PermanentSendError(f"texthub {resp.status_code} {code}")
        raise TransientSendError(f"texthub unexpected {resp.status_code}")


def handle_stop(conn, *, phone: str) -> int:
    """TextHub opt-out webhook (someone texted STOP). Opts out every resident
    on that number - families share phones - and cancels queued texts."""
    rows = conn.execute("SELECT id FROM residents WHERE phone = %s AND deleted_at IS NULL", (phone,)).fetchall()
    for (rid,) in rows:
        consents.record(conn, rid, "sms_reminders", False, source="sms_stop")
    conn.execute(
        "UPDATE notifications_outbox SET status = 'failed', last_error = 'STOP received' "
        "WHERE channel = 'sms' AND recipient = %s AND status = 'pending'",
        (phone,),
    )
    # Note: STOP only records sms_reminders. Waitlist offers and closure texts
    # don't check consent (see recipients.py), so they keep coming. Known issue.
    return len(rows)
