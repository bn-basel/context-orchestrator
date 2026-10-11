"""Checkout + Paybridge webhook.

The webhook endpoint must stay fast and must not depend on the session; it is
called by Paybridge, not a browser. Signature check, storing the raw event in
paybridge_events and acting on it all happen in billing.webhooks, inside one
transaction. See docs/runbooks/paybridge-outage.md.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, redirect, request

from hallpass.accounts import residents
from hallpass.api._helpers import json_body, require_resident, to_json
from hallpass.billing import payments, webhooks
from hallpass.core import db
from hallpass.core.config import get_settings

log = logging.getLogger(__name__)

bp = Blueprint("payments", __name__)


@bp.post("/checkout")
def start_checkout():
    who = require_resident()
    body = json_body()
    with db.transaction() as conn:
        me = residents.get(conn, who.id)
        started = payments.start_checkout(conn, int(body["booking_id"]), me.email)
    # {"payment_id": ..., "redirect_url": "...paybridge hosted page..."}
    return to_json(started)


@bp.get("/return")
def checkout_return():
    """Where Paybridge sends the browser back to. We do NOT treat this as
    'paid': confirmation only ever happens off the webhook. The front end polls
    the booking until it flips to confirmed (usually < 5 seconds)."""
    ref = request.args.get("ref", "")
    return redirect(f"{get_settings().base_url}/bookings/pending?ref={ref}", code=302)


@bp.post("/paybridge/webhook")
def paybridge_webhook():
    raw = request.get_data(cache=False)
    with db.transaction() as conn:
        status = webhooks.handle_delivery(conn, raw, request.headers)
    # 2xx for anything we stored, including duplicates; otherwise Paybridge
    # retries for 72h and we end up with more duplicates, not fewer.
    if status >= 400:
        log.warning("paybridge webhook rejected (%s) from %s", status, request.remote_addr)
    return jsonify({"status": status}), status
