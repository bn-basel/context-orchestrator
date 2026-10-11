"""Thin client for the Paybridge REST API (v2).

We only use four endpoints:

    POST /v2/checkout/sessions      create a hosted checkout page
    GET  /v2/payments/{id}          look up a payment (reconciliation, support)
    POST /v2/refunds                full or partial refund of a payment
    GET  /v2/settlements            daily settlement report (reconciliation)

Auth is a bearer secret key (``HALLPASS_PAYBRIDGE_API_KEY``). Test keys start
``pb_test_``, live ones ``pb_live_``; config refuses to start in production
with a test key.

Every POST sends an ``Idempotency-Key``. Paybridge keeps them for 24 hours,
so retrying a refund with the same key inside that window cannot double-refund.
After 24 hours it can. Keep that in mind before hitting "retry" on an old
failed refund in the staff UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
import structlog

from hallpass.billing.errors import PaybridgeError
from hallpass.core.config import get_settings

log = structlog.get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: str  # cs_...
    url: str
    payment_id: str | None  # pay_... ; Paybridge creates it up front since API 2024-02


class PaybridgeClient:
    def __init__(self, base_url: str | None = None, secret_key: str | None = None, *, http: httpx.Client | None = None):
        settings = get_settings()
        # paybridge_api_base already ends in /v2, hence the odd-looking paths below.
        self._base = (base_url or settings.paybridge_api_base).rstrip("/")
        key = secret_key or settings.paybridge_api_key
        self._http = http or httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            headers={"Authorization": f"Bearer {key}", "Paybridge-Version": "2024-02-01"},
        )

    def _post(self, path: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        try:
            resp = self._http.post(
                f"{self._base}{path}", json=payload, headers={"Idempotency-Key": idempotency_key}
            )
        except httpx.HTTPError as exc:  # timeouts, DNS, the usual
            raise PaybridgeError(f"POST {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            log.warning("paybridge.error", path=path, status=resp.status_code, body=resp.text[:500])
            raise PaybridgeError(f"POST {path} -> {resp.status_code}", status_code=resp.status_code, body=resp.text)
        return resp.json()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = self._http.get(f"{self._base}{path}", params=params)
        except httpx.HTTPError as exc:
            raise PaybridgeError(f"GET {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise PaybridgeError(f"GET {path} -> {resp.status_code}", status_code=resp.status_code, body=resp.text)
        return resp.json()

    def create_checkout_session(
        self,
        *,
        amount_pence: int,
        reference: str,
        description: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        expires_in_seconds: int = 900,
    ) -> CheckoutSession:
        body = self._post(
            "/checkout/sessions",
            {
                "amount": amount_pence,
                "currency": "GBP",
                "reference": reference,
                "description": description[:120],
                "customer": {"email": customer_email},
                "success_url": success_url,
                "cancel_url": cancel_url,
                "expires_in": expires_in_seconds,
            },
            idempotency_key=f"checkout:{reference}",
        )
        return CheckoutSession(id=body["id"], url=body["url"], payment_id=body.get("payment_id"))

    def get_payment(self, payment_id: str) -> dict[str, Any]:
        return self._get(f"/payments/{payment_id}")

    def create_refund(self, *, payment_id: str, amount_pence: int, idempotency_key: str, note: str = "") -> dict[str, Any]:
        return self._post(
            "/refunds",
            {"payment_id": payment_id, "amount": amount_pence, "metadata": {"note": note[:200]}},
            idempotency_key=idempotency_key,
        )

    def settlements(self, day: date) -> list[dict[str, Any]]:
        # Paginated in theory. We have never had more than one page (limit 500)
        # in a day, so we don't follow `next`. TODO if we ever get busy.
        body = self._get("/settlements", {"date": day.isoformat(), "limit": 500})
        return list(body.get("data", []))
