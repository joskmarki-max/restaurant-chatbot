"""Money math: integer cents, no float rounding, honest unknown handling."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from src import comparison, database as db, validation as v


def test_cents_arithmetic_no_float_error():
    # 12.00 + 2.00 + 1.50 + 1.00 = 16.50 -> 1650 cents exactly
    assert comparison.total_with_extras(1200, [200, 150, 100]) == 1650


def test_unknown_extra_means_unknown_total():
    assert comparison.total_with_extras(1200, [200, None]) is None


def test_discount_applies():
    assert comparison.total_with_extras(1200, [200], discount_cents=100) == 1300


def test_parse_budget_variants():
    assert v.parse_budget_cents("15") == 1500
    assert v.parse_budget_cents("$15") == 1500
    assert v.parse_budget_cents("12.50") == 1250
    assert v.parse_budget_cents(15) == 1500


def test_parse_budget_rejects_bad_input():
    for bad in ["0", "-5", "abc", "", "$", "1.234", "999999999"]:
        with pytest.raises(v.ValidationError):
            v.parse_budget_cents(bad)
    for bad in [float("nan"), float("inf"), -3.5, True]:
        with pytest.raises(v.ValidationError):
            v.parse_budget_cents(bad)


def test_cents_to_str():
    assert db.cents_to_str(1650) == "$16.50"
    assert db.cents_to_str(None) == "Unavailable"
