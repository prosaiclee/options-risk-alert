from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CNN_FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


@dataclass(frozen=True)
class FearGreedIndex:
    value: float | None
    rating: str
    timestamp: datetime | None
    one_year_percentile: float | None = None
    one_year_min: float | None = None
    one_year_max: float | None = None
    source: str = "CNN Fear & Greed Index"
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "rating": self.rating,
            "rating_ko": korean_rating(self.rating),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "one_year_percentile": self.one_year_percentile,
            "one_year_min": self.one_year_min,
            "one_year_max": self.one_year_max,
            "source": self.source,
            "error": self.error,
        }


def fetch_fear_greed_index(url: str = CNN_FEAR_GREED_URL, timeout: int = 10) -> FearGreedIndex:
    package_result = fetch_with_fear_and_greed_package()
    if package_result.available:
        return package_result

    request = Request(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "User-Agent": "Mozilla/5.0 options-risk-alert/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return FearGreedIndex(None, "unavailable", None, error=str(exc))
    return parse_fear_greed_payload(payload)


def fetch_with_fear_and_greed_package() -> FearGreedIndex:
    try:
        import fear_and_greed
    except ImportError as exc:
        return FearGreedIndex(None, "unavailable", None, error=f"fear-and-greed package unavailable: {exc}")

    try:
        result = fear_and_greed.get()
        payload = None
        try:
            import fear_and_greed.cnn as cnn

            payload = cnn.Fetcher()()
        except Exception:
            payload = None
    except Exception as exc:
        return FearGreedIndex(None, "unavailable", None, error=str(exc))

    value = float(result.value)
    timestamp = result.last_update
    if timestamp and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    position = one_year_position(payload, value) if payload else {}
    return FearGreedIndex(value, normalize_rating(str(result.description), value), timestamp, **position)


def parse_fear_greed_payload(payload: dict[str, Any]) -> FearGreedIndex:
    raw = payload.get("fear_and_greed", payload)
    value = _extract_number(raw, "score", "value", "fearGreedIndex")
    rating = str(raw.get("rating") or raw.get("status") or classify_fear_greed(value)).strip()
    timestamp = _extract_timestamp(raw.get("timestamp") or raw.get("lastUpdated") or raw.get("asOf"))
    return FearGreedIndex(value, normalize_rating(rating, value), timestamp, **one_year_position(payload, value))


def classify_fear_greed(value: float | None) -> str:
    if value is None:
        return "unavailable"
    if value <= 24:
        return "Extreme Fear"
    if value <= 44:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


def normalize_rating(rating: str, value: float | None) -> str:
    clean = rating.replace("_", " ").strip().lower()
    if clean in {"extreme fear", "fear", "neutral", "greed", "extreme greed"}:
        return " ".join(word.capitalize() for word in clean.split())
    return classify_fear_greed(value)


def format_fear_greed(index: FearGreedIndex) -> str:
    if not index.available:
        return f"Fear & Greed Index: 조회 실패 ({index.error})"
    position = format_one_year_position(index)
    return f"Fear & Greed Index: {index.value:.0f} / 100 / {korean_rating(index.rating)} / {position}"


def korean_rating(rating: str) -> str:
    labels = {
        "Extreme Fear": "극단적 공포",
        "Fear": "공포",
        "Neutral": "중립",
        "Greed": "탐욕",
        "Extreme Greed": "극단적 탐욕",
        "unavailable": "조회 불가",
    }
    return labels.get(rating, labels.get(normalize_rating(rating, None), rating))


def format_one_year_position(index: FearGreedIndex) -> str:
    if index.one_year_percentile is None:
        return "1년 내 위치 조회 불가"
    return (
        f"1년 내 하위 {index.one_year_percentile:.0f}% "
        f"(범위 {index.one_year_min:.0f}-{index.one_year_max:.0f})"
    )


def one_year_position(payload: dict[str, Any], current_value: float | None) -> dict[str, float | None]:
    if current_value is None:
        return {}
    historical = payload.get("fear_and_greed_historical", {})
    data = historical.get("data", []) if isinstance(historical, dict) else []
    values: list[float] = []
    for point in data:
        if not isinstance(point, dict):
            continue
        value = point.get("y", point.get("score"))
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return {}
    below_or_equal = sum(1 for value in values if value <= current_value)
    return {
        "one_year_percentile": below_or_equal / len(values) * 100,
        "one_year_min": min(values),
        "one_year_max": max(values),
    }


def _extract_number(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in raw:
            continue
        try:
            return float(raw[key])
        except (TypeError, ValueError):
            continue
    return None


def _extract_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None
