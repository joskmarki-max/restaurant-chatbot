"""Input validation. Invalid input never reaches a query (PRD sections 10, 16)."""

from __future__ import annotations

import math
import re

MAX_TEXT_LEN = 120
MAX_BUDGET_CENTS = 10_000_00  # $10,000 sanity cap


class ValidationError(ValueError):
    pass


# --- word-form numbers: "fifteen dollars", "one million dollars" ---

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}

_NUM_WORD_ALTS = "|".join(
    sorted(set(_NUMBER_WORDS) | set(_SCALE_WORDS), key=len, reverse=True)
)
_WORD_BUDGET_RE = re.compile(
    rf"\b((?:{_NUM_WORD_ALTS})(?:\s+(?:{_NUM_WORD_ALTS}))*)\s+dollars?\b",
    re.IGNORECASE,
)


def _words_to_dollars(phrase: str) -> int:
    """'one million' -> 1000000, 'fifteen' -> 15. Unknown words contribute 0."""
    total, current = 0, 0
    for w in phrase.lower().split():
        if w in _NUMBER_WORDS:
            current += _NUMBER_WORDS[w]
        elif w in _SCALE_WORDS:
            current *= _SCALE_WORDS[w]
            if _SCALE_WORDS[w] >= 1000:
                total += current
                current = 0
    return total + current


def clean_text(value: str | None, field: str = "input") -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text.")
    value = value.strip()
    if not value:
        raise ValidationError(f"{field} is empty.")
    if len(value) > MAX_TEXT_LEN:
        raise ValidationError(f"{field} is too long.")
    return value


def parse_budget_cents(raw: str | float | int | None) -> int:
    """Parse a USD budget into integer cents.

    Accepts '15', '$15', '15.50'. Rejects negative, zero, NaN, infinity,
    non-numeric and unreasonably large values. A budget exactly equal to an
    item price IS a valid match (boundary inclusive).
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValidationError("Please enter a budget, for example 15.")
    if isinstance(raw, bool):
        raise ValidationError("Budget must be a number.")
    if isinstance(raw, (int, float)):
        amount = float(raw)
    else:
        text = raw.strip().replace("$", "").replace(",", "")
        if not re.fullmatch(r"\d+(\.\d{1,2})?", text):
            raise ValidationError(
                f"'{raw.strip()[:20]}' is not a valid USD amount. Try like 15 or 12.50."
            )
        amount = float(text)
    if not math.isfinite(amount):
        raise ValidationError("Budget must be a finite number.")
    if amount <= 0:
        raise ValidationError("Budget must be more than $0.")
    cents = int(round(amount * 100))
    if cents > MAX_BUDGET_CENTS:
        raise ValidationError("That budget looks unrealistically large. Try a smaller amount.")
    return cents


def validate_branch_id(branch_id: str | None, known_ids: set[str]) -> str:
    """Branch IDs must come from the allowlist of covered branches."""
    bid = clean_text(branch_id, "branch")
    if bid not in known_ids:
        raise ValidationError("That branch is not in our covered list.")
    return bid


def extract_budget_from_text(text: str) -> int | None:
    """Best-effort budget extraction for chat input. Returns None if absent.

    Understands '$15', 'under 15', and word forms like 'fifteen dollars' or
    'one million dollars'. Returns the stated amount literally in cents:
    the $10,000 sanity cap lives in parse_budget_cents (structured widget
    input and LLM output), not in free-text understanding. Explicit negative
    ('-$10') and zero ('$0') budgets are rejected as None — callers surface a
    correction prompt for those instead of silently flipping the sign.
    """
    if re.search(r"-\s*\$", text) or re.search(r"\bunder\s+-\s*\$?\d", text, re.IGNORECASE):
        return None  # explicit negative budget: reject, never flip sign
    m = _WORD_BUDGET_RE.search(text)
    if m:
        dollars = _words_to_dollars(m.group(1))
        return dollars * 100 if dollars > 0 else None
    for pattern in (r"\$\s?(\d+(?:\.\d{1,2})?)", r"\bunder\s+\$?(\d+(?:\.\d{1,2})?)"):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            amount = float(m.group(1))
            if amount <= 0:
                return None
            return int(round(amount * 100))
    return None
