"""Budget filtering and fair comparison. Pure Python, integer cents (PRD section 10).

Fairness rules:
- Only eligible records compete: known price, not stale, same channel.
- Per-slice prices are never ranked against whole-pizza prices.
- Size/serving/channel mismatches are explained, never hidden.
- Ties keep a stable order; no invented "best" without a stated criterion.
"""

from __future__ import annotations


def _eligible(row: dict) -> bool:
    return (
        row.get("price_cents") is not None
        and not row.get("stale", True)
    )


def filter_by_budget(menu_rows: list[dict], budget_cents: int) -> list[dict]:
    """Items whose food-only pickup price fits the budget, cheapest first.

    Budget exactly equal to the price counts as a match (boundary inclusive).
    Stale or unknown prices are excluded and reported separately.
    """
    eligible, excluded = [], []
    for row in menu_rows:
        if _eligible(row) and row["price_cents"] <= budget_cents:
            eligible.append(row)
        elif row.get("price_cents") is not None:
            excluded.append(row)
    eligible.sort(key=lambda r: (r["price_cents"], r["name"]))
    return eligible


def excluded_from_budget(menu_rows: list[dict], budget_cents: int) -> list[dict]:
    """Rows left out of a budget result, with the reason attached."""
    out = []
    for row in menu_rows:
        if row.get("price_cents") is None:
            out.append({**row, "exclude_reason": "price unavailable"})
        elif row.get("stale"):
            out.append({**row, "exclude_reason": "price needs re-check (stale)"})
        elif row["price_cents"] > budget_cents:
            out.append({**row, "exclude_reason": "over budget"})
    return out


def compare_two(a: dict, b: dict) -> dict:
    """Compare two menu rows. Returns the verdict plus fairness notes."""
    notes: list[str] = []
    if a.get("serving_basis") != b.get("serving_basis"):
        notes.append(
            f"Serving differs ({a.get('serving_basis')} vs {b.get('serving_basis')}); "
            "per-serving value cannot be ranked directly."
        )
    if (a.get("size") or "").lower() != (b.get("size") or "").lower():
        notes.append(f"Size differs ({a.get('size')} vs {b.get('size')}).")
    price_a, price_b = a.get("price_cents"), b.get("price_cents")
    cheaper = None
    diff_cents = None
    if price_a is not None and price_b is not None:
        diff_cents = abs(price_a - price_b)
        if price_a < price_b:
            cheaper = "a"
        elif price_b < price_a:
            cheaper = "b"
        else:
            cheaper = "tie"
    else:
        notes.append("One or both prices are unavailable, so no price winner.")
    return {
        "a": a,
        "b": b,
        "cheaper": cheaper,          # 'a' | 'b' | 'tie' | None
        "diff_cents": diff_cents,
        "fairness_notes": notes,
    }


def total_with_extras(
    base_cents: int,
    extras_cents: list[int | None],
    discount_cents: int = 0,
) -> int | None:
    """Base + verified extras - verified discount. Unknown extra -> total unknown."""
    if base_cents is None:
        return None
    if any(e is None for e in extras_cents):
        return None  # unknown mandatory charge: no false total
    return base_cents + sum(e for e in extras_cents if e) - discount_cents
