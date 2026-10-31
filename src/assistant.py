"""Language layer: natural-language query -> structured intent (PRD section 11).

Two paths, same database and rules:
- LLM path (optional): constrained JSON intent extraction. Read-only; the model
  never sees raw SQL and never writes. Any schema failure -> rule fallback.
- Rule path (always available): keyword/regex intent parsing. Powers the app
  fully when no API key is configured.

Numbers and cards are always rendered from database records by app.py;
the model never invents prices, calories, or branches.
"""

from __future__ import annotations

import json
import re

from . import validation as v

INTENTS = {"budget_search", "item_price", "compare", "menu_browse", "unknown"}

CATEGORY_WORDS = {
    "pizza": ["pizza", "pizzas"],
    "bread": ["bread", "breadstick", "cheese bread", "crazy bread"],
    "wings": ["wing", "wings"],
    "sides": ["side", "sides", "puff", "puffs"],
    "dessert": ["dessert", "brownie", "cookie"],
    "drinks": ["drink", "drinks", "pepsi", "soda"],
}

CITY_WORDS = ["houston", "detroit", "chicago", "new york", "dallas", "austin"]

INTENT_SCHEMA_HINT = """Reply with JSON only, exactly these keys:
{"intent": "budget_search|item_price|compare|menu_browse|unknown",
 "city": string or null, "restaurant_name": string or null,
 "category": string or null, "item_name": string or null,
 "budget_cents": integer or null}"""


def _rule_intent(text: str) -> dict:
    t = text.lower()
    out = {
        "intent": "unknown",
        "city": None,
        "restaurant_name": None,
        "category": None,
        "item_name": None,
        "budget_cents": None,
        "missing": [],
        "clarification": None,
        "correction": None,
        "ai_used": False,
    }
    budget = v.extract_budget_from_text(text)
    if budget is not None:
        out["budget_cents"] = budget
    for city in CITY_WORDS:
        if city in t:
            out["city"] = city.title()
            break
    for cat, words in CATEGORY_WORDS.items():
        if any(w in t for w in words):
            out["category"] = cat
            break
    if "little caesars" in t or "little caesar" in t:
        out["restaurant_name"] = "Little Caesars"
    elif "domino" in t:
        out["restaurant_name"] = "Domino's"
    if re.search(r"\b(better|best)\s+value\b", t):
        # Journey C: no "better value" conclusion without an agreed criterion —
        # ask what the user means instead of guessing.
        out["intent"] = "compare"
        out["clarification"] = (
            "When you say 'better value', do you mean the cheapest option, "
            "or the most food for the money?"
        )
        out["missing"].append("value criterion")
    elif budget is not None:
        out["intent"] = "budget_search"
    elif "compare" in t or " vs " in t or "versus" in t:
        out["intent"] = "compare"
    elif any(w in t for w in ["how much", "price of", "cost of", "price for"]) \
            or re.search(r"\bprice\b|\bcost\b", t):
        out["intent"] = "item_price"
        m = re.search(r"(?:price of|cost of|price for|how much is|how much for)\s+(?:a|an|the)?\s*([a-z\s]+?)(?:\?|$| at | in )", t)
        if not m:
            m = re.search(r"([a-z][a-z\s\-]{1,50}?)\s+prices?\s*\??$", t)
        if m:
            out["item_name"] = m.group(1).strip()[:60] or None
    elif "menu" in t or "show" in t or "list" in t:
        out["intent"] = "menu_browse"

    # Journey A: a budget whose scope is unclear (food-only vs checkout total)
    # gets a short clarification question instead of a silent assumption.
    if out["intent"] == "budget_search" and out["budget_cents"] and \
            re.search(r"\b(total|dinner|delivery|checkout|including|tax|taxes)\b", t):
        amt = out["budget_cents"]
        amt_s = f"${amt // 100}" if amt % 100 == 0 else f"${amt / 100:.2f}"
        out["clarification"] = (
            f"Just to confirm: is {amt_s} for food only, "
            "or your total including tax and delivery?"
        )

    # A stated-but-invalid budget ($0) gets a visible correction prompt —
    # never a silent unfiltered menu.
    if out["budget_cents"] is None and re.search(r"\$\s*0+(\.0+)?\b", t):
        out["correction"] = (
            "A budget of $0 can't match anything — budgets need to be more "
            "than $0. What budget should I search with?"
        )

    # Missing essential fields per journey rules (PRD section 5).
    if out["intent"] == "budget_search" and not out["city"]:
        out["missing"].append("city")
    if out["intent"] in {"item_price", "menu_browse", "compare"} and not out["restaurant_name"]:
        out["missing"].append("restaurant or branch")
    return out


def _llm_intent(text: str, api_key: str, model: str) -> dict | None:
    """Constrained LLM extraction. Returns None on any failure."""
    try:
        from openai import OpenAI  # lazy: optional dependency
    except ImportError:
        return None
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model or "gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "Extract restaurant-search intent as JSON. Never invent "
                            "prices, branches, or calories. " + INTENT_SCHEMA_HINT},
                {"role": "user", "content": text[:500]},
            ],
            temperature=0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return None
    if data.get("intent") not in INTENTS:
        return None
    out = {
        "intent": data.get("intent"),
        "city": data.get("city"),
        "restaurant_name": data.get("restaurant_name"),
        "category": data.get("category"),
        "item_name": data.get("item_name"),
        "budget_cents": data.get("budget_cents"),
        "missing": [],
        "clarification": None,
        "correction": None,
        "ai_used": True,
    }
    # Independent validation: model output is never trusted blindly.
    try:
        if out["budget_cents"] is not None:
            out["budget_cents"] = v.parse_budget_cents(out["budget_cents"])
    except v.ValidationError:
        out["budget_cents"] = None
    for key in ("city", "restaurant_name", "category", "item_name"):
        if out[key] is not None:
            try:
                out[key] = v.clean_text(str(out[key]), key)
            except v.ValidationError:
                out[key] = None
    return out


def extract_intent(
    text: str, api_key: str | None = None, model: str | None = None
) -> dict:
    """Public entry. Always returns a validated intent dict; never raises."""
    try:
        text = v.clean_text(text, "question")
    except v.ValidationError as e:
        return {"intent": "unknown", "missing": [], "ai_used": False,
                "error": str(e), "city": None, "restaurant_name": None,
                "category": None, "item_name": None, "budget_cents": None,
                "clarification": None, "correction": None}
    if api_key:
        llm = _llm_intent(text, api_key, model or "")
        if llm:
            return llm
    result = _rule_intent(text)
    result["ai_used"] = False
    return result
