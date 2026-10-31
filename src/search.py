"""Approved search functions. The only way the UI and the LLM layer read data.

Deterministic: same database + same inputs = same results, with or without AI.
"""

from __future__ import annotations

import sqlite3

from . import database as db
from . import validation as v


def find_branches(
    conn: sqlite3.Connection,
    city: str | None = None,
    zip_code: str | None = None,
    name: str | None = None,
) -> list[dict]:
    if city:
        city = v.clean_text(city, "city")
    if zip_code:
        zip_code = v.clean_text(zip_code, "ZIP")
    if name:
        name = v.clean_text(name, "restaurant name")
    return [dict(r) for r in db.get_branches(conn, city, zip_code, name)]


def browse_menu(
    conn: sqlite3.Connection,
    branch_id: str,
    category: str | None = None,
    q: str | None = None,
) -> list[dict]:
    known = {r["id"] for r in db.get_branches(conn)}
    v.validate_branch_id(branch_id, known)
    if category:
        category = v.clean_text(category, "category")
    if q:
        q = v.clean_text(q, "search")
    return db.get_menu(conn, branch_id, category, q)


def lookup_item(
    conn: sqlite3.Connection, branch_id: str, item_id: str, channel: str = "pickup"
) -> dict:
    """One exact item at one exact branch: price, nutrition, evidence."""
    known = {r["id"] for r in db.get_branches(conn)}
    v.validate_branch_id(branch_id, known)
    price = db.get_price(conn, branch_id, item_id, channel)
    nutrition = db.get_nutrition(conn, item_id)
    branch = db.get_branch(conn, branch_id)
    return {
        "branch": dict(branch) if branch else None,
        "price": price,            # None -> "not in our verified dataset"
        "nutrition": nutrition,    # None or calories None -> unavailable
        "channel": channel,
    }
