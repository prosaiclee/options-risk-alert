#!/bin/bash
# Poll Telegram once for new user questions and answer them. Run on a short
# interval (e.g. every 60s) by launchd for near-realtime Q&A without keeping a
# long-lived process alive. The last processed update id is stored in
# data/telegram_offset.txt, so each run only handles new messages.
set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

python -m options_risk_alert \
  --history data/yahoo_snapshots.csv \
  --telegram-poll-once
