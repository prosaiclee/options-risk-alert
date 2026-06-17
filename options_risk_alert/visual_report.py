from __future__ import annotations

from html import escape
from math import isfinite
from pathlib import Path
from typing import Callable, Iterable

from .engine import OptionsRiskEngine
from .fear_greed import FearGreedIndex, format_fear_greed
from .models import OptionFlowSnapshot, PortfolioRiskReport
from .put_details import PutDetailSnapshot


SYMBOL_COLORS = {
    "SPY": "#2563eb",
    "QQQ": "#7c3aed",
    "SOXX": "#dc2626",
    "SMH": "#ea580c",
    "VIX": "#0891b2",
}


def write_visual_report(
    path: str | Path,
    *,
    report: PortfolioRiskReport,
    snapshots: list[OptionFlowSnapshot],
    engine: OptionsRiskEngine | None = None,
    fear_greed: FearGreedIndex | None = None,
    put_details: list[PutDetailSnapshot] | None = None,
) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        generate_visual_report(
            report=report,
            snapshots=snapshots,
            engine=engine,
            fear_greed=fear_greed,
            put_details=put_details or [],
        ),
        encoding="utf-8",
    )


def generate_visual_report(
    *,
    report: PortfolioRiskReport,
    snapshots: list[OptionFlowSnapshot],
    engine: OptionsRiskEngine | None = None,
    fear_greed: FearGreedIndex | None = None,
    put_details: list[PutDetailSnapshot] | None = None,
) -> str:
    recent = sorted(snapshots, key=lambda item: item.timestamp)
    symbol_reports = {item.symbol: item for item in report.symbol_reports}
    latest_rows = _latest_by_symbol(recent)
    put_details = put_details or []

    sections = [
        _summary_section(report, fear_greed),
        _latest_table(latest_rows, symbol_reports, engine),
        _chart_section(recent),
        _put_details_table(put_details),
    ]
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Options Risk Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --border: #dbe2ea;
      --text: #111827;
      --muted: #64748b;
      --accent: #0f766e;
      --danger: #b91c1c;
      --warn: #b45309;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, "Malgun Gothic", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.45;
    }}
    main {{
      width: min(1180px, calc(100% - 28px));
      margin: 0 auto;
      padding: 24px 0 44px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      margin-bottom: 18px;
    }}
    h1, h2 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; margin-bottom: 12px; }}
    .timestamp {{ color: var(--muted); margin-top: 4px; font-size: 13px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 6px 12px;
      border-radius: 6px;
      background: #e0f2fe;
      color: #075985;
      font-weight: 700;
      white-space: nowrap;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
      margin-top: 14px;
      overflow: hidden;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .metric {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      min-width: 0;
    }}
    .metric span {{
      color: var(--muted);
      display: block;
      font-size: 12px;
      margin-bottom: 4px;
    }}
    .metric strong {{ font-size: 18px; overflow-wrap: anywhere; }}
    .muted {{ color: var(--muted); }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 760px; }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 9px 10px;
      text-align: right;
      font-size: 13px;
      vertical-align: top;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ color: var(--muted); font-weight: 700; background: #f8fafc; }}
    .charts {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }}
    .chart {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      overflow-x: auto;
    }}
    svg {{ width: 100%; min-width: 760px; height: auto; display: block; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; font-size: 12px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 5px; color: var(--muted); }}
    .swatch {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
    footer {{ margin-top: 16px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 760px) {{
      main {{ width: min(100% - 16px, 1180px); padding-top: 14px; }}
      header {{ display: block; }}
      h1 {{ font-size: 22px; }}
      .badge {{ margin-top: 10px; }}
      section {{ padding: 14px; }}
      .summary-grid {{ grid-template-columns: 1fr 1fr; }}
      .metric strong {{ font-size: 16px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>ETF Options Risk Dashboard</h1>
        <div class="timestamp">Generated at {escape(report.generated_at.isoformat())} / source delay {report.data_delay_minutes} min</div>
      </div>
      <div class="badge">{escape(report.level)}</div>
    </header>
    {''.join(sections)}
    <footer>{escape(report.disclaimer)}</footer>
  </main>
</body>
</html>
"""


def _summary_section(report: PortfolioRiskReport, fear_greed: FearGreedIndex | None) -> str:
    fear_text = "n/a"
    if fear_greed:
        fear_text = format_fear_greed(fear_greed)
    return f"""
    <section>
      <h2>Summary</h2>
      <p>{escape(report.summary)}</p>
      <div class="summary-grid">
        <div class="metric"><span>Overall level</span><strong>{escape(report.level)}</strong></div>
        <div class="metric"><span>Score</span><strong>{report.score}</strong></div>
        <div class="metric"><span>Watched symbols</span><strong>{escape(', '.join(report.watched_symbols))}</strong></div>
        <div class="metric"><span>Fear & Greed</span><strong>{escape(fear_text)}</strong></div>
      </div>
    </section>
    """


def _latest_table(
    snapshots: list[OptionFlowSnapshot],
    symbol_reports: dict[str, object],
    engine: OptionsRiskEngine | None,
) -> str:
    rows = []
    for snapshot in snapshots:
        symbol_report = symbol_reports.get(snapshot.symbol)
        level = getattr(symbol_report, "level", "n/a")
        put_z = ratio_z = None
        if engine:
            put_z, _ = engine.z_score(snapshot, "put_premium_bought")
            ratio_z, _ = engine.z_score(snapshot, "put_call_premium_ratio")
        rows.append(
            "<tr>"
            f"<td>{escape(snapshot.symbol)}</td>"
            f"<td>{escape(str(level))}</td>"
            f"<td>{_compact(snapshot.put_premium_bought)}</td>"
            f"<td>{snapshot.put_call_premium_ratio:.2f}</td>"
            f"<td>{_format_optional_z(put_z)}</td>"
            f"<td>{_format_optional_z(ratio_z)}</td>"
            f"<td>{snapshot.iv30:.2f}</td>"
            f"<td>{snapshot.norm_25d_skew_30:.2f}</td>"
            f"<td>{snapshot.short_dated_share:.1%}</td>"
            f"<td>{_compact(snapshot.underlying_price)}</td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="10">No snapshots available.</td></tr>'
    return f"""
    <section>
      <h2>Latest ETF Snapshot</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Level</th><th>Put premium</th><th>Put/Call</th>
              <th>Put z</th><th>Ratio z</th><th>IV30</th><th>Skew</th>
              <th>Short dated</th><th>Underlying</th>
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </section>
    """


def _chart_section(snapshots: list[OptionFlowSnapshot]) -> str:
    charts = [
        _line_chart("Put premium trend", snapshots, lambda item: item.put_premium_bought, y_floor=0.0, formatter=_compact),
        _line_chart("Put/Call premium ratio", snapshots, lambda item: item.put_call_premium_ratio, y_floor=0.0),
        _line_chart("IV30 trend", snapshots, lambda item: item.iv30, y_floor=0.0),
    ]
    return f"""
    <section>
      <h2>Trend Charts</h2>
      <div class="charts">{''.join(charts)}</div>
    </section>
    """


def _line_chart(
    title: str,
    snapshots: list[OptionFlowSnapshot],
    value_getter: Callable[[OptionFlowSnapshot], float],
    *,
    y_floor: float | None = None,
    formatter: Callable[[float], str] | None = None,
    max_points_per_symbol: int = 80,
) -> str:
    series = _series_by_symbol(snapshots, value_getter, max_points_per_symbol)
    values = [point[1] for points in series.values() for point in points]
    if not values:
        return f'<div class="chart"><strong>{escape(title)}</strong><p class="muted">No chart data.</p></div>'

    min_y = min(values)
    max_y = max(values)
    if y_floor is not None:
        min_y = min(y_floor, min_y)
    if max_y == min_y:
        max_y = min_y + 1.0

    width = 920
    height = 300
    left = 62
    right = 18
    top = 24
    bottom = 42
    chart_w = width - left - right
    chart_h = height - top - bottom

    def x_at(index: int, total: int) -> float:
        if total <= 1:
            return left + chart_w
        return left + (chart_w * index / (total - 1))

    def y_at(value: float) -> float:
        return top + chart_h - ((value - min_y) / (max_y - min_y) * chart_h)

    grid_lines = []
    y_formatter = formatter or _plain_number
    for index in range(5):
        value = min_y + (max_y - min_y) * index / 4
        y = y_at(value)
        grid_lines.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5e7eb" />'
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{escape(y_formatter(value))}</text>'
        )

    paths = []
    legend = []
    for symbol, points in series.items():
        color = SYMBOL_COLORS.get(symbol, "#334155")
        coords = " ".join(f"{x_at(index, len(points)):.1f},{y_at(value):.1f}" for index, (_, value) in enumerate(points))
        paths.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" />')
        legend.append(f'<span class="legend-item"><span class="swatch" style="background:{color}"></span>{escape(symbol)}</span>')

    first_label, last_label = _chart_time_labels(snapshots)
    svg = f"""
      <svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
        <text x="{left}" y="16" font-size="14" font-weight="700" fill="#111827">{escape(title)}</text>
        {''.join(grid_lines)}
        <line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#cbd5e1" />
        <line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#cbd5e1" />
        {''.join(paths)}
        <text x="{left}" y="{height - 14}" font-size="11" fill="#64748b">{escape(first_label)}</text>
        <text x="{width - right}" y="{height - 14}" text-anchor="end" font-size="11" fill="#64748b">{escape(last_label)}</text>
      </svg>
    """
    return f'<div class="chart">{svg}<div class="legend">{"".join(legend)}</div></div>'


def _put_details_table(details: list[PutDetailSnapshot]) -> str:
    if not details:
        body = '<tr><td colspan="8">No put expiration/strike detail data yet.</td></tr>'
        latest_label = "n/a"
    else:
        latest = max(item.timestamp for item in details)
        latest_label = latest.isoformat()
        current = [item for item in details if item.timestamp == latest]
        current.sort(key=lambda item: item.put_premium, reverse=True)
        body = "".join(
            "<tr>"
            f"<td>{escape(item.symbol)}</td>"
            f"<td>{escape(item.expiration)}</td>"
            f"<td>{item.days_to_expiry}</td>"
            f"<td>{escape(item.strike_bucket)}</td>"
            f"<td>{_compact(item.put_premium)}</td>"
            f"<td>{item.put_volume:,}</td>"
            f"<td>{item.open_interest:,}</td>"
            f"<td>{item.avg_iv:.2f}</td>"
            "</tr>"
            for item in current[:16]
        )
    return f"""
    <section>
      <h2>Put Expiration / Strike Detail</h2>
      <p class="muted">Latest detail snapshot: {escape(latest_label)}</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th><th>Expiration</th><th>DTE</th><th>Strike bucket</th>
              <th>Put premium</th><th>Volume</th><th>Open interest</th><th>Avg IV</th>
            </tr>
          </thead>
          <tbody>{body}</tbody>
        </table>
      </div>
    </section>
    """


def _latest_by_symbol(snapshots: list[OptionFlowSnapshot]) -> list[OptionFlowSnapshot]:
    latest: dict[str, OptionFlowSnapshot] = {}
    for snapshot in snapshots:
        current = latest.get(snapshot.symbol)
        if current is None or snapshot.timestamp >= current.timestamp:
            latest[snapshot.symbol] = snapshot
    return [latest[symbol] for symbol in sorted(latest)]


def _series_by_symbol(
    snapshots: Iterable[OptionFlowSnapshot],
    value_getter: Callable[[OptionFlowSnapshot], float],
    max_points_per_symbol: int,
) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for snapshot in sorted(snapshots, key=lambda item: item.timestamp):
        value = float(value_getter(snapshot))
        if not isfinite(value):
            continue
        grouped.setdefault(snapshot.symbol, []).append((snapshot.timestamp.isoformat(), value))
    return {symbol: points[-max_points_per_symbol:] for symbol, points in sorted(grouped.items()) if points}


def _chart_time_labels(snapshots: list[OptionFlowSnapshot]) -> tuple[str, str]:
    if not snapshots:
        return ("n/a", "n/a")
    ordered = sorted(snapshots, key=lambda item: item.timestamp)
    return (ordered[0].timestamp.strftime("%m-%d %H:%M"), ordered[-1].timestamp.strftime("%m-%d %H:%M"))


def _format_optional_z(value: float | None) -> str:
    if value is None or not isfinite(value):
        return "n/a"
    return f"{value:.2f}"


def _compact(value: float) -> str:
    if not isfinite(float(value)):
        return "n/a"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.2f}"


def _plain_number(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:.0f}"
    return f"{value:.2f}"
