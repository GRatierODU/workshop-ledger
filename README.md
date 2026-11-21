# Workshop Ledger

A live dashboard for my Crusader Kings III Steam Workshop mods: subscribers, favorites, visitors, ratings, comments and 24-hour gains on one page, phone-friendly.

- **Page:** `docs/index.html`, served by GitHub Pages.
- **Data:** `fetch.py` runs in GitHub Actions every ~15 minutes, reads public Steam data and writes `docs/data/*.json`. `state/` keeps history and known comments between runs.
- **Phone alerts:** new comments by other people are pushed through [ntfy](https://ntfy.sh) to the topic in the `NTFY_TOPIC` repository secret.
- **Update right now:** Actions → "Update Workshop stats" → Run workflow.
- **Hide a mod:** add its id to `HIDDEN_IDS` in `fetch.py`.
