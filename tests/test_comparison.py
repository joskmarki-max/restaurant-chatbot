"""Budget + comparison fairness (PRD section 10)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import comparison, search


def test_budget_boundary_inclusive(conn):
    menu = search.browse_menu(conn, "lc-detroit-40")
    eligible = comparison.filter_by_budget(menu, 549)  # exactly the cheese price
    assert [r["id"] for r in eligible] == ["lc-classic-cheese"]


def test_stale_excluded_from_budget(conn):
    menu = search.browse_menu(conn, "lc-detroit-40")
    eligible = comparison.filter_by_budget(menu, 10_000)
    ids = [r["id"] for r in eligible]
    assert "lc-classic-pepperoni" not in ids  # stale -> excluded, with reason
    excluded = {r["id"]: r["exclude_reason"] for r in comparison.excluded_from_budget(menu, 10_000)}
    assert "stale" in excluded["lc-classic-pepperoni"]


def test_results_sorted_cheapest_first(conn):
    menu = search.browse_menu(conn, "lc-houston-811")
    eligible = comparison.filter_by_budget(menu, 10_000)
    prices = [r["price_cents"] for r in eligible]
    assert prices == sorted(prices)


def test_compare_flags_size_mismatch():
    a = {"name": "A", "size": "Large", "serving_basis": "whole", "price_cents": 500}
    b = {"name": "B", "size": "Medium", "serving_basis": "whole", "price_cents": 400}
    res = comparison.compare_two(a, b)
    assert res["cheaper"] == "b" and res["diff_cents"] == 100
    assert any("Size differs" in n for n in res["fairness_notes"])


def test_compare_flags_serving_mismatch():
    a = {"name": "A", "size": "Large", "serving_basis": "slice", "price_cents": 200}
    b = {"name": "B", "size": "Large", "serving_basis": "whole", "price_cents": 1500}
    res = comparison.compare_two(a, b)
    assert any("Serving differs" in n for n in res["fairness_notes"])


def test_compare_tie():
    a = {"name": "A", "size": "Large", "serving_basis": "whole", "price_cents": 500}
    b = {"name": "B", "size": "Large", "serving_basis": "whole", "price_cents": 500}
    assert comparison.compare_two(a, b)["cheaper"] == "tie"
