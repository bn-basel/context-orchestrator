import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from hallpass.core import clock
from hallpass.notifications.senders import RecordingSender

# A Tuesday morning in BST. `pg_conn` comes from tests/conftest.py.
T0 = datetime(2025, 6, 10, 9, 30, tzinfo=UTC)


@pytest.fixture
def frozen():
    with clock.frozen(T0):
        yield


@pytest.fixture
def senders():
    return RecordingSender(), RecordingSender()


@pytest.fixture
def booking(pg_conn):
    """facility + space + resident + confirmed booking. Returns (booking_id, resident_id)."""

    seq = iter(range(1, 100))

    def _make(*, phone="+447700900333", starts_in=timedelta(hours=26), status="confirmed"):
        n = next(seq)
        email = "priya@example.org" if n == 1 else f"priya{n}@example.org"
        (fid,) = pg_conn.execute("INSERT INTO facilities (name) VALUES ('Eastfield Leisure Centre') RETURNING id").fetchone()
        (sid,) = pg_conn.execute(
            "INSERT INTO spaces (facility_id, name) VALUES (%s, 'Studio 2') RETURNING id", (fid,)
        ).fetchone()
        (rid,) = pg_conn.execute(
            "INSERT INTO residents (email, full_name, phone) VALUES (%s, 'Priya Shah', %s) RETURNING id",
            (email, phone),
        ).fetchone()
        start = T0 + starts_in
        (bid,) = pg_conn.execute(
            "INSERT INTO bookings (space_id, resident_id, starts_at, ends_at, status, price_pence) "
            "VALUES (%s, %s, %s, %s, %s, 1200) RETURNING id",
            (sid, rid, start, start + timedelta(hours=1), status),
        ).fetchone()
        return bid, rid

    return _make


class FakeTextHub:
    """TextHub v1 stand-in. Each request consumes one step: "ok",
    "read_timeout" (TextHub accepted it, we never saw the reply),
    "connect_timeout", "500", "invalid_number"."""

    def __init__(self, steps=()):
        self.steps = list(steps)
        self.accepted: list[dict] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        step = self.steps.pop(0) if self.steps else "ok"
        if step == "connect_timeout":
            raise httpx.ConnectTimeout("connect", request=request)
        if step == "invalid_number":
            return httpx.Response(422, json={"error": {"code": "invalid_number"}})
        if step == "500":
            return httpx.Response(500, text="nope")
        self.accepted.append(json.loads(request.content))
        if step == "read_timeout":
            raise httpx.ReadTimeout("read", request=request)
        return httpx.Response(201, json={"id": f"msg_{len(self.accepted)}", "segments": 1})

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="https://texthub.test", transport=httpx.MockTransport(self._handle))
