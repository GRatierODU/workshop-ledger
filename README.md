# Workshop Ledger

A live dashboard for my Crusader Kings III Steam Workshop mods: subscribers, favorites, visitors, ratings, comments and 24-hour gains on one page, phone-friendly.

- **Page:** `docs/index.html`, served by GitHub Pages.
- **Data:** `fetch.py` runs in GitHub Actions every ~15 minutes, reads public Steam data and writes `docs/data/*.json`. `state/` keeps history and known comments between runs.
- **Phone alerts:** `fetch.py --comments` runs every ~5 minutes (Check new comments workflow) and pushes new comments by other people through [ntfy](https://ntfy.sh) to the topic in the `NTFY_TOPIC` repository secret.
- **Update right now:** Actions → "Update Workshop stats" → Run workflow.
- **Insights (needs the `STEAM_API_KEY` secret):** `insights.py` ranks your mods among CK3 mods and AGOT submods, builds the AGOT leaderboard and finds collections with your mods, once an hour. Alerts: new collections, new downvotes, star changes, reports, entering the AGOT top 10.
- **Hide a mod:** add its id to `HIDDEN_IDS` in `fetch.py`.
