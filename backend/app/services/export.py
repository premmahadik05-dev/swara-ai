"""CSV exports (orders, stock, customers). Pure functions: rows in, bytes out.

Two things matter here beyond "write a CSV":
  * Spreadsheet formula injection. A product, customer or note that starts with = + - @ (or a tab / carriage return) is run as a
    formula by Excel and Google Sheets when the file is opened. Text cells that start that way get a leading apostrophe, which the
    spreadsheet shows as plain text. Real numbers are passed as numbers, so a negative quantity is not changed.
  * Excel on Windows opens a UTF-8 file as ANSI unless it starts with a byte-order mark, which turns Gujarati and Hindi names
    into rubbish. The file starts with one.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from fastapi import Response

IST = timedelta(hours=5, minutes=30)
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> Any:
    """A cell value that a spreadsheet will show as written."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def rupees(paise: int | None) -> str:
    """Whole paise as a plain decimal rupee amount, two places, no symbol or separators (so a spreadsheet reads a number)."""
    return f"{(paise or 0) / 100:.2f}"


def qty(value: Any) -> str:
    """Quantities such as 2.5 or 12 without trailing zeros."""
    d = Decimal(str(value))
    text = format(d.normalize(), "f")
    return text if "." in text or d == d.to_integral() else str(d)


def ist(value: datetime | None) -> str:
    """A UTC (naive) timestamp from the database as 'YYYY-MM-DD HH:MM' in Indian time."""
    return (value + IST).strftime("%Y-%m-%d %H:%M") if value else ""


def to_csv(header: list[str], rows: Iterable[list[Any]]) -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([safe_cell(c) for c in r])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def csv_response(body: bytes, name: str, truncated: bool = False) -> Response:
    """The download: attachment, never cached (it holds the shop's data), and flagged when more rows matched than one file holds."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    headers = {"Content-Disposition": f'attachment; filename="swara-{name}-{stamp}.csv"', "Cache-Control": "no-store"}
    if truncated:
        headers["X-Export-Truncated"] = "true"
    return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)
