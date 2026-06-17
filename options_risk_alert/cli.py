from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .csv_loader import load_snapshots, write_snapshots
from .engine import OptionsRiskEngine
from .fear_greed import FearGreedIndex, fetch_fear_greed_index, format_fear_greed
from .market_calendar import is_us_market_trading_day, is_us_regular_market_open, market_closed_day_message, market_status_message
from .models import LEVEL_ORDER
from .put_details import latest_put_detail_summary, load_put_details, write_put_details
from .put_valuation import DEFAULT_PUT_VALUE_SYMBOLS, collect_put_value_candidates, render_put_value_report
from .telegram import send_telegram_document, send_telegram_message
from .visual_report import write_visual_report
from .yahoo_provider import DEFAULT_YAHOO_SYMBOLS, collect_yahoo_snapshots_with_put_details


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect abnormal U.S. options downside risk flow.")
    parser.add_argument("--history", required=True, help="Historical baseline CSV path.")
    parser.add_argument("--current", help="Current 15-minute delayed option flow CSV path. Required for --provider csv.")
    parser.add_argument("--current-latest", action="store_true", help="Use the latest timestamp in --history as current and earlier rows as baseline.")
    parser.add_argument("--provider", choices=["csv", "yahoo"], default="csv")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_YAHOO_SYMBOLS, help="Yahoo symbols to collect when --provider yahoo is used.")
    parser.add_argument("--max-expirations", type=int, default=4, help="Number of Yahoo option expirations to collect per symbol.")
    parser.add_argument("--save-current", help="Optional CSV path to save the collected current snapshots.")
    parser.add_argument("--append-current", action="store_true", help="Append to --save-current instead of overwriting it.")
    parser.add_argument("--save-put-details", default=".\\data\\yahoo_put_details.csv", help="CSV path to save Yahoo put detail snapshots.")
    parser.add_argument("--no-put-details", action="store_true", help="Disable saving and rendering put expiration/strike detail summaries.")
    parser.add_argument(
        "--include-closed-market",
        action="store_true",
        help="Collect Yahoo snapshots even outside the U.S. regular session. By default Yahoo collection skips closed-market periods.",
    )
    parser.add_argument("--include-fear-greed", action="store_true", default=True, help="Include CNN Fear & Greed Index as a market-context indicator. Enabled by default.")
    parser.add_argument("--no-fear-greed", action="store_true", help="Disable Fear & Greed Index lookup.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--min-history-points", type=int, default=10)
    parser.add_argument("--send-telegram", action="store_true", help="Send the rendered report to Telegram.")
    parser.add_argument(
        "--telegram-min-level",
        choices=["정상", "관찰", "주의", "위험"],
        default="관찰",
        help="Minimum portfolio level required to send Telegram. Use 정상 for scheduled status reports.",
    )
    parser.add_argument("--put-value", action="store_true", help="Show put option value candidates for hedge planning.")
    parser.add_argument("--put-value-symbols", nargs="+", default=DEFAULT_PUT_VALUE_SYMBOLS, help="Symbols to screen for put value candidates.")
    parser.add_argument("--put-value-top", type=int, default=3, help="Number of put candidates to show per symbol.")
    parser.add_argument("--put-value-max-spread", type=float, default=40.0, help="Maximum bid-ask spread percent for put value candidates.")
    parser.add_argument("--html-report", help="Write a standalone HTML dashboard for ETF option flow visualization.")
    parser.add_argument("--telegram-poll-once", action="store_true", help="Poll Telegram once and answer new user questions.")
    parser.add_argument("--telegram-listen", action="store_true", help="Continuously listen for Telegram questions using long polling.")
    args = parser.parse_args(argv)

    if args.telegram_listen:
        from .telegram_bot import listen_telegram

        listen_telegram(history_path=args.history)
        return 0

    if args.telegram_poll_once:
        from .telegram_bot import poll_telegram_once

        result = poll_telegram_once(history_path=args.history)
        print(f"Telegram poll: processed={result.processed}, sent={result.sent}, message={result.message}")
        return 0

    loaded_history = load_snapshots(args.history)
    if args.current_latest:
        if not args.include_closed_market and not is_us_market_trading_day():
            print(market_closed_day_message())
            return 0
        history, current = split_latest_snapshot(loaded_history)
    elif args.provider == "csv":
        if not args.current:
            parser.error("--current is required when --provider csv is used.")
        history = loaded_history
        current = load_snapshots(args.current)
    else:
        if not args.include_closed_market and not is_us_regular_market_open():
            print(market_status_message())
            return 0
        history = loaded_history
        current, put_details = collect_yahoo_snapshots_with_put_details(args.symbols, max_expirations=args.max_expirations)
        if not args.no_put_details and args.save_put_details:
            write_put_details(args.save_put_details, put_details, append=args.append_current)
    if args.save_current:
        write_snapshots(args.save_current, current, append=args.append_current)
    engine = OptionsRiskEngine(history, min_history_points=args.min_history_points)
    report = engine.evaluate(current)
    fear_greed = None if args.no_fear_greed else fetch_fear_greed_index()
    put_detail_summary = None if args.no_put_details else latest_put_detail_summary(args.save_put_details)
    text_report = render_text_report(report, fear_greed=fear_greed, current=current, engine=engine, put_detail_summary=put_detail_summary)
    if args.html_report:
        visual_snapshots = loaded_history if args.current_latest else loaded_history + current
        visual_put_details = [] if args.no_put_details else load_put_details(args.save_put_details)
        write_visual_report(
            args.html_report,
            report=report,
            snapshots=visual_snapshots,
            engine=engine,
            fear_greed=fear_greed,
            put_details=visual_put_details,
        )
        print(f"HTML report saved: {args.html_report}", file=sys.stderr)

    if args.format == "json":
        payload = report.to_dict()
        if fear_greed:
            payload["fear_greed_index"] = fear_greed.to_dict()
        if args.put_value:
            put_candidates = collect_put_value_candidates(
                args.put_value_symbols,
                top_n=args.put_value_top,
                max_spread_pct=args.put_value_max_spread,
                history_snapshots=loaded_history,
            )
            payload["put_value_candidates"] = {
                symbol: [candidate.to_dict() for candidate in candidates]
                for symbol, candidates in put_candidates.items()
            }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.put_value:
            put_candidates = collect_put_value_candidates(
                args.put_value_symbols,
                top_n=args.put_value_top,
                max_spread_pct=args.put_value_max_spread,
                history_snapshots=loaded_history,
            )
            text_report = text_report + "\n\n" + render_put_value_report(put_candidates)
        print(text_report)
    if args.send_telegram:
        if LEVEL_ORDER[report.level] >= LEVEL_ORDER[args.telegram_min_level]:
            telegram_result = send_telegram_message(text_report)
            if not telegram_result.ok:
                print(f"Telegram 전송 실패: {telegram_result.message}")
                return 2
            if args.html_report:
                document_result = send_telegram_document(
                    args.html_report,
                    caption=f"ETF options visualization dashboard | {report.level} | {report.generated_at.isoformat()}",
                )
                if not document_result.ok:
                    print(f"Telegram HTML 전송 실패: {document_result.message}")
                    return 2
            print("Telegram 전송 완료")
        else:
            print(f"Telegram 전송 생략: {report.level} < {args.telegram_min_level}")
    return 0


def split_latest_snapshot(snapshots):
    if not snapshots:
        raise ValueError("--history has no snapshots.")
    latest = max(snapshot.timestamp for snapshot in snapshots)
    history = [snapshot for snapshot in snapshots if snapshot.timestamp < latest]
    current = [snapshot for snapshot in snapshots if snapshot.timestamp == latest]
    if not history:
        raise ValueError("--current-latest requires at least one earlier snapshot in --history.")
    return history, current


def render_text_report(report, fear_greed: FearGreedIndex | None = None, current=None, engine=None, put_detail_summary: str | None = None) -> str:
    lines = [
        f"Options Risk Alert | {report.level}",
        f"기준: {report.generated_at.isoformat()} / 지연 {report.data_delay_minutes}분",
        "",
        "총평",
        f"- {report.summary}",
    ]
    if fear_greed:
        lines.extend(["", "시장 심리", f"- {format_fear_greed(fear_greed)}"])
        if fear_greed.available:
            lines.append(f"- {fear_greed_context(fear_greed)}")
        else:
            lines.append("- 기존 옵션 플로우 평가는 계속 유효하지만, 시장 심리 보조 지표는 제외했습니다.")
    if current and engine:
        lines.extend(["", "ETF별 옵션 현황", render_etf_overview(report, current, engine)])
    if put_detail_summary:
        lines.extend(["", put_detail_summary])
    lines.extend(["", "알림 근거"])
    for symbol_report in report.symbol_reports:
        lines.append(f"- {symbol_report.symbol} {symbol_report.level} (score={symbol_report.score}): {symbol_report.summary}")
        for item in symbol_report.evidence[:4]:
            if item.z_score is None:
                lines.append(f"  * {item.message} 현재값={format_number(item.value)}")
            else:
                lines.append(
                    "  * "
                    f"{item.message} 현재값={format_number(item.value)}, "
                    f"기준평균={format_number(item.baseline_mean)}, z={item.z_score:.2f}"
                )
        for caveat in symbol_report.caveats:
            lines.append(f"  - 주의: {caveat}")
    lines.extend(["", report.disclaimer])
    return "\n".join(lines)


def render_etf_overview(report, current, engine) -> str:
    reports = {symbol_report.symbol: symbol_report for symbol_report in report.symbol_reports}
    lines = ["```", "ETF   등급  풋z   풋/콜  비율z"]
    for snapshot in sorted(current, key=lambda item: item.symbol):
        symbol_report = reports[snapshot.symbol]
        put_z, _ = engine.z_score(snapshot, "put_premium_bought")
        ratio_z, _ = engine.z_score(snapshot, "put_call_premium_ratio")
        lines.append(f"{snapshot.symbol:<5} {symbol_report.level:<4} {format_z(put_z):>5} {snapshot.put_call_premium_ratio:>6.2f} {format_z(ratio_z):>6}")
    lines.append("```")
    return "\n".join(lines)


def fear_greed_context(index: FearGreedIndex) -> str:
    if index.value is None:
        return "시장 심리 데이터를 사용할 수 없습니다."
    if index.value <= 24:
        return "극단적 공포 구간으로, 옵션 하방 신호가 함께 나오면 위험회피 해석이 강화됩니다."
    if index.value <= 44:
        return "공포 구간으로, 방어적 옵션 수요와 함께 보면 시장 불안이 커진 상태입니다."
    if index.value <= 55:
        return "중립 구간입니다. 옵션 플로우 신호를 더 우선해서 해석합니다."
    if index.value <= 75:
        return "탐욕 구간입니다. 하방 옵션 급증이 나오면 낙관적 분위기 속 헤지 증가로 해석할 수 있습니다."
    return "극단적 탐욕 구간입니다. 하방 옵션 급증은 과열 구간의 방어적 헤지 신호일 수 있습니다."


def format_number(value) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def format_z(value) -> str:
    return "n/a" if value is None else f"{value:.2f}"
