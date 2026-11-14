"""Quantity / unit conversion into a product's base selling unit.

Money is kept in integer paise and quantities in :class:`~decimal.Decimal` so that the
order total is exact (no float drift) - see ``tests/test_orders_calc.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

COUNT_UNITS = {"pack", "pc", "bottle", "box", "bag"}
WEIGHT = {"kg": Decimal(1), "g": Decimal("0.001")}
VOLUME = {"l": Decimal(1), "ml": Decimal("0.001")}

Q3 = Decimal("0.001")


@dataclass(frozen=True)
class Conversion:
    status: str  # ok | need_unit | mismatch | non_integer
    qty: Optional[Decimal] = None  # in the product's base unit
    hint: Optional[str] = None  # machine-readable detail for the dialogue manager


def quantize_qty(q: Decimal) -> Decimal:
    return q.quantize(Q3, rounding=ROUND_HALF_UP)


def is_whole(q: Decimal) -> bool:
    return q == q.to_integral_value()


def convert_quantity(
    product_unit: str,
    pack_size: Optional[Decimal],
    pack_size_unit: Optional[str],
    qty: Decimal,
    unit: Optional[str],
) -> Conversion:
    """Convert ``qty`` spoken in ``unit`` into ``product_unit``.

    ``product_unit`` is one of ``kg``, ``l`` (loose goods) or ``pack``, ``pc`` (counted goods).
    ``pack_size`` + ``pack_size_unit`` describe what is inside one counted pack
    (e.g. tea: 0.25 kg) so "1 kilo tea" can become 4 packs.
    """
    if qty <= 0:
        return Conversion("mismatch", hint="non_positive")

    if product_unit in ("kg", "l"):
        table = WEIGHT if product_unit == "kg" else VOLUME
        if unit is None:
            return Conversion("need_unit", hint=product_unit)
        if unit in table:
            return Conversion("ok", quantize_qty(qty * table[unit]))
        if unit in COUNT_UNITS and pack_size is not None and pack_size_unit == product_unit:
            return Conversion("ok", quantize_qty(qty * pack_size))
        return Conversion("mismatch", hint=product_unit)

    # counted goods (pack / pc)
    if unit is None or unit in COUNT_UNITS:
        if not is_whole(qty):
            return Conversion("non_integer", hint="count")
        return Conversion("ok", quantize_qty(qty))
    if unit == "dozen":
        total = qty * 12
        if not is_whole(total):
            return Conversion("non_integer", hint="count")
        return Conversion("ok", quantize_qty(total))
    dim = WEIGHT if unit in WEIGHT else VOLUME if unit in VOLUME else None
    if dim is not None and pack_size is not None and pack_size_unit is not None:
        same_dim = (unit in WEIGHT and pack_size_unit == "kg") or (unit in VOLUME and pack_size_unit == "l")
        if same_dim:
            packs = (qty * dim[unit]) / pack_size
            if abs(packs - packs.to_integral_value()) < Decimal("0.0001"):
                return Conversion("ok", quantize_qty(packs.to_integral_value()))
            return Conversion("non_integer", hint=f"pack_size:{pack_size}{pack_size_unit}")
    return Conversion("mismatch", hint="count")


def line_total_paise(price_paise: int, qty: Decimal) -> int:
    """Exact line total in integer paise, rounded half-up."""
    return int((Decimal(price_paise) * qty).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def fmt_qty(q: Decimal) -> str:
    """Human format: 2 -> '2', 1.5 -> '1.5', 0.25 -> '0.25'."""
    q = q.normalize()
    s = format(q, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s
