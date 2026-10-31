# Design memory (PRD section 20)

Written history of decisions: date, reason, affected files, validation.
New sessions must verify code state against this file before changing scope.

## 2026-10-30 — Initial build

- **Stack**: Python + Streamlit + SQLite (sqlite3) + pytest, per PRD section 7.
  PostgreSQL/FastAPI/React deferred to a future public release; they are not
  needed for the pilot and would only add complexity.
- **Pilot branch**: Little Caesars Detroit (530 East Warren, store #40) is the
  seeded branch because its 15 pickup prices were verified on the official
  ordering menu (2026-10-09). Houston (store #811) was the proposed pilot city;
  its branch record exists and a fresh price check is running — the app shows
  honest "no verified records yet" for Houston until that lands. Reason: the
  PRD allows branch selection to follow reliable data (section 2, scope change).
- **Money**: integer cents everywhere; NULL for unknown. Affects: database.py,
  comparison.py, import_data.py. Validated by tests/test_money.py.
- **Freshness**: 7 days for prices, 30 for nutrition (PRD section 8). Stale
  prices are flagged in the UI and excluded from budget ranking. Seed prices
  from 2026-10-09 are therefore shown stale until the re-check completes.
- **LLM**: provider undecided, so the build is key-optional. Rule-based intent
  always works; `_llm_intent` activates only with `LLM_API_KEY` + `openai`
  package, and its output is re-validated (never trusted blindly). Affects:
  src/assistant.py, app.py sidebar status.
- **Branch isolation**: enforced in SQL (price_snapshots always carry branch_id)
  and tested (tests/test_search.py::test_branch_isolation).
- **No checkout**: the app has a "View source" link per result and no Order
  button, per PRD section 12 (no fake ordering impression).
- **Second chain**: Domino's pending source verification; restaurant record not
  seeded until branch + prices are verified. Not a code gap — a data gap.

## 2026-10-30 — Price refresh (both pilot branches)

- **Detroit #40 re-checked** on the official ordering menu: 23 items.
  Two real price changes vs 2026-10-09: Classic Cheese $5.49 -> $6.49,
  EMB Pepperoni $8.49 -> $7.49. Old snapshots kept as history (is_current=0).
- **Houston #811 first verified**: branch address confirmed from the official
  store page as 2603 Fulton St Suite A, Houston, TX 77009. 23 pickup prices
  recorded. Branch isolation now demonstrable: Classic Cheese $6.49 (Detroit)
  vs $5.99 (Houston); EMB $7.49 vs $6.99.
- **Pretzel gap closed**: 8 pretzel-crust variants added with live-menu calories
  (1,830–2,660), resolving the earlier PDF-ambiguity nulls for these items.
- Calories identical across both stores for the same items; only prices differ.
- Affects: data/reviewed/menu.json (v2026-10-30-refresh). Validated by
  tests/test_search.py (branch isolation) — 22/22 pass.

## 2026-10-30 — Streamlit thread fix

- **Bug**: `sqlite3.ProgrammingError` on first app run — the cached connection
  was created in one thread and used in another (Streamlit script runner).
- **Fix**: `sqlite3.connect(..., check_same_thread=False)` in
  `src/database.py::get_connection`. Safe for the pilot: the app only reads;
  writes happen in the separate `import_data` process. Verified with a
  cross-thread read test; 22/22 pytest still pass.

## 2026-10-30 — Top-5 expansion (Taco Bell + Wendy's added)

- **Taco Bell** (Houston, 2093 Taylor Street, TX 77007, store 027807): 15 items
  with prices + calories from tacobell.com official per-store menu.
- **Wendy's** (Houston, 210 Patton Street, TX 77009): 15 items with prices +
  calories from order.wendys.com official carryout menu. Coca-Cola kept NULL
  (price $3.09–$3.89 and calories 180–320 vary by size — never guessed).
- **McDonald's NOT added**: mcdonalds.com publishes no per-restaurant prices
  (menu pages show items + calories only; ordering is app-only). Third-party
  prices rejected per the official-source-only rule.
- **Domino's NOT added**: dominos.com withholds all menu prices from automated
  browsing (bot mitigation confirmed after retries); store 1910 W 18th St,
  Houston TX 77008 was verified as the branch but no prices could be read.
  Affects: data/reviewed/menu.json (v2026-10-30-top5). 22/22 pytest pass.

## 2026-10-31 — §18 evaluation baseline (first run)

- Refreshed tests/eval_cases.json expected behaviours to the fresh 2026-10-30
  dataset (14 cases had stale $5.49/NULL/stale expectations).
- New runner: tests/run_eval.py — builds a throwaway DB from the reviewed seed,
  executes all 40 cases through the real src/ functions, writes
  reports/eval-baseline-<date>.json.
- Baseline 2026-10-31: **31/40 pass, 7 fail, 2 skipped (EV-36/37 need LLM key),
  zero critical failures.** All 10 critical cases pass (branch isolation,
  provenance, injection safety, honest empty states).
- The 7 failures are all NL-understanding gaps, none in data/correctness:
  EV-04 ('pepperoni price?' phrasing not caught by item_price trigger),
  EV-14 (-$10 silently treated as $10), EV-15/EV-18 (word-form budgets),
  EV-16 (no per-query food-only vs total clarification), EV-19 ($0 silent in chat),
  EV-25 ('better value' -> unknown). This is the Phase-5 fix list.
- Known data gap (not a code bug): historical price snapshots (is_current=0 rows)
  were never seeded, so EV-32 checks current-price correctness only.

## 2026-10-31 — Evaluation fixes (Phase 5): 31/40 -> 38/40, release gate MET

- **Baseline** (morning): 31/40 pass, 7 fail, 2 skipped (EV-36/37 need LLM key),
  zero critical failures. Old report preserved at
  reports/eval-baseline-2026-10-31-pre-fix.json ("baseline -> fixes -> re-run"
  story for the report).
- **Fixes** — all in the rule path, no data changes:
  - EV-04: item_price trigger broadened — "X price?" / "cost" phrasing now
    detected; item name extracted from the trailing-"price?" form. Missing
    branch still flagged (never guessed).
  - EV-14: explicit negative budgets ("-$10") rejected as None — the sign is
    never silently flipped.
  - EV-15/EV-18: word-form budgets parsed ("fifteen dollars", "one million
    dollars") via a small number-word parser. Free-text extraction returns the
    stated amount literally; the $10,000 sanity cap stays in parse_budget_cents
    (structured widget input + LLM-output gate), not in chat understanding.
  - EV-16 (doc Journey A): budget + scope-ambiguous words ("total", "dinner",
    "delivery", "checkout", "including", "tax") now returns a short
    clarification question ("is $15 for food only, or your total including tax
    and delivery?") instead of a silent food-only assumption.
  - EV-19: a stated "$0" budget returns a visible correction prompt via the new
    `correction` field — never a silent unfiltered menu.
  - EV-25 (doc Journey C): "better value" -> compare intent + "value criterion"
    in missing + clarification asking cheapest vs most-food-per-dollar. No
    value conclusion without an agreed criterion.
- **Intent dict** gained two optional fields: `clarification` (question string)
  and `correction` (correction string); app.py renders both in the chat column.
- **Runner**: EV-16/EV-19 checks were hardcoded `ok=False` stubs documenting the
  gaps; rewritten to verify the new behavior (no stubbed outcomes remain).
- **Tests**: 12 new (4 assistant incl. criterion/clarification/correction cases,
  8 validation incl. widget-cap guard) — **34/34 pass**.
- **Result**: **38/40 pass, 0 fail, 2 skipped** (EV-36/37 need LLM_API_KEY);
  all 10 critical pass; release gate (>=36/40, all critical) **MET**.
  Report: reports/eval-baseline-2026-10-31.json.
- Affects: src/assistant.py, src/validation.py, app.py, tests/run_eval.py,
  tests/test_assistant.py, tests/test_validation.py (new), docs/DESIGN-MEMORY.md.
  Validated by: pytest 34/34 + tests/run_eval.py 38/40.

## 2026-10-31 — Hosting-ready + auto data updates

- Hosting: app.py auto-seeds SQLite from data/reviewed/menu.json on first run
  (fresh host needs no manual import). requirements.txt adds openai (optional,
  for LLM_API_KEY). New DEPLOY.md: free Streamlit Community Cloud steps
  (GitHub repo -> deploy). .gitignore: added .pytest_cache/, .streamlit/secrets.toml.
- Auto updates: menu.json `_meta.version` stored in new `meta` table on import;
  app.py re-imports automatically when the version changes. Verified: fresh ->
  import; restart same data -> no import; version bump -> re-import (history kept).
  DEPLOY.md "Adding more data later": edit menu.json -> bump version ->
  restart app (laptop) or git push (hosted; Cloud reboots on push).
- Pending on user: GitHub account + deploy click (needs his login; can't be done for him).

## Open decisions

- Exact pilot branches (Houston refresh will decide)
- Supported ZIP list
- LLM provider / model / usage budget
- Final product name ("USA Restaurant Assistant" is the working name)
- Hosting (local demo first, per PRD)
