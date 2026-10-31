"""Budget extraction from free text: numeric, word-form, and invalid inputs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import validation as v


def test_dollar_form():
    assert v.extract_budget_from_text("Find pizza under $15 in Detroit.") == 1500


def test_under_without_dollar_sign():
    assert v.extract_budget_from_text("Find pizza under 15") == 1500


def test_word_form_dollars():
    # EV-18
    assert v.extract_budget_from_text("Find pizza under fifteen dollars in Detroit.") == 1500


def test_word_form_million():
    # EV-15: stated literally, no silent cap in free-text understanding
    assert v.extract_budget_from_text("I have a budget of one million dollars.") == 100_000_000


def test_negative_budget_rejected():
    # EV-14: never silently flip the sign
    assert v.extract_budget_from_text("Find pizza under -$10.") is None


def test_zero_budget_rejected():
    # EV-19: zero is not a usable budget; caller shows a correction prompt
    assert v.extract_budget_from_text("My budget is $0.") is None


def test_no_budget_present():
    assert v.extract_budget_from_text("Show me the menu") is None


def test_parse_budget_cents_still_guards_widget_input():
    # The structured budget widget keeps its sanity cap and zero rejection.
    import pytest
    with pytest.raises(v.ValidationError):
        v.parse_budget_cents("0")
    with pytest.raises(v.ValidationError):
        v.parse_budget_cents("99999999")
    assert v.parse_budget_cents("15") == 1500
