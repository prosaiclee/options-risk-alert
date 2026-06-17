#!/bin/bash
# Send a scheduled status report (includes 정상) to Telegram from the latest
# snapshot. Used by the timed launchd report jobs (Korea open / US pre-market).
# Mirrors the old Windows tasks OptionsRiskKoreaOpenReport / *USPreMarketReport.
set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m options_risk_alert \
  --history data/yahoo_snapshots.csv \
  --current-latest \
  --send-telegram --telegram-min-level 정상
