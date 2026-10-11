"""CSV export for reports. Finance open these in Excel, hence the BOM."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

from hallpass.core import money, tz


def _cell(key: str, value: Any) -> Any:
    if value is None:
        return ""
    if key.endswith("_pence") and isinstance(value, int):
        # Excel users want pounds. Keep the raw pence column name though so
        # nobody mistakes which is which when they paste it somewhere.
        return f"{value / 100:.2f}" if abs(value) < 10**12 else money.format_gbp(value)
    if isinstance(value, datetime):
        return tz.format_local(value, "%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    return value


def to_csv(rows: Iterable[Mapping[str, Any]]) -> str:
    rows = list(rows)
    buf = io.StringIO()
    buf.write("﻿")
    if not rows:
        return buf.getvalue()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _cell(k, v) for k, v in row.items()})
    return buf.getvalue()
