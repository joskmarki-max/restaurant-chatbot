"""Database layer: schema, connection, and parameterized queries.

Rules enforced here (see PRD sections 9 and 16):
- Money is stored as integer cents. Unknown price/calories are NULL, never 0.
- Every query is parameterized; user text is never concatenated into SQL.
- Branch isolation: a price snapshot always belongs to one exact branch.
- New prices are new snapshot rows; history is never silently overwritten.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS restaurants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'pizza',
    official_url TEXT
);

CREATE TABLE IF NOT EXISTS branches (
    id           TEXT PRIMARY KEY,
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    address      TEXT NOT NULL,
    city         TEXT NOT NULL,
    state        TEXT NOT NULL,
    zip          TEXT,
    timezone     TEXT NOT NULL DEFAULT 'America/Chicago',
    official_url TEXT
);

CREATE TABLE IF NOT EXISTS menu_items (
    id            TEXT PRIMARY KEY,
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    name          TEXT NOT NULL,
    category      TEXT NOT NULL,
    size          TEXT,
    serving_basis TEXT NOT NULL DEFAULT 'whole'
);

CREATE TABLE IF NOT EXISTS sources (
    id         TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    type       TEXT NOT NULL,          -- 'ordering_menu' | 'nutrition_pdf' | 'branch_page'
    checked_at TEXT NOT NULL,          -- ISO date
    reviewer   TEXT NOT NULL DEFAULT 'maintainer',
    note       TEXT
);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id  TEXT NOT NULL REFERENCES branches(id),
    item_id    TEXT NOT NULL REFERENCES menu_items(id),
    channel    TEXT NOT NULL DEFAULT 'pickup',   -- 'pickup' | 'delivery'
    cents      INTEGER,                            -- NULL = unknown price
    source_id  TEXT NOT NULL REFERENCES sources(id),
    checked_at TEXT NOT NULL,                      -- ISO date
    is_current INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_price_lookup
    ON price_snapshots(branch_id, item_id, channel, is_current);

CREATE TABLE IF NOT EXISTS nutrition (
    item_id       TEXT NOT NULL REFERENCES menu_items(id),
    variant       TEXT NOT NULL DEFAULT '',
    calories      INTEGER,                          -- NULL = unknown
    serving_basis TEXT NOT NULL DEFAULT 'whole',
    source_id     TEXT REFERENCES sources(id),
    checked_at    TEXT,
    PRIMARY KEY (item_id, variant)
);

CREATE TABLE IF NOT EXISTS modifiers (
    id           TEXT PRIMARY KEY,
    item_id      TEXT REFERENCES menu_items(id),
    branch_id    TEXT REFERENCES branches(id),      -- NULL = all branches of the item's restaurant
    name         TEXT NOT NULL,
    charge_cents INTEGER,                           -- NULL = unknown charge
    rule         TEXT
);

CREATE TABLE IF NOT EXISTS offers (
    id           TEXT PRIMARY KEY,
    restaurant_id TEXT NOT NULL REFERENCES restaurants(id),
    title        TEXT NOT NULL,
    terms        TEXT,
    source_id    TEXT REFERENCES sources(id),
    active_from  TEXT,
    active_to    TEXT,                               -- NULL/empty = expiry unknown
    checked_at   TEXT
);

CREATE TABLE IF NOT EXISTS offer_branches (
    offer_id  TEXT NOT NULL REFERENCES offers(id),
    branch_id TEXT NOT NULL REFERENCES branches(id),
    PRIMARY KEY (offer_id, branch_id)
);
"""

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "restaurant.db"

# Freshness thresholds (PRD section 8): internal review limits.
PRICE_STALE_DAYS = 7
NUTRITION_STALE_DAYS = 30


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: Streamlit runs the script in different threads
    # while reusing the cached connection. Writes only happen in import_data
    # (a separate process), so this is safe for the pilot.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_stale(checked_at: str | None, days: int) -> bool:
    """True when a record is older than the freshness threshold, or undated."""
    if not checked_at:
        return True
    try:
        checked = datetime.fromisoformat(checked_at).date()
    except ValueError:
        return True
    return (date.today() - checked).days > days


def cents_to_str(cents: int | None) -> str:
    if cents is None:
        return "Unavailable"
    return f"${cents / 100:.2f}"


# ---------------------------------------------------------------------------
# Approved read queries. All parameterized. The LLM layer may only call these.
# ---------------------------------------------------------------------------

def get_restaurants(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM restaurants ORDER BY name").fetchall()


def get_branches(
    conn: sqlite3.Connection,
    city: str | None = None,
    zip_code: str | None = None,
    name: str | None = None,
) -> list[sqlite3.Row]:
    """Find covered branches. Never invents nearby branches."""
    sql = """
        SELECT b.*, r.name AS restaurant_name
        FROM branches b JOIN restaurants r ON r.id = b.restaurant_id
        WHERE 1 = 1
    """
    params: list = []
    if city:
        sql += " AND lower(b.city) LIKE '%' || lower(?) || '%'"
        params.append(city.strip()[:60])
    if zip_code:
        sql += " AND b.zip = ?"
        params.append(zip_code.strip()[:10])
    if name:
        sql += " AND lower(r.name) LIKE '%' || lower(?) || '%'"
        params.append(name.strip()[:60])
    sql += " ORDER BY b.city, b.address LIMIT 50"
    return conn.execute(sql, params).fetchall()


def get_branch(conn: sqlite3.Connection, branch_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT b.*, r.name AS restaurant_name
        FROM branches b JOIN restaurants r ON r.id = b.restaurant_id
        WHERE b.id = ?
        """,
        (branch_id,),
    ).fetchone()


def get_menu(
    conn: sqlite3.Connection,
    branch_id: str,
    category: str | None = None,
    q: str | None = None,
) -> list[dict]:
    """Branch menu with latest current pickup price + nutrition. Branch-isolated."""
    sql = """
        SELECT mi.id, mi.name, mi.category, mi.size, mi.serving_basis,
               ps.cents AS price_cents, ps.checked_at AS price_checked_at,
               s.url AS source_url,
               n.calories, n.serving_basis AS cal_basis
        FROM menu_items mi
        LEFT JOIN price_snapshots ps
               ON ps.item_id = mi.id AND ps.branch_id = ? AND ps.channel = 'pickup'
              AND ps.is_current = 1
        LEFT JOIN sources s ON s.id = ps.source_id
        LEFT JOIN nutrition n ON n.item_id = mi.id
        WHERE mi.restaurant_id = (SELECT restaurant_id FROM branches WHERE id = ?)
    """
    params: list = [branch_id, branch_id]
    if category:
        sql += " AND lower(mi.category) = lower(?)"
        params.append(category.strip()[:40])
    if q:
        sql += " AND lower(mi.name) LIKE '%' || lower(?) || '%'"
        params.append(q.strip()[:60])
    sql += " ORDER BY mi.category, mi.name"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["stale"] = is_stale(d["price_checked_at"], PRICE_STALE_DAYS)
        out.append(d)
    return out


def get_price(
    conn: sqlite3.Connection, branch_id: str, item_id: str, channel: str = "pickup"
) -> dict | None:
    """Latest current price snapshot for one exact branch/item/channel."""
    row = conn.execute(
        """
        SELECT ps.cents, ps.checked_at, s.url AS source_url,
               mi.name AS item_name, mi.size, b.address AS branch_address
        FROM price_snapshots ps
        JOIN menu_items mi ON mi.id = ps.item_id
        JOIN branches b ON b.id = ps.branch_id
        LEFT JOIN sources s ON s.id = ps.source_id
        WHERE ps.branch_id = ? AND ps.item_id = ? AND ps.channel = ?
          AND ps.is_current = 1
        ORDER BY ps.checked_at DESC LIMIT 1
        """,
        (branch_id, item_id, channel),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["stale"] = is_stale(d["checked_at"], PRICE_STALE_DAYS)
    return d


def get_nutrition(conn: sqlite3.Connection, item_id: str) -> dict | None:
    row = conn.execute(
        "SELECT calories, serving_basis, checked_at FROM nutrition WHERE item_id = ?",
        (item_id,),
    ).fetchone()
    return dict(row) if row else None


def get_sources(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM sources ORDER BY checked_at DESC").fetchall()


def get_modifiers(
    conn: sqlite3.Connection, item_id: str, branch_id: str | None = None
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM modifiers WHERE item_id = ? AND (branch_id IS NULL"
    params: list = [item_id]
    if branch_id:
        sql += " OR branch_id = ?"
        params.append(branch_id)
    sql += ")"
    return conn.execute(sql, params).fetchall()
