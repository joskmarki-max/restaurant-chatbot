"""Search correctness: branch isolation, injection safety, honest absence."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db, search


def test_branch_isolation(conn):
    detroit = {r["id"]: r for r in search.browse_menu(conn, "lc-detroit-40")}
    houston = {r["id"]: r for r in search.browse_menu(conn, "lc-houston-811")}
    assert detroit["lc-classic-cheese"]["price_cents"] == 549
    assert houston["lc-classic-cheese"]["price_cents"] == 599
    # Detroit's pepperoni price must never leak into Houston's menu
    assert houston["lc-classic-pepperoni"]["price_cents"] is None


def test_sql_injection_attempt_is_safe(conn):
    evil = "'; DROP TABLE branches; --"
    rows = search.browse_menu(conn, "lc-detroit-40", q=evil)
    assert rows == []  # no match, no crash
    assert db.get_branch(conn, "lc-detroit-40") is not None  # table intact


def test_unknown_branch_rejected(conn):
    import pytest
    from src import validation as v
    with pytest.raises(v.ValidationError):
        search.browse_menu(conn, "no-such-branch")


def test_missing_item_means_not_in_dataset(conn):
    assert db.get_price(conn, "lc-houston-811", "lc-wings") is None


def test_stale_flagged(conn):
    menu = {r["id"]: r for r in search.browse_menu(conn, "lc-detroit-40")}
    assert menu["lc-classic-cheese"]["stale"] is False
    assert menu["lc-classic-pepperoni"]["stale"] is True
