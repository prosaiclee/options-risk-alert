from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from time import sleep
from typing import Any

from .cli import fear_greed_context, render_etf_overview, split_latest_snapshot
from .csv_loader import load_snapshots
from .engine import OptionsRiskEngine
from .fear_greed import fetch_fear_greed_index, format_fear_greed
from .put_details import latest_put_detail_summary
from .put_valuation import collect_put_value_candidates, render_put_value_report
from .telegram import get_telegram_updates, read_env_file, send_telegram_message


DEFAULT_OFFSET_PATH = Path("data/telegram_offset.txt")


@dataclass(frozen=True)
class BotPollResult:
    processed: int
    sent: int
    message: str


def poll_telegram_once(
    *,
    history_path: str,
    offset_path: str | Path = DEFAULT_OFFSET_PATH,
    timeout_seconds: int = 10,
) -> BotPollResult:
    offset_file = Path(offset_path)
    offset = read_offset(offset_file)
    updates_result = get_telegram_updates(offset=offset, timeout_seconds=timeout_seconds)
    if not updates_result.ok or not updates_result.response:
        return BotPollResult(0, 0, updates_result.message)

    updates = updates_result.response.get("result", [])
    if not updates:
        return BotPollResult(0, 0, "no updates")

    allowed_chat_id = read_allowed_chat_id()
    processed = 0
    sent = 0
    next_offset = offset
    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            next_offset = max(next_offset or 0, int(update_id) + 1)
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = str(message.get("text", "")).strip()
        if not text:
            continue
        if allowed_chat_id and chat_id != allowed_chat_id:
            continue
        processed += 1
        answer = answer_question(text, history_path)
        result = send_telegram_message(answer, chat_id=chat_id)
        if result.ok:
            sent += 1

    if next_offset is not None:
        write_offset(offset_file, next_offset)
    return BotPollResult(processed, sent, "ok")


def listen_telegram(
    *,
    history_path: str,
    offset_path: str | Path = DEFAULT_OFFSET_PATH,
    timeout_seconds: int = 50,
    sleep_seconds: int = 1,
) -> None:
    while True:
        result = poll_telegram_once(
            history_path=history_path,
            offset_path=offset_path,
            timeout_seconds=timeout_seconds,
        )
        print(f"Telegram listen: processed={result.processed}, sent={result.sent}, message={result.message}", flush=True)
        sleep(sleep_seconds)


def answer_question(text: str, history_path: str) -> str:
    normalized = text.lower()
    if any(keyword in normalized for keyword in ["/start", "help", "도움", "명령"]):
        return help_message()
    if any(keyword in normalized for keyword in ["풋", "put", "헷지", "헤지", "싸", "가치"]):
        return put_value_answer(history_path)
    if any(keyword in normalized for keyword in ["옵션", "etf", "qqq", "spy", "soxx", "smh"]):
        return option_status_answer(history_path)
    if any(keyword in normalized for keyword in ["시장", "상황", "fear", "greed", "공포", "탐욕"]):
        return market_status_answer(history_path)
    return "질문을 이해하지 못했습니다.\n\n" + help_message()


def market_status_answer(history_path: str) -> str:
    report, current, engine = latest_report(history_path)
    fear_greed = fetch_fear_greed_index()
    lines = [
        "시장 상황 요약",
        f"- 기준 시각: {report.generated_at.isoformat()}",
        f"- 옵션 플로우 등급: {report.level}",
        f"- {report.summary}",
        "",
        format_fear_greed(fear_greed),
    ]
    if fear_greed.available:
        lines.append(f"- 해석: {fear_greed_context(fear_greed)}")
    lines.extend(["", "ETF별 현황:", render_etf_overview(report, current, engine)])
    return "\n".join(lines)


def option_status_answer(history_path: str) -> str:
    report, current, engine = latest_report(history_path)
    return "\n".join(
        [
            "옵션 상황 요약",
            f"- 기준 시각: {report.generated_at.isoformat()}",
            f"- 전체 등급: {report.level}",
            f"- {report.summary}",
            "",
            render_etf_overview(report, current, engine),
            "",
            latest_put_detail_summary("data/yahoo_put_details.csv"),
        ]
    )


def put_value_answer(history_path: str) -> str:
    snapshots = load_snapshots(history_path)
    candidates = collect_put_value_candidates(["QQQ", "SOXX", "SMH"], top_n=2, max_spread_pct=60, history_snapshots=snapshots)
    return render_put_value_report(candidates)


def latest_report(history_path: str):
    snapshots = load_snapshots(history_path)
    history, current = split_latest_snapshot(snapshots)
    engine = OptionsRiskEngine(history)
    report = engine.evaluate(current)
    return report, current, engine


def help_message() -> str:
    return "\n".join(
        [
            "Options Risk Alert Bot 명령 예시",
            "- 시장 상황 알려줘",
            "- 옵션 상황 알려줘",
            "- 풋옵션 가치 알려줘",
            "- SOXX 헷지 후보",
            "",
            "응답은 저장된 최신 옵션 스냅샷과 현재 Fear & Greed Index를 기반으로 합니다.",
        ]
    )


def read_allowed_chat_id() -> str:
    env = read_env_file()
    return os.environ.get("TELEGRAM_CHAT_ID") or env.get("TELEGRAM_CHAT_ID", "")


def read_offset(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    return int(raw) if raw else None


def write_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(offset), encoding="utf-8")
