# USA Restaurant Assistant — pilot

English chatbot (Streamlit) that answers menu, price, calorie and comparison
questions for **one exact restaurant branch at a time**, using only verified
records. Prices are never invented; unknown values are shown as unavailable.

## Quick start (Windows)

```bat
cd C:\Users\mauza\restaurant-chatbot
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m src.import_data
python -m streamlit run app.py
```

Then open the URL Streamlit prints (usually http://localhost:8501).

macOS / Linux:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.import_data
python -m streamlit run app.py
```

## Optional: AI chat

The app works fully **without** any API key (filters + rule-based chat).
To enable smarter chat intent extraction:

1. Copy `.env.example` to `.env`
2. Put your key in `LLM_API_KEY=` (never commit `.env`, never paste keys in chat)

## Run tests

```bash
python -m pytest tests/ -q
```

## Project layout

| Path | Purpose |
| --- | --- |
| `app.py` | Streamlit UI: Find food, Compare, Menu, Data status |
| `src/database.py` | SQLite schema + parameterized queries (branch-isolated) |
| `src/validation.py` | Budget/branch/input checks; invalid input never reaches a query |
| `src/search.py` | Approved read functions (the only data access for UI and AI) |
| `src/comparison.py` | Budget filter + fair comparison, integer cents |
| `src/assistant.py` | LLM intent (optional) + rule-based fallback |
| `src/import_data.py` | Reviewed JSON -> SQLite import, validated, transactional |
| `data/reviewed/menu.json` | Human-reviewed seed records (the only import input) |
| `data/evidence/` | Source metadata notes |
| `data/restaurant.db` | Generated database (not committed) |
| `tests/` | pytest suite: money, search, comparison, assistant |
| `docs/DESIGN-MEMORY.md` | Decision log |

## Data honesty rules (non-negotiable)

- Money stored as integer cents; unknown price/calories = NULL, never 0.
- A price belongs to one exact branch + channel. Detroit prices are never
  shown as Houston prices.
- Prices older than 7 days are flagged stale and excluded from budget ranking
  until a human re-checks them.
- New prices are new snapshots; history is preserved.
- The model gets read-only allowlisted functions only. No raw SQL for the LLM.

## Current pilot data (2026-10-30)

- Little Caesars, Detroit — 530 East Warren, Detroit, MI 48201 (store #40):
  23 items, pickup prices re-checked 2026-10-30 on the official ordering menu.
  Changes vs 2026-10-09: Classic Cheese $5.49 -> $6.49, EMB Pepperoni $8.49 -> $7.49.
- Little Caesars, Houston — 2603 Fulton St Suite A, Houston, TX 77009 (store #811):
  23 items, pickup prices first verified 2026-10-30. Branch isolation in action:
  Classic Cheese is $6.49 in Detroit vs $5.99 in Houston.
- 8 pretzel-crust variants added with live-menu calories (1,830–2,660).
- Taco Bell, Houston — 2093 Taylor Street, Houston, TX 77007 (store 027807):
  15 items with prices + calories, verified 2026-10-30 on tacobell.com.
- Wendy's, Houston — 210 Patton Street, Houston, TX 77009:
  15 items with prices + calories, verified 2026-10-30 on order.wendys.com.
  (Coca-Cola price/calories vary by size: shown as unavailable, never guessed.)
- NOT added: McDonald's (official website publishes no prices — app-only);
  Domino's (official site withholds prices from automated browsing — bot wall).
