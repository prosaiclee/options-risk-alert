from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import OptionFlowSnapshot

CSV_FIELDS = [
    "timestamp",
    "symbol",
    "put_premium_bought",
    "call_premium_bought",
    "puts_bought",
    "calls_bought",
    "otm_put_oi",
    "otm_call_oi",
    "iv30",
    "hv20",
    "norm_25d_skew_30",
    "net_option_delta",
    "dtx1",
    "dtx2_5",
    "dtx6_30",
    "underlying_price",
    "underlying_change_pct",
    "is_event_day",
    "large_trade_count",
    "total_trade_count",
    "vix_front_month",
    "vix_second_month",
    "source_delay_minutes",
    "source",
    "underlying_group",
    "asset_role",
]


NUMERIC_FIELDS = {
    "put_premium_bought": float,
    "call_premium_bought": float,
    "puts_bought": int,
    "calls_bought": int,
    "otm_put_oi": int,
    "otm_call_oi": int,
    "iv30": float,
    "hv20": float,
    "norm_25d_skew_30": float,
    "net_option_delta": float,
    "dtx1": int,
    "dtx2_5": int,
    "dtx6_30": int,
    "underlying_price": float,
    "underlying_change_pct": float,
    "large_trade_count": int,
    "total_trade_count": int,
    "vix_front_month": float,
    "vix_second_month": float,
    "source_delay_minutes": int,
}


def load_snapshots(path: str | Path) -> list[OptionFlowSnapshot]:
    rows: list[OptionFlowSnapshot] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            rows.append(snapshot_from_row(row))
    return rows


def write_snapshots(path: str | Path, snapshots: list[OptionFlowSnapshot], *, append: bool = False) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    should_write_header = not append or not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open(mode, encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        if should_write_header:
            writer.writeheader()
        for snapshot in snapshots:
            row = {field: getattr(snapshot, field) for field in CSV_FIELDS if hasattr(snapshot, field)}
            row["timestamp"] = snapshot.timestamp.isoformat()
            writer.writerow(row)


def snapshot_from_row(row: dict[str, str]) -> OptionFlowSnapshot:
    parsed: dict[str, Any] = {
        "timestamp": parse_timestamp(required(row, "timestamp")),
        "symbol": required(row, "symbol"),
    }
    for field_name, caster in NUMERIC_FIELDS.items():
        value = row.get(field_name, "")
        if value == "":
            continue
        parsed[field_name] = caster(float(value)) if caster is int else caster(value)
    parsed["is_event_day"] = parse_bool(row.get("is_event_day", "false"))
    if row.get("underlying_group"):
        parsed["underlying_group"] = row["underlying_group"]
    if row.get("asset_role"):
        parsed["asset_role"] = row["asset_role"]
    if row.get("source"):
        parsed["source"] = row["source"]
    return OptionFlowSnapshot(**parsed)


def required(row: dict[str, str], field_name: str) -> str:
    value = row.get(field_name, "")
    if not value:
        raise ValueError(f"Missing required CSV field: {field_name}")
    return value


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}
