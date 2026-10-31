"""Language layer: rule-based intent works with no API key; LLM never trusted blindly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import assistant


def test_rule_budget_intent():
    out = assistant.extract_intent("Find pizza under $15 in Houston")
    assert out["intent"] == "budget_search"
    assert out["budget_cents"] == 1500
    assert out["city"] == "Houston"
    assert out["category"] == "pizza"
    assert out["ai_used"] is False


def test_rule_item_price_intent():
    out = assistant.extract_intent("How much is a cheese pizza at Little Caesars?")
    assert out["intent"] == "item_price"
    assert out["restaurant_name"] == "Little Caesars"


def test_missing_city_flagged():
    out = assistant.extract_intent("Find pizza under $15")
    assert "city" in out["missing"]


def test_no_key_no_crash_no_invention():
    out = assistant.extract_intent("Find pizza under $15 in Houston", api_key=None)
    assert out["ai_used"] is False
    assert out["budget_cents"] == 1500  # from text, not invented


def test_empty_question_safe():
    out = assistant.extract_intent("   ")
    assert out["intent"] == "unknown"
    assert "error" in out


def test_item_price_question_form():
    # EV-04: "Thin crust pepperoni price?" -> item_price, branch still missing
    out = assistant.extract_intent("Thin crust pepperoni price?")
    assert out["intent"] == "item_price"
    assert "restaurant or branch" in out["missing"]


def test_budget_scope_clarification():
    # EV-16 / doc Journey A: "total" makes food-only vs total unclear
    out = assistant.extract_intent("I have $15 total for dinner tonight.")
    assert out["intent"] == "budget_search"
    assert out["budget_cents"] == 1500
    assert out["clarification"]  # short clarification question, no silent default


def test_zero_budget_correction_prompt():
    # EV-19: $0 is rejected with a visible correction, not a silent menu
    out = assistant.extract_intent("My budget is $0.")
    assert out["budget_cents"] is None
    assert "$0" in (out["correction"] or "")


def test_better_value_asks_criterion():
    # EV-25 / doc Journey C: "better value" needs an agreed criterion
    import json
    out = assistant.extract_intent("Which is better value, the wings or the pizza?")
    assert "criterion" in json.dumps(out).lower()
    assert out["clarification"]
