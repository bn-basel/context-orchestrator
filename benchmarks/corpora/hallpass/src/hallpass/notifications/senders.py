"""Sender interface plus a recording sender for tests and staging.

Staging has an anonymised copy of prod, but the anonymiser has missed old
mobile numbers before, so staging is wired to RecordingSender for SMS.
Never give staging the real TextHub key.
"""

from __future__ import annotations

from typing import Protocol


class Sender(Protocol):
    def send(self, *, row_id: int, recipient: str, template: str, context: dict) -> str | None:
        """Deliver or raise outbox.TransientSendError / PermanentSendError."""
        ...


class RecordingSender:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, *, row_id: int, recipient: str, template: str, context: dict) -> str | None:
        self.sent.append({"row_id": row_id, "recipient": recipient, "template": template, "context": context})
        return f"rec-{row_id}"
