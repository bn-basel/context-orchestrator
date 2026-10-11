"""Flask application factory.

gunicorn runs ``hallpass.api.app:create_app()``. Locally::

    flask --app hallpass.api.app run --debug
"""

from __future__ import annotations

import logging
import uuid

from flask import Flask, g, jsonify, request

from hallpass.accounts import sessions
from hallpass.core import db
from hallpass.core.config import get_settings
from hallpass.core.errors import HallpassError

log = logging.getLogger(__name__)


def create_app() -> Flask:
    settings = get_settings()
    app = Flask("hallpass")
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["SESSION_COOKIE_SECURE"] = settings.is_production
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    from hallpass.api import accounts, bookings, payments, reports, staff

    app.register_blueprint(accounts.bp, url_prefix="/api/account")
    app.register_blueprint(bookings.bp, url_prefix="/api/bookings")
    app.register_blueprint(payments.bp, url_prefix="/api/payments")
    app.register_blueprint(staff.bp, url_prefix="/api/staff")
    app.register_blueprint(reports.bp, url_prefix="/api/reports")

    @app.before_request
    def _request_context() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        # Resolves the session cookie to a resident or staff user (or None).
        g.principal = sessions.load_principal(request)

    @app.after_request
    def _add_request_id(resp):
        resp.headers["X-Request-Id"] = g.get("request_id", "")
        return resp

    @app.errorhandler(HallpassError)
    def _hallpass_error(exc: HallpassError):
        if exc.status >= 500:
            log.error("request %s failed: %s", g.get("request_id"), exc.message)
        return jsonify(exc.to_dict()), exc.status

    @app.get("/health/live")
    def live():
        return {"ok": True}

    @app.get("/health/ready")
    def ready():
        with db.connection() as conn:
            db.fetch_one(conn, "SELECT 1")
        return {"ok": True}

    if settings.legacy_healthz:
        # TODO(2024-06): remove once the council LB probe is switched over.
        app.add_url_rule("/healthz", "healthz", ready)

    app.teardown_appcontext(lambda _exc: None)
    return app
