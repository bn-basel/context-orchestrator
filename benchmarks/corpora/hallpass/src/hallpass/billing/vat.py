"""VAT treatment of hires.

All tariff prices are VAT-inclusive (gross). Residents only ever see one
number. Organisations get invoices, and the invoice PDF has to show net +
VAT, so we split the gross here *at render time*. invoice_lines only stores
the gross amount_pence -- we never persisted the VAT split. That matters if
the rules below change: re-rendering an old invoice gives different VAT.
(Finance keep the PDFs they sent, so in practice they'd notice.)

Rules as implemented. NOT tax advice, and Finance have not signed off the
charity bit -- read docs/billing/assumptions-vat.md before touching this:

    hirer is a registered charity         exempt   <-- ASSUMPTION, unconfirmed
    sports space, series of 10+ sessions  exempt   (the "series of lets" rule)
    everything else                       standard 20%

The series-of-lets rule is a real HMRC rule (roughly: lets of sports
facilities to the same club, 10+ sessions, at least a day apart, paid for
as a block). We apply a simplified version. The charity rule came from the
old paper booking forms ("charities: no VAT") and nobody has confirmed it.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from hallpass.core.money import vat_from_gross

STANDARD_RATE_PERCENT = 20
SPORTS_KINDS = ("sports_hall", "pitch")


class VatTreatment(enum.StrEnum):
    STANDARD = "standard"
    EXEMPT = "exempt"


@dataclass(frozen=True, slots=True)
class VatSplit:
    gross_pence: int
    net_pence: int
    vat_pence: int
    treatment: VatTreatment


def split_gross(gross_pence: int, treatment: VatTreatment) -> VatSplit:
    """Split a VAT-inclusive amount into net and VAT, net + vat == gross.

    VAT = gross * 20/120, half-up to the penny (core.money.vat_from_gross).
    HMRC allow rounding per line or per invoice; we do it per line, so an
    invoice's VAT total can be a few pence off "total * 1/6".
    """
    if treatment is not VatTreatment.STANDARD:
        return VatSplit(gross_pence, gross_pence, 0, treatment)
    vat = vat_from_gross(gross_pence, STANDARD_RATE_PERCENT)
    return VatSplit(gross_pence, gross_pence - vat, vat, treatment)


def is_registered_charity(organisation: dict | None) -> bool:
    # kind='charity' without a number does happen (data entry). We require
    # the number; a "charity" with no number pays VAT. Arguably wrong, see
    # the assumptions doc.
    return bool(organisation and organisation.get("charity_number"))


def treatment_for(*, space_kind: str, organisation: dict | None, series_occurrences: int) -> VatTreatment:
    # ASSUMPTION (unconfirmed with Finance): registered charities don't pay VAT
    # on hires. If Finance say no, delete this branch; the query to find the
    # affected invoices is in docs/billing/assumptions-vat.md.
    if is_registered_charity(organisation):
        return VatTreatment.EXEMPT
    if space_kind in SPORTS_KINDS and series_occurrences >= 10:
        return VatTreatment.EXEMPT
    return VatTreatment.STANDARD
