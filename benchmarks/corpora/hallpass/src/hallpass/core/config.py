"""Settings, read once from the environment.

Everything is prefixed HALLPASS_. In prod the values come from the systemd
EnvironmentFile (/etc/hallpass/hallpass.env), which is managed by Ansible in the
infra repo, not here.

Two ways in:

    from hallpass.core.config import get_settings     # preferred
    from hallpass.core.config import settings         # lazy proxy, same object

The accounts/notifications code was written against an older settings module
that used UPPER_CASE names (``settings.SMTP_HOST``). The proxy still answers
to those by lower-casing them. Please use lower case in new code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    db_pool_min: int
    db_pool_max: int
    secret_key: str
    session_secret: str
    magic_link_secret: str
    base_url: str

    paybridge_api_base: str
    paybridge_api_key: str
    paybridge_webhook_secret: str  # comma-separated during a rotation

    smtp_host: str
    smtp_port: int
    email_from: str
    email_reply_to: str
    email_domain: str
    email_backend: str  # "smtp" or "console"

    texthub_base_url: str
    texthub_api_key: str
    texthub_sender_id: str

    hold_minutes: int = 15
    magic_link_ttl_minutes: int = 20
    log_json: bool = True
    # Kept for the old /healthz check used by the load balancer. Don't remove
    # until infra confirm they've moved to /health/ready.
    legacy_healthz: bool = True
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.environ
    environment = env.get("HALLPASS_ENV", "development")
    secret_key = env.get("HALLPASS_SECRET_KEY", "dev-not-secret")
    settings = Settings(
        environment=environment,
        database_url=env.get("HALLPASS_DATABASE_URL", "postgresql:///hallpass_dev"),
        db_pool_min=_int(env.get("HALLPASS_DB_POOL_MIN"), 2),
        db_pool_max=_int(env.get("HALLPASS_DB_POOL_MAX"), 10),
        secret_key=secret_key,
        # Separate secrets so rotating one doesn't sign everybody out AND
        # invalidate links in flight. Fall back to secret_key in dev.
        session_secret=env.get("HALLPASS_SESSION_SECRET", secret_key),
        magic_link_secret=env.get("HALLPASS_MAGIC_LINK_SECRET", secret_key),
        base_url=env.get("HALLPASS_BASE_URL", "http://localhost:5000"),
        paybridge_api_base=env.get("HALLPASS_PAYBRIDGE_API_BASE", "https://sandbox.paybridge.example/v2"),
        paybridge_api_key=env.get("HALLPASS_PAYBRIDGE_API_KEY", ""),
        paybridge_webhook_secret=env.get("HALLPASS_PAYBRIDGE_WEBHOOK_SECRET", ""),
        smtp_host=env.get("HALLPASS_SMTP_HOST", "localhost"),
        smtp_port=_int(env.get("HALLPASS_SMTP_PORT"), 25),
        email_from=env.get("HALLPASS_EMAIL_FROM", "bookings@leisure.council.example"),
        email_reply_to=env.get("HALLPASS_EMAIL_REPLY_TO", "leisure.bookings@council.example"),
        email_domain=env.get("HALLPASS_EMAIL_DOMAIN", "leisure.council.example"),
        email_backend=env.get("HALLPASS_EMAIL_BACKEND", "console"),
        texthub_base_url=env.get("HALLPASS_TEXTHUB_BASE_URL", "https://api.texthub.example"),
        texthub_api_key=env.get("HALLPASS_TEXTHUB_API_KEY", ""),
        texthub_sender_id=env.get("HALLPASS_TEXTHUB_SENDER_ID", "COUNCIL"),
        hold_minutes=_int(env.get("HALLPASS_HOLD_MINUTES"), 15),
        magic_link_ttl_minutes=_int(env.get("HALLPASS_MAGIC_LINK_TTL_MINUTES"), 20),
        log_json=_bool(env.get("HALLPASS_LOG_JSON"), default=environment != "development"),
        legacy_healthz=_bool(env.get("HALLPASS_LEGACY_HEALTHZ"), default=True),
    )
    if settings.is_production:
        _check_production(settings)
    return settings


def _check_production(s: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("HALLPASS_SECRET_KEY", s.secret_key if s.secret_key != "dev-not-secret" else ""),
            ("HALLPASS_PAYBRIDGE_API_KEY", s.paybridge_api_key),
            ("HALLPASS_PAYBRIDGE_WEBHOOK_SECRET", s.paybridge_webhook_secret),
            ("HALLPASS_TEXTHUB_API_KEY", s.texthub_api_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing production settings: {', '.join(missing)}")
    if s.email_backend != "smtp":
        raise RuntimeError("production must use the SMTP relay (HALLPASS_EMAIL_BACKEND=smtp)")


class _SettingsProxy:
    """Module-level ``settings`` that resolves on first attribute access, so
    importing this module never reads the environment (tests set env vars in
    fixtures, after import)."""

    def __getattr__(self, name: str) -> Any:
        s = get_settings()
        if name.isupper():
            name = name.lower()
        return getattr(s, name)

    def __repr__(self) -> str:
        return "<hallpass settings proxy>"


settings = _SettingsProxy()
