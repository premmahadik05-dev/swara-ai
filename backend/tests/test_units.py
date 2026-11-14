from decimal import Decimal as D

import pytest

from app.nlu.units import convert_quantity, fmt_qty, line_total_paise, quantize_qty


@pytest.mark.parametrize("pu,pack,pku,qty,unit,status,out", [
    ("kg", None, None, "2", "kg", "ok", "2"),
    ("kg", None, None, "500", "g", "ok", "0.5"),
    ("kg", None, None, "250", "g", "ok", "0.25"),
    ("l", None, None, "500", "ml", "ok", "0.5"),
    ("kg", None, None, "2", None, "need_unit", None),
    ("kg", None, None, "2", "l", "mismatch", None),
    ("l", None, None, "1", "kg", "mismatch", None),
    ("pc", None, None, "3", None, "ok", "3"),
    ("pc", None, None, "2", "dozen", "ok", "24"),
    ("pc", None, None, "1.5", None, "non_integer", None),
    ("pack", None, None, "1", "pack", "ok", "1"),
    ("kg", None, None, "0", "kg", "mismatch", None),
    ("kg", None, None, "-1", "kg", "mismatch", None),
    # tea sold in 250 g packs
    ("pack", "0.25", "kg", "1", "kg", "ok", "4"),
    ("pack", "0.25", "kg", "500", "g", "ok", "2"),
    ("pack", "0.25", "kg", "300", "g", "non_integer", None),
    ("pack", "0.25", "kg", "3", "pack", "ok", "3"),
])
def test_convert(pu, pack, pku, qty, unit, status, out):
    c = convert_quantity(pu, D(pack) if pack else None, pku, D(qty), unit)
    assert c.status == status
    if out is not None:
        assert c.qty == D(out)


def test_line_total_is_exact_integer_paise_half_up():
    assert line_total_paise(5800, D("2")) == 11600
    assert line_total_paise(4600, D("2.5")) == 11500
    assert line_total_paise(3333, D("0.5")) == 1667  # 1666.5 -> half-up
    assert line_total_paise(1, D("0.499")) == 0
    assert line_total_paise(1, D("0.5")) == 1
    assert line_total_paise(18500, D("0.375")) == 6938  # 6937.5 -> 6938


def test_no_float_drift_on_many_small_quantities():
    total = sum(line_total_paise(4600, D("0.1")) for _ in range(1000))
    assert total == 460 * 1000


@pytest.mark.parametrize("q,s", [("2", "2"), ("1.50", "1.5"), ("0.250", "0.25"), ("10", "10"), ("100", "100")])
def test_fmt_qty(q, s):
    assert fmt_qty(D(q)) == s


def test_quantize():
    assert quantize_qty(D("0.0005")) == D("0.001")
    assert quantize_qty(D("0.0004")) == D("0.000")
