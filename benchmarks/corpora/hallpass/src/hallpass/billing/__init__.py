"""Billing: pricing, concessions, VAT, invoices, Paybridge card payments, refunds.

Rough map (see docs/billing/README.md for the longer version):

    pricing.py        price_rules -> a Quote for a space and time range
    concessions.py    resident concessions + block-booking discount
    vat.py            VAT treatment and gross/net splits
    invoices.py       monthly invoices for organisations on account (bank transfer)
    paybridge.py      thin HTTP client for the Paybridge API
    payments.py       hosted checkout, recording payments
    webhooks.py       Paybridge webhook endpoint logic (dedupe + dispatch)
    refunds.py        refund policy (ADR 0012) and issuing refunds/credits
    reconciliation.py nightly check of Paybridge settlements against `payments`

All money is integer pence (ADR 0002). If you find yourself typing `float`
in this package, stop and read hallpass.core.money first.
"""

from hallpass.billing.errors import BillingError, PaybridgeError, RefundNotAllowed

__all__ = ["BillingError", "PaybridgeError", "RefundNotAllowed"]
