from __future__ import annotations

from hallpass.core.errors import ConflictError, HallpassError, PolicyError, UpstreamError


class BillingError(HallpassError):
    """Base class for anything that goes wrong with money."""


class NoPriceRule(PolicyError):
    """No price_rules row covers part of the requested time.

    Usually means someone added opening hours for a space without adding a
    matching rule. The booking page shows this as "This space has no price for
    that time" which confuses everyone; the fix is in docs/billing/how-to-price-rules.md.
    """

    default_code = "no_price_rule"

    def __init__(self, space_id: int, local_label: str):
        super().__init__(
            f"no price rule for space {space_id} at {local_label}",
            details={"space_id": space_id, "at": local_label},
        )
        self.space_id = space_id
        self.local_label = local_label


class PaybridgeError(UpstreamError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message, provider="paybridge")
        self.status_code = status_code
        self.body = body


class SignatureInvalid(BillingError):
    status = 400
    default_code = "bad_signature"


class RefundNotAllowed(PolicyError):
    default_code = "refund_not_allowed"


class AlreadyRefunded(ConflictError):
    default_code = "already_refunded"


class InvoiceStateError(ConflictError):
    default_code = "invoice_state"
