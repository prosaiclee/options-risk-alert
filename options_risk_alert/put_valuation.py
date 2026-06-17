from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import isfinite
from typing import Any, Iterable


DEFAULT_PUT_VALUE_SYMBOLS = ["QQQ", "SOXX", "SMH"]


@dataclass(frozen=True)
class PutOptionCandidate:
    symbol: str
    expiration: str
    days_to_expiry: int
    strike: float
    underlying_price: float
    moneyness_pct: float
    mid_price: float
    bid: float
    ask: float
    spread_pct: float
    implied_volatility: float
    volume: int
    open_interest: int
    premium_pct_underlying: float
    protection_pct: float
    cost_per_protection: float
    iv_percentile: float | None
    one_year_iv_percentile: float | None
    one_year_cheapness_score: float | None
    one_year_observations: int
    value_score: float
    rating: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def collect_put_value_candidates(
    symbols: Iterable[str],
    *,
    min_dte: int = 21,
    max_dte: int = 120,
    min_otm_pct: float = 5.0,
    max_otm_pct: float = 20.0,
    max_spread_pct: float = 40.0,
    min_open_interest: int = 50,
    max_expirations: int = 12,
    top_n: int = 3,
    timestamp: datetime | None = None,
    history_snapshots: Iterable[Any] | None = None,
) -> dict[str, list[PutOptionCandidate]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance가 설치되어 있지 않습니다. `python -m pip install -r requirements.txt`를 실행하세요.") from exc

    collected_at = timestamp or datetime.now(timezone.utc)
    results: dict[str, list[PutOptionCandidate]] = {}
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        underlying = _last_price(ticker)
        rows_by_expiration: list[tuple[str, list[dict[str, Any]]]] = []
        for expiration in list(getattr(ticker, "options", []) or [])[:max_expirations]:
            dte = _days_to_expiry(expiration, collected_at.date())
            if dte < min_dte or dte > max_dte:
                continue
            chain = ticker.option_chain(expiration)
            rows_by_expiration.append((expiration, _rows_from_frame(chain.puts)))
        candidates = build_put_value_candidates(
            symbol,
            underlying,
            rows_by_expiration,
            current_date=collected_at.date(),
            min_otm_pct=min_otm_pct,
            max_otm_pct=max_otm_pct,
            max_spread_pct=max_spread_pct,
            min_open_interest=min_open_interest,
            history_snapshots=history_snapshots,
        )
        results[symbol.upper()] = sorted(candidates, key=lambda item: item.value_score, reverse=True)[:top_n]
    return results


def build_put_value_candidates(
    symbol: str,
    underlying_price: float,
    expiration_rows: Iterable[tuple[str, Iterable[dict[str, Any]]]],
    *,
    current_date: date,
    min_otm_pct: float = 5.0,
    max_otm_pct: float = 20.0,
    max_spread_pct: float = 40.0,
    min_open_interest: int = 50,
    history_snapshots: Iterable[Any] | None = None,
) -> list[PutOptionCandidate]:
    raw_candidates: list[dict[str, Any]] = []
    for expiration, rows in expiration_rows:
        dte = _days_to_expiry(expiration, current_date)
        for row in rows:
            strike = _number(row.get("strike"))
            if strike <= 0 or underlying_price <= 0 or strike >= underlying_price:
                continue
            moneyness_pct = (underlying_price - strike) / underlying_price * 100
            if moneyness_pct < min_otm_pct or moneyness_pct > max_otm_pct:
                continue
            bid = _number(row.get("bid"))
            ask = _number(row.get("ask"))
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            mid = _mid_price(row)
            if mid <= 0:
                continue
            iv = _number(row.get("impliedVolatility")) * 100
            volume = int(_number(row.get("volume")))
            open_interest = int(_number(row.get("openInterest")))
            if open_interest < min_open_interest:
                continue
            premium_pct = mid / underlying_price * 100
            protection_pct = max(moneyness_pct, 0.01)
            spread_pct = (ask - bid) / mid * 100
            if spread_pct > max_spread_pct:
                continue
            raw_candidates.append(
                {
                    "symbol": symbol.upper(),
                    "expiration": expiration,
                    "days_to_expiry": dte,
                    "strike": strike,
                    "underlying_price": underlying_price,
                    "moneyness_pct": moneyness_pct,
                    "mid_price": mid,
                    "bid": bid,
                    "ask": ask,
                    "spread_pct": spread_pct,
                    "implied_volatility": iv,
                    "volume": volume,
                    "open_interest": open_interest,
                    "premium_pct_underlying": premium_pct,
                    "protection_pct": protection_pct,
                    "cost_per_protection": premium_pct / protection_pct,
                }
            )

    iv_values = [item["implied_volatility"] for item in raw_candidates if item["implied_volatility"] > 0]
    one_year_iv_values = historical_iv_values(history_snapshots or [], symbol, current_date)
    candidates: list[PutOptionCandidate] = []
    for item in raw_candidates:
        iv_percentile = percentile_rank(iv_values, item["implied_volatility"]) if iv_values else None
        one_year_iv_percentile = percentile_rank(one_year_iv_values, item["implied_volatility"]) if one_year_iv_values else None
        one_year_cheapness_score = None if one_year_iv_percentile is None else round(100.0 - one_year_iv_percentile, 2)
        score = put_value_score(item, iv_percentile, one_year_iv_percentile)
        candidates.append(
            PutOptionCandidate(
                **item,
                iv_percentile=iv_percentile,
                one_year_iv_percentile=one_year_iv_percentile,
                one_year_cheapness_score=one_year_cheapness_score,
                one_year_observations=len(one_year_iv_values),
                value_score=score,
                rating=value_rating(score),
            )
        )
    return candidates


def put_value_score(item: dict[str, Any], iv_percentile: float | None, one_year_iv_percentile: float | None = None) -> float:
    cost = item["cost_per_protection"]
    spread = item["spread_pct"]
    open_interest = item["open_interest"]
    volume = item["volume"]
    score = 0.0
    iv_anchor = one_year_iv_percentile if one_year_iv_percentile is not None else iv_percentile
    if iv_anchor is not None:
        score += max(0.0, 100.0 - iv_anchor) * 0.35
    score += max(0.0, 100.0 - min(cost * 25.0, 100.0)) * 0.30
    score += max(0.0, 100.0 - min(spread * 2.0, 100.0)) * 0.20
    score += min(100.0, open_interest / 10.0) * 0.10
    score += min(100.0, volume / 5.0) * 0.05
    return round(max(0.0, min(100.0, score)), 2)


def value_rating(score: float) -> str:
    if score >= 75:
        return "저렴"
    if score >= 55:
        return "보통"
    return "비쌈"


def percentile_rank(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    return sum(1 for item in values if item <= value) / len(values) * 100


def historical_iv_values(history_snapshots: Iterable[Any], symbol: str, current_date: date) -> list[float]:
    start_date = current_date - timedelta(days=365)
    values: list[float] = []
    target_symbol = symbol.upper()
    for snapshot in history_snapshots:
        snapshot_symbol = getattr(snapshot, "symbol", "").upper()
        timestamp = getattr(snapshot, "timestamp", None)
        iv30 = getattr(snapshot, "iv30", 0)
        if snapshot_symbol != target_symbol or timestamp is None:
            continue
        snapshot_date = timestamp.date()
        if start_date <= snapshot_date <= current_date and iv30 and iv30 > 0:
            values.append(float(iv30))
    return values


def render_put_value_report(candidates_by_symbol: dict[str, list[PutOptionCandidate]]) -> str:
    lines = [
        "풋옵션 가치 스크리닝",
        "기준: 21-120일 만기, 5-20% OTM 풋. 점수는 낮은 IV, 낮은 비용/보호폭, 좁은 스프레드, 유동성을 함께 본 상대 평가입니다.",
    ]
    for symbol, candidates in sorted(candidates_by_symbol.items()):
        lines.append(f"\n{symbol}")
        if not candidates:
            lines.append("- 조건에 맞는 후보 없음")
            continue
        for item in candidates:
            lines.append(
                "- "
                f"{item.expiration} {item.strike:.2f}P "
                f"({item.days_to_expiry}D, {item.moneyness_pct:.1f}% OTM): "
                f"mid {item.mid_price:.2f}, IV {item.implied_volatility:.1f}%, "
                f"1Y {format_one_year_cheapness(item)}, "
                f"cost {item.premium_pct_underlying:.2f}% of ETF, spread {item.spread_pct:.1f}%, "
                f"OI {item.open_interest}, score {item.value_score:.0f} ({item.rating})"
            )
    lines.append("\n주의: Yahoo 옵션 체인 기반 스크리닝이며 투자 조언이 아닙니다. 실제 주문 전 호가, 체결 가능성, 포지션 규모를 다시 확인해야 합니다.")
    return "\n".join(lines)


def format_one_year_cheapness(item: PutOptionCandidate) -> str:
    if item.one_year_iv_percentile is None or item.one_year_cheapness_score is None:
        return "1년 기준 없음"
    return f"IV 하위 {item.one_year_iv_percentile:.0f}%/저렴도 {item.one_year_cheapness_score:.0f}"


def _rows_from_frame(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return frame.to_dict("records")
    return list(frame)


def _last_price(ticker: Any) -> float:
    fast_info = getattr(ticker, "fast_info", None)
    if fast_info:
        for key in ("last_price", "lastPrice", "regularMarketPrice"):
            try:
                value = fast_info[key] if isinstance(fast_info, dict) else getattr(fast_info, key)
            except (KeyError, AttributeError):
                continue
            price = _number(value)
            if price > 0:
                return price
    history = ticker.history(period="1d")
    if hasattr(history, "empty") and not history.empty:
        return float(history["Close"].iloc[-1])
    raise RuntimeError("Yahoo Finance에서 기초자산 가격을 가져오지 못했습니다.")


def _mid_price(row: dict[str, Any]) -> float:
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    last = _number(row.get("lastPrice"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return last


def _days_to_expiry(expiration: str, current_date: date) -> int:
    expiry_date = date.fromisoformat(expiration)
    return max((expiry_date - current_date).days, 0)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0
