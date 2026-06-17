from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Iterable

from .models import OptionFlowSnapshot, normalize_symbol
from .put_details import PutDetailSnapshot


DEFAULT_YAHOO_SYMBOLS = ["SPY", "QQQ", "SOXX", "SMH"]


@dataclass(frozen=True)
class YahooExpirationRows:
    expiration: str
    calls: Iterable[dict[str, Any]]
    puts: Iterable[dict[str, Any]]


def collect_yahoo_snapshots(
    symbols: Iterable[str],
    *,
    max_expirations: int = 4,
    timestamp: datetime | None = None,
) -> list[OptionFlowSnapshot]:
    """Collect current option-chain snapshots from Yahoo Finance via yfinance."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance가 설치되어 있지 않습니다. `python -m pip install -r requirements.txt`를 실행하세요.") from exc

    collected_at = timestamp or datetime.now(timezone.utc)
    snapshots: list[OptionFlowSnapshot] = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        underlying_price = _yahoo_last_price(ticker)
        expirations = list(getattr(ticker, "options", []) or [])[:max_expirations]
        chains: list[YahooExpirationRows] = []
        for expiration in expirations:
            chain = ticker.option_chain(expiration)
            chains.append(
                YahooExpirationRows(
                    expiration=expiration,
                    calls=_rows_from_frame(chain.calls),
                    puts=_rows_from_frame(chain.puts),
                )
            )
        snapshots.append(build_yahoo_snapshot(symbol, underlying_price, chains, timestamp=collected_at))
    return snapshots


def collect_yahoo_snapshots_with_put_details(
    symbols: Iterable[str],
    *,
    max_expirations: int = 4,
    timestamp: datetime | None = None,
) -> tuple[list[OptionFlowSnapshot], list[PutDetailSnapshot]]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance가 설치되어 있지 않습니다. `python -m pip install -r requirements.txt`를 실행하세요.") from exc

    collected_at = timestamp or datetime.now(timezone.utc)
    snapshots: list[OptionFlowSnapshot] = []
    details: list[PutDetailSnapshot] = []
    for symbol in symbols:
        ticker = yf.Ticker(symbol)
        underlying_price = _yahoo_last_price(ticker)
        expirations = list(getattr(ticker, "options", []) or [])[:max_expirations]
        chains: list[YahooExpirationRows] = []
        for expiration in expirations:
            chain = ticker.option_chain(expiration)
            puts = _rows_from_frame(chain.puts)
            chains.append(YahooExpirationRows(expiration=expiration, calls=_rows_from_frame(chain.calls), puts=puts))
            details.extend(build_put_detail_snapshots(symbol, underlying_price, expiration, puts, timestamp=collected_at))
        snapshots.append(build_yahoo_snapshot(symbol, underlying_price, chains, timestamp=collected_at))
    return snapshots, details


def build_yahoo_snapshot(
    symbol: str,
    underlying_price: float,
    expirations: Iterable[YahooExpirationRows],
    *,
    timestamp: datetime | None = None,
) -> OptionFlowSnapshot:
    """Convert Yahoo option-chain rows into the engine's normalized snapshot model."""
    collected_at = timestamp or datetime.now(timezone.utc)
    put_premium = 0.0
    call_premium = 0.0
    put_volume = 0
    call_volume = 0
    otm_put_oi = 0
    otm_call_oi = 0
    dtx1 = 0
    dtx2_5 = 0
    dtx6_30 = 0
    put_iv_values: list[float] = []
    call_iv_values: list[float] = []
    atm_iv_values: list[float] = []
    total_trade_count = 0

    for chain in expirations:
        days_to_expiry = _days_to_expiry(chain.expiration, collected_at.date())
        for row in chain.puts:
            strike = _number(row.get("strike"))
            volume = int(_number(row.get("volume")))
            open_interest = int(_number(row.get("openInterest")))
            mid = _option_mid_price(row)
            iv = _number(row.get("impliedVolatility"))
            total_trade_count += 1 if volume > 0 else 0
            if strike < underlying_price:
                put_premium += volume * mid * 100
                put_volume += volume
                otm_put_oi += open_interest
                if iv > 0:
                    put_iv_values.append(iv)
                if days_to_expiry <= 1:
                    dtx1 += volume
                elif days_to_expiry <= 5:
                    dtx2_5 += volume
                elif days_to_expiry <= 30:
                    dtx6_30 += volume
            if _is_near_atm(strike, underlying_price) and iv > 0:
                atm_iv_values.append(iv)

        for row in chain.calls:
            strike = _number(row.get("strike"))
            volume = int(_number(row.get("volume")))
            open_interest = int(_number(row.get("openInterest")))
            mid = _option_mid_price(row)
            iv = _number(row.get("impliedVolatility"))
            total_trade_count += 1 if volume > 0 else 0
            if strike > underlying_price:
                call_premium += volume * mid * 100
                call_volume += volume
                otm_call_oi += open_interest
                if iv > 0:
                    call_iv_values.append(iv)
            if _is_near_atm(strike, underlying_price) and iv > 0:
                atm_iv_values.append(iv)

    iv30 = _mean(atm_iv_values) * 100
    put_iv = _mean(put_iv_values) * 100
    call_iv = _mean(call_iv_values) * 100
    skew = put_iv - call_iv if put_iv and call_iv else 0.0

    return OptionFlowSnapshot(
        timestamp=collected_at,
        symbol=normalize_symbol(symbol),
        put_premium_bought=put_premium,
        call_premium_bought=call_premium,
        puts_bought=put_volume,
        calls_bought=call_volume,
        otm_put_oi=otm_put_oi,
        otm_call_oi=otm_call_oi,
        iv30=iv30,
        norm_25d_skew_30=skew,
        dtx1=dtx1,
        dtx2_5=dtx2_5,
        dtx6_30=dtx6_30,
        underlying_price=underlying_price,
        large_trade_count=0,
        total_trade_count=total_trade_count,
        source_delay_minutes=15,
        source="yahoo",
    )


def build_put_detail_snapshots(
    symbol: str,
    underlying_price: float,
    expiration: str,
    puts: Iterable[dict[str, Any]],
    *,
    timestamp: datetime,
) -> list[PutDetailSnapshot]:
    buckets: dict[str, dict[str, float]] = {}
    days_to_expiry = _days_to_expiry(expiration, timestamp.date())
    for row in puts:
        strike = _number(row.get("strike"))
        if strike <= 0 or underlying_price <= 0 or strike >= underlying_price:
            continue
        otm_pct = (underlying_price - strike) / underlying_price * 100
        bucket = strike_bucket(otm_pct)
        volume = int(_number(row.get("volume")))
        open_interest = int(_number(row.get("openInterest")))
        mid = _option_mid_price(row)
        iv = _number(row.get("impliedVolatility")) * 100
        premium = volume * mid * 100
        entry = buckets.setdefault(bucket, {"premium": 0.0, "volume": 0.0, "oi": 0.0, "iv_weight": 0.0, "mid_weight": 0.0})
        entry["premium"] += premium
        entry["volume"] += volume
        entry["oi"] += open_interest
        entry["iv_weight"] += iv * max(volume, 1)
        entry["mid_weight"] += mid * max(volume, 1)

    details: list[PutDetailSnapshot] = []
    for bucket, entry in buckets.items():
        weight = max(entry["volume"], 1.0)
        details.append(
            PutDetailSnapshot(
                timestamp=timestamp,
                symbol=normalize_symbol(symbol),
                expiration=expiration,
                days_to_expiry=days_to_expiry,
                strike_bucket=bucket,
                put_premium=entry["premium"],
                put_volume=int(entry["volume"]),
                open_interest=int(entry["oi"]),
                avg_iv=entry["iv_weight"] / weight,
                avg_mid=entry["mid_weight"] / weight,
            )
        )
    return details


def strike_bucket(otm_pct: float) -> str:
    if otm_pct < 5:
        return "0-5% OTM"
    if otm_pct < 10:
        return "5-10% OTM"
    if otm_pct < 20:
        return "10-20% OTM"
    return "20%+ OTM"


def _rows_from_frame(frame: Any) -> list[dict[str, Any]]:
    if hasattr(frame, "to_dict"):
        return frame.to_dict("records")
    return list(frame)


def _yahoo_last_price(ticker: Any) -> float:
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


def _option_mid_price(row: dict[str, Any]) -> float:
    bid = _number(row.get("bid"))
    ask = _number(row.get("ask"))
    last = _number(row.get("lastPrice"))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2
    return last


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if isfinite(number) else 0.0


def _days_to_expiry(expiration: str, current_date: date) -> int:
    expiry_date = date.fromisoformat(expiration)
    return max((expiry_date - current_date).days, 0)


def _is_near_atm(strike: float, underlying_price: float) -> bool:
    if underlying_price <= 0:
        return False
    return abs(strike - underlying_price) / underlying_price <= 0.03


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
