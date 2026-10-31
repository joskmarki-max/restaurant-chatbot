"""Reviewed-data import: data/reviewed/menu.json -> SQLite (PRD sections 8, 9).

- Human-reviewed JSON is the only input. Unreviewed data never goes live.
- Every row is validated; foreign keys enforced; import runs in one transaction.
- Invalid rows are reported and rejected; a failed import commits nothing.
- New prices become new snapshots; old snapshots stay as history (is_current=0).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db  # noqa: E402

REVIEWED_JSON = Path(__file__).resolve().parent.parent / "data" / "reviewed" / "menu.json"


class ImportError_(Exception):
    pass


def _req(obj: dict, key: str, where: str):
    if key not in obj or obj[key] is None or obj[key] == "":
        raise ImportError_(f"{where}: missing required field '{key}'")
    return obj[key]


def _cents(value, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ImportError_(f"{where}: cents must be a non-negative integer or null")
    return value


def import_reviewed(db_path: str | Path | None = None,
                    json_path: str | Path | None = None) -> dict:
    json_path = Path(json_path) if json_path else REVIEWED_JSON
    data = json.loads(json_path.read_text(encoding="utf-8"))

    conn = db.get_connection(db_path)
    db.init_schema(conn)
    report = {"inserted": 0, "rejected": [], "warnings": []}
    today = date.today().isoformat()

    try:
        cur = conn.cursor()
        # --- restaurants -------------------------------------------------
        for r in data.get("restaurants", []):
            rid = _req(r, "id", "restaurants")
            cur.execute(
                "INSERT OR REPLACE INTO restaurants(id,name,category,official_url)"
                " VALUES (?,?,?,?)",
                (rid, _req(r, "name", f"restaurant {rid}"),
                 r.get("category", "pizza"), r.get("official_url")),
            )
            report["inserted"] += 1
        # --- branches ----------------------------------------------------
        for b in data.get("branches", []):
            bid = _req(b, "id", "branches")
            cur.execute(
                """INSERT OR REPLACE INTO branches
                   (id,restaurant_id,address,city,state,zip,timezone,official_url)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (bid, _req(b, "restaurant_id", f"branch {bid}"),
                 _req(b, "address", f"branch {bid}"), _req(b, "city", f"branch {bid}"),
                 _req(b, "state", f"branch {bid}"), b.get("zip"),
                 b.get("timezone", "America/Chicago"), b.get("official_url")),
            )
            report["inserted"] += 1
        # --- menu items --------------------------------------------------
        for it in data.get("menu_items", []):
            iid = _req(it, "id", "menu_items")
            cur.execute(
                """INSERT OR REPLACE INTO menu_items
                   (id,restaurant_id,name,category,size,serving_basis)
                   VALUES (?,?,?,?,?,?)""",
                (iid, _req(it, "restaurant_id", f"item {iid}"),
                 _req(it, "name", f"item {iid}"), _req(it, "category", f"item {iid}"),
                 it.get("size"), it.get("serving_basis", "whole")),
            )
            report["inserted"] += 1
        # --- sources -----------------------------------------------------
        for s in data.get("sources", []):
            sid = _req(s, "id", "sources")
            cur.execute(
                """INSERT OR REPLACE INTO sources
                   (id,url,type,checked_at,reviewer,note) VALUES (?,?,?,?,?,?)""",
                (sid, _req(s, "url", f"source {sid}"),
                 _req(s, "type", f"source {sid}"),
                 s.get("checked_at", today), s.get("reviewer", "maintainer"),
                 s.get("note")),
            )
            report["inserted"] += 1
        # --- price snapshots (history preserved) -------------------------
        for p in data.get("price_snapshots", []):
            where = f"price {p.get('branch_id')}/{p.get('item_id')}"
            branch_id = _req(p, "branch_id", where)
            item_id = _req(p, "item_id", where)
            source_id = _req(p, "source_id", where)
            cents = _cents(p.get("cents"), where)
            channel = p.get("channel", "pickup")
            checked_at = p.get("checked_at", today)
            cur.execute(
                """UPDATE price_snapshots SET is_current = 0
                   WHERE branch_id = ? AND item_id = ? AND channel = ?
                     AND is_current = 1""",
                (branch_id, item_id, channel),
            )
            cur.execute(
                """INSERT INTO price_snapshots
                   (branch_id,item_id,channel,cents,source_id,checked_at,is_current)
                   VALUES (?,?,?,?,?,?,1)""",
                (branch_id, item_id, channel, cents, source_id, checked_at),
            )
            if db.is_stale(checked_at, db.PRICE_STALE_DAYS):
                report["warnings"].append(f"{where}: price is stale (>7 days)")
            report["inserted"] += 1
        # --- nutrition (NULL = unknown, never 0) --------------------------
        for n in data.get("nutrition", []):
            iid = _req(n, "item_id", "nutrition")
            cals = n.get("calories")
            if cals is not None and (not isinstance(cals, int) or cals < 0):
                raise ImportError_(f"nutrition {iid}: calories must be int >= 0 or null")
            cur.execute(
                """INSERT OR REPLACE INTO nutrition
                   (item_id,variant,calories,serving_basis,source_id,checked_at)
                   VALUES (?,?,?,?,?,?)""",
                (iid, n.get("variant", ""), cals,
                 n.get("serving_basis", "whole"), n.get("source_id"),
                 n.get("checked_at", today)),
            )
            report["inserted"] += 1
        # --- data version (lets the app auto re-import on updates) --------
        version = data.get("_meta", {}).get("version", "")
        cur.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES ('data_version', ?)",
            (version,),
        )
        conn.commit()
    except Exception as e:  # noqa: BLE001 - report, then roll back everything
        conn.rollback()
        report["rejected"].append(str(e))
        raise ImportError_(f"Import failed and was rolled back: {e}") from e
    finally:
        conn.close()
    return report


if __name__ == "__main__":
    rep = import_reviewed()
    print(f"inserted rows: {rep['inserted']}")
    for w in rep["warnings"]:
        print("warning:", w)
    for r in rep["rejected"]:
        print("rejected:", r)
