"""USA Restaurant Assistant — Streamlit pilot UI.

Views: Find food | Compare | Menu | Data status.
English UI. All numbers come from the verified SQLite database; nothing is
invented. Works fully without an LLM API key (structured filters + rule-based
chat intent); with a key, chat intent extraction gets smarter.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import assistant, comparison, database as db, search, validation as v

# --------------------------------------------------------------------------
# Theme (PRD section 12)
# --------------------------------------------------------------------------
st.set_page_config(page_title="USA Restaurant Assistant", layout="wide")
st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-family: system-ui, -apple-system, sans-serif; }
    .stApp { background-color: #F5F7FB; }
    .card { background: #FFFFFF; border-radius: 12px; padding: 16px;
            margin-bottom: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
    .price { color: #1353A4; font-size: 22px; font-weight: 700; }
    .badge-warn { color: #8A4B08; font-weight: 600; }
    .badge-err { color: #B42318; font-weight: 600; }
    .muted { color: #5b6472; font-size: 14px; }
    .stButton>button { background-color: #1353A4; color: white; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

TITLE = "USA Restaurant Assistant"


@st.cache_resource
def conn():
    c = db.get_connection()
    db.init_schema(c)
    from src import import_data
    want = (
        json.loads(import_data.REVIEWED_JSON.read_text(encoding="utf-8"))
        .get("_meta", {})
        .get("version", "")
    )
    have = None
    try:
        row = c.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()
        have = row["value"] if row else None
    except Exception:  # noqa: BLE001 - old DB without the meta table
        have = None
    if not db.get_branches(c) or have != want:
        # Fresh host, or menu.json was updated: (re)import the reviewed data.
        # Old prices stay as history (is_current=0); nothing is invented.
        c.close()
        import_data.import_reviewed()
        c = db.get_connection()
    return c


CONN = conn()
BRANCHES = [dict(r) for r in db.get_branches(CONN)]
BRANCH_IDS = {b["id"] for b in BRANCHES}
BRANCH_LABEL = {b["id"]: f"{b['restaurant_name']} — {b['address']}" for b in BRANCHES}

LLM_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
st.sidebar.title(TITLE)
view = st.sidebar.radio("View", ["Find food", "Compare", "Menu", "Data status"])
st.sidebar.markdown("---")
default_branch = st.sidebar.selectbox(
    "Branch", options=list(BRANCH_IDS),
    format_func=lambda i: BRANCH_LABEL[i], key="branch",
)
if LLM_KEY:
    st.sidebar.success("AI chat: available")
else:
    st.sidebar.info("AI chat: unavailable — filters below still work fully.")
if st.sidebar.button("Clear conversation"):
    for k in ("chat_history", "last_results"):
        st.session_state.pop(k, None)
    st.rerun()

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def result_card(row: dict):
    price = db.cents_to_str(row.get("price_cents"))
    cals = row.get("calories")
    cal_txt = f"{cals} cal" if cals is not None else "Calories unavailable"
    stale = " <span class='badge-warn'>[needs re-check: price may be stale]</span>" \
        if row.get("stale") else ""
    src = row.get("source_url") or "#"
    checked = row.get("price_checked_at") or "unknown date"
    st.markdown(
        f"""<div class="card">
        <div><strong>{row['name']}</strong> <span class="muted">({row.get('size') or ''})</span></div>
        <div class="price">{price}</div>
        <div class="muted">{cal_txt} · pickup · checked {checked}{stale}</div>
        <div><a href="{src}" target="_blank">View source</a></div>
        </div>""",
        unsafe_allow_html=True,
    )


def honest_empty(message: str):
    st.markdown(
        f"<div class='card'><span class='badge-err'>No verified options.</span>"
        f"<div class='muted'>{message}</div></div>",
        unsafe_allow_html=True,
    )


def run_find(branch_id: str, budget_cents: int | None, category: str | None,
             budget_meaning: str, query: str | None = None):
    """Shared search used by both filters and chat. Returns (eligible, excluded, notes)."""
    notes = []
    menu = search.browse_menu(CONN, branch_id, category=category or None, q=query)
    if not menu:
        return [], [], ["This branch has no verified menu records yet."]
    if budget_cents is None:
        eligible = [r for r in menu if not r.get("stale") and r.get("price_cents") is not None]
        excluded = [r for r in menu if r not in eligible]
        return eligible, excluded, notes
    eligible = comparison.filter_by_budget(menu, budget_cents)
    excluded = comparison.excluded_from_budget(menu, budget_cents)
    if budget_meaning == "total":
        notes.append(
            "Budget treated as food-only for matching: tax and fees are unknown, "
            "so a food-only match is not a guarantee the full checkout fits."
        )
    return eligible, excluded, notes


# --------------------------------------------------------------------------
# View: Find food
# --------------------------------------------------------------------------
if view == "Find food":
    st.header("Find food")
    col_f, col_c = st.columns([1, 2])

    with col_f:
        st.subheader("Filters")
        budget_raw = st.text_input("Food budget (USD)", value="", placeholder="e.g. 15")
        budget_meaning = st.radio("Budget means", ["food-only", "total"], horizontal=True)
        category = st.selectbox("Category", ["any", "pizza", "bread", "wings", "sides", "dessert", "drinks"])
        do_search = st.button("Find options")
        st.markdown("---")
        st.subheader("Ask in English")
        chat_q = st.chat_input("e.g. Find pizza under $15 in Detroit")

    with col_c:
        question = chat_q
        budget_cents = None
        cat = None if category == "any" else category
        if question:
            intent = assistant.extract_intent(question, api_key=LLM_KEY or None, model=LLM_MODEL or None)
            if intent.get("budget_cents"):
                budget_cents = intent["budget_cents"]
            if intent.get("category"):
                cat = intent["category"]
            if intent.get("missing"):
                st.warning(
                    "I need one more detail: "
                    + ", ".join(intent["missing"])
                    + ". (I never guess locations or branches.)"
                )
            if intent.get("correction"):
                st.warning(intent["correction"])
            if intent.get("clarification"):
                st.info(intent["clarification"])
            if not intent.get("ai_used"):
                st.caption("Rule-based understanding used (no AI key configured).")
        elif do_search or budget_raw:
            try:
                budget_cents = v.parse_budget_cents(budget_raw) if budget_raw.strip() else None
            except v.ValidationError as e:
                st.error(str(e))
                budget_cents = "invalid"

        if budget_cents != "invalid" and (do_search or question or budget_raw):
            eligible, excluded, notes = run_find(default_branch, budget_cents, cat, budget_meaning)
            for n in notes:
                st.info(n)
            if eligible:
                st.subheader(f"Matches within {db.cents_to_str(budget_cents) if budget_cents else 'menu'}")
                for row in eligible:
                    result_card(row)
            else:
                honest_empty(
                    "No verified options match this food-only budget at the selected branch. "
                    "Stale or unavailable prices are listed below, not hidden."
                )
            if excluded:
                with st.expander("Not included (with reasons)"):
                    for row in excluded:
                        reason = row.get("exclude_reason", "")
                        st.markdown(
                            f"<div class='card'><strong>{row['name']}</strong> "
                            f"<span class='muted'>— {reason}</span></div>",
                            unsafe_allow_html=True,
                        )

        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
        for role, msg in st.session_state.chat_history:
            with st.chat_message(role):
                st.write(msg)

# --------------------------------------------------------------------------
# View: Compare
# --------------------------------------------------------------------------
elif view == "Compare":
    st.header("Compare two options")
    st.caption("Fair comparison: size, serving and channel differences are shown, never hidden.")
    menu_a = search.browse_menu(CONN, default_branch)
    branch_b = st.selectbox("Second branch", options=list(BRANCH_IDS),
                            format_func=lambda i: BRANCH_LABEL[i], key="branch_b")
    menu_b = search.browse_menu(CONN, branch_b)

    c1, c2 = st.columns(2)
    with c1:
        item_a = st.selectbox("Option A", [r["id"] for r in menu_a],
                              format_func=lambda i: next(r["name"] for r in menu_a if r["id"] == i))
    with c2:
        item_b = st.selectbox("Option B", [r["id"] for r in menu_b],
                              format_func=lambda i: next(r["name"] for r in menu_b if r["id"] == i))
    if st.button("Compare"):
        a = next(r for r in menu_a if r["id"] == item_a)
        b = next(r for r in menu_b if r["id"] == item_b)
        res = comparison.compare_two(a, b)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**A — {BRANCH_LABEL[default_branch]}**")
            result_card(a)
        with col2:
            st.markdown(f"**B — {BRANCH_LABEL[branch_b]}**")
            result_card(b)
        if res["cheaper"] == "tie":
            st.info("Same pickup price.")
        elif res["cheaper"]:
            winner = "A" if res["cheaper"] == "a" else "B"
            st.success(f"Lower pickup price: option {winner} "
                       f"(difference {db.cents_to_str(res['diff_cents'])}).")
        for note in res["fairness_notes"]:
            st.warning(note)

# --------------------------------------------------------------------------
# View: Menu
# --------------------------------------------------------------------------
elif view == "Menu":
    st.header(f"Menu — {BRANCH_LABEL[default_branch]}")
    menu = search.browse_menu(CONN, default_branch)
    if not menu:
        honest_empty("No verified menu records for this branch yet. "
                     "That means 'not in our dataset', not 'sold out'.")
    else:
        for row in menu:
            result_card(row)

# --------------------------------------------------------------------------
# View: Data status
# --------------------------------------------------------------------------
else:
    st.header("Data status")
    st.caption("Every number shown in this app comes from a record below. "
               "No record = no claim.")
    for b in BRANCHES:
        menu = search.browse_menu(CONN, b["id"])
        fresh = sum(1 for r in menu if not r.get("stale") and r.get("price_cents") is not None)
        st.markdown(
            f"<div class='card'><strong>{BRANCH_LABEL[b['id']]}</strong>"
            f"<div class='muted'>{len(menu)} items · {fresh} with fresh prices</div></div>",
            unsafe_allow_html=True,
        )
    st.subheader("Sources")
    for s in db.get_sources(CONN):
        st.markdown(
            f"<div class='card'><a href='{s['url']}' target='_blank'>{s['url']}</a>"
            f"<div class='muted'>{s['type']} · checked {s['checked_at']} · {s['reviewer']}"
            f"{' · ' + s['note'] if s['note'] else ''}</div></div>",
            unsafe_allow_html=True,
        )
    st.subheader("How verification works")
    st.markdown(
        "- Prices are checked on the restaurant's official ordering menu, per branch.\n"
        "- A price older than 7 days is flagged and left out of budget ranking until re-checked.\n"
        "- Unknown price or calories are shown as unavailable, never guessed.\n"
        "- One branch's price is never shown as another branch's."
    )
