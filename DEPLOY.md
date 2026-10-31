# Deploying the chatbot as a public website (free)

The app is a standard Streamlit app, so the simplest free hosting is
**Streamlit Community Cloud** (made by the Streamlit team, free for public apps).

## What was already prepared for hosting

- `app.py` seeds the SQLite database **automatically on first run** from
  `data/reviewed/menu.json` — no manual `import_data` step needed on the host.
- `requirements.txt` lists everything the host must install.
- `.gitignore` keeps the local database and secrets out of git.

## Steps (about 10 minutes)

1. **Create a GitHub account** (if you don't have one): https://github.com
2. **Create a new repository** (e.g. `restaurant-chatbot`), public.
3. **Upload the project files** to the repo — everything inside
   `restaurant-chatbot/` (app.py, src/, data/, tests/, requirements.txt, ...).
   Easiest: on the repo page use *Add file → Upload files* and drag the folder
   contents in. (`data/restaurant.db` is ignored — the host rebuilds it.)
4. **Go to https://share.streamlit.io** and sign in with GitHub.
5. Click **New app** → select your repository, branch `main`, main file `app.py`
   → **Deploy**.
6. Wait 2–3 minutes. You get a public URL like
   `https://your-app-name.streamlit.app` — open it on your phone or laptop;
   the chatbot runs there, no laptop needed.

## Optional: LLM key on the hosted app

The app works fully without a key. To enable the LLM path on the host:
Streamlit Cloud → your app → **Settings → Secrets**, add:

```toml
LLM_API_KEY = "sk-..."
LLM_MODEL = "gpt-4o-mini"
```

`app.py` reads these from environment variables, which is exactly how
Streamlit secrets are exposed.

## Adding more data later

You never edit the database directly. The workflow is always:

1. Edit **`data/reviewed/menu.json`** — add the restaurant, branch, items,
   prices, calories, and a `sources` record (with the official URL and
   checked date), exactly like the existing entries.
2. Bump the version string at the top: `"_meta": { "version": "..." }`
   (e.g. `"2026-11-05-dominos"`). **This step matters** — the app uses it
   to detect that the data changed.
3. That's it. On the next app start the new version is detected and the
   import runs automatically:
   - **On your laptop:** just restart the Streamlit app.
   - **On the hosted site:** push the updated `menu.json` to GitHub —
     Streamlit Cloud reboots the app on every push, and the fresh import
     runs on restart.

Old prices are kept as history (`is_current=0`); nothing is overwritten or
invented. If the JSON has any mistake, the import is rejected completely
(validated first, committed only if everything passes).

## Notes

- Free tier = the app is **public** (anyone with the link can open it).
- The hosted filesystem is ephemeral: if the app sleeps/restarts, the database
  is rebuilt from `menu.json` automatically — your verified data is never lost.
- To update data later: edit `data/reviewed/menu.json`, push to GitHub, and
  reboot the app (⋮ menu → Reboot). The fresh import runs on next start.
