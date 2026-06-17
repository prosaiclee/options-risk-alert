#!/bin/bash
# Collect a Yahoo options snapshot, regenerate the dashboard, send a Telegram
# alert if warranted, and push so Vercel redeploys. Safe to run on a fixed
# interval: the Python CLI skips collection outside U.S. regular market hours,
# so off-hours runs simply no-op and produce no commit.
#
# Used by the launchd job scripts/macos/com.optionsrisk.collect.plist on a Mac
# mini acting as the always-on home server.
set -euo pipefail

# Repo root = parent of this script's directory (location-independent).
cd "$(cd "$(dirname "$0")/.." && pwd)"

# Activate the virtualenv if present.
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m options_risk_alert \
  --provider yahoo \
  --history data/yahoo_snapshots.csv \
  --symbols SPY QQQ SOXX SMH \
  --save-current data/yahoo_snapshots.csv --append-current \
  --save-put-details data/yahoo_put_details.csv \
  --html-report public/index.html \
  --send-telegram --telegram-min-level 관찰

# Commit and push only if the run produced changes (i.e., market was open).
git add public/index.html data/yahoo_snapshots.csv data/yahoo_put_details.csv
if git diff --cached --quiet; then
  echo "No changes (market likely closed). Nothing to push."
else
  git pull --rebase --autostash origin main || true
  git commit -m "chore: refresh options dashboard (mac mini)"
  git push origin main
fi
