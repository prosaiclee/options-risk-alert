from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PUT_DETAIL_FIELDS = [
    "timestamp",
    "symbol",
    "expiration",
    "days_to_expiry",
    "strike_bucket",
    "put_premium",
    "put_volume",
    "open_interest",
    "avg_iv",
    "avg_mid",
]


@dataclass(frozen=True)
class PutDetailSnapshot:
    timestamp: datetime
    symbol: str
    expiration: str
    days_to_expiry: int
    strike_bucket: str
    put_premium: float
    put_volume: int
    open_interest: int
    avg_iv: float
    avg_mid: float

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["timestamp"] = self.timestamp.isoformat()
        return data


def write_put_details(path: str | Path, details: list[PutDetailSnapshot], *, append: bool = False) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    should_write_header = not append or not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open(mode, encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=PUT_DETAIL_FIELDS)
        if should_write_header:
            writer.writeheader()
        for detail in details:
            writer.writerow(detail.to_dict())


def load_put_details(path: str | Path) -> list[PutDetailSnapshot]:
    input_path = Path(path)
    if not input_path.exists():
        return []
    details: list[PutDetailSnapshot] = []
    with input_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            details.append(
                PutDetailSnapshot(
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    symbol=row["symbol"],
                    expiration=row["expiration"],
                    days_to_expiry=int(float(row["days_to_expiry"])),
                    strike_bucket=row["strike_bucket"],
                    put_premium=float(row["put_premium"]),
                    put_volume=int(float(row["put_volume"])),
                    open_interest=int(float(row["open_interest"])),
                    avg_iv=float(row["avg_iv"]),
                    avg_mid=float(row["avg_mid"]),
                )
            )
    return details


def latest_put_detail_summary(path: str | Path, top_n: int = 3) -> str:
    details = load_put_details(path)
    if not details:
        return "풋옵션 세부 현황: 아직 저장된 만기/행사가 세부 데이터가 없습니다."
    latest = max(detail.timestamp for detail in details)
    current = [detail for detail in details if detail.timestamp == latest]
    current.sort(key=lambda item: item.put_premium, reverse=True)
    lines = [f"풋옵션 세부 현황 ({latest.isoformat()})"]
    for detail in current[:top_n]:
        lines.append(
            "- "
            f"{detail.symbol} {detail.expiration} {detail.strike_bucket} "
            f"({detail.days_to_expiry}D): premium {detail.put_premium:,.0f}, "
            f"vol {detail.put_volume:,}, IV {detail.avg_iv:.1f}%"
        )
    return "\n".join(lines)
