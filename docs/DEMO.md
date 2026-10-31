# Demo script (5 minutes)

1. **Data status view** — show the two branches and the sources table. Point out:
   every price has a source link and a checked date.
2. **Menu view** (Detroit branch) — scroll the 15 items. Note the stale badge:
   prices verified 2026-10-09 are flagged until re-checked.
3. **Find food** — set budget 10, food-only. Show the honest empty state +
   the "Not included (with reasons)" list. Explain: stale prices are excluded
   from ranking, not hidden.
4. **Find food, chat** — type "Find pizza under $15 in Detroit". Show the
   rule-based intent working with no API key.
5. **Compare** — Classic Cheese (Detroit) vs Classic Cheese (Houston, when
   refreshed): same item, two branches, branch-isolated prices.
6. **Invalid input** — budget "-5" or "abc": show the validation message.
7. **Tests** — run `python -m pytest tests/ -q` in the terminal: 22 pass.

Talking points: branch isolation, NULL not zero, integer cents, no invented
numbers, AI-optional architecture, read-only tools for the model.
