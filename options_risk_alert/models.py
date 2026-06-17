from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


CORE_SYMBOLS: dict[str, tuple[str, str]] = {
    "SPX": ("SP500", "equity_index"),
    "SPY": ("SP500", "equity_etf"),
    "NDX": ("NASDAQ", "equity_index"),
    "QQQ": ("NASDAQ", "equity_etf"),
    "SOXX": ("SEMICONDUCTOR", "semiconductor_etf"),
    "SMH": ("SEMICONDUCTOR", "semiconductor_etf"),
    "VIX": ("VOLATILITY", "volatility_index"),
    "^VIX": ("VOLATILITY", "volatility_index"),
}

LEVEL_ORDER = {
    "정상": 0,
    "관찰": 1,
    "주의": 2,
    "위험": 3,
}


def normalize_symbol(symbol: str) -> str:
    clean = symbol.strip().upper()
    if clean == "^VIX":
        return "VIX"
    return clean


@dataclass(frozen=True)
class OptionFlowSnapshot:
    timestamp: datetime
    symbol: str
    put_premium_bought: float = 0.0
    call_premium_bought: float = 0.0
    puts_bought: int = 0
    calls_bought: int = 0
    otm_put_oi: int = 0
    otm_call_oi: int = 0
    iv30: float = 0.0
    hv20: float = 0.0
    norm_25d_skew_30: float = 0.0
    net_option_delta: float = 0.0
    dtx1: int = 0
    dtx2_5: int = 0
    dtx6_30: int = 0
    underlying_price: float = 0.0
    underlying_change_pct: float = 0.0
    is_event_day: bool = False
    large_trade_count: int = 0
    total_trade_count: int = 0
    vix_front_month: float = 0.0
    vix_second_month: float = 0.0
    source_delay_minutes: int = 15
    source: str = ""
    underlying_group: str = ""
    asset_role: str = ""

    def __post_init__(self) -> None:
        symbol = normalize_symbol(self.symbol)
        object.__setattr__(self, "symbol", symbol)
        default_group, default_role = CORE_SYMBOLS.get(symbol, ("OTHER", "other"))
        if not self.underlying_group:
            object.__setattr__(self, "underlying_group", default_group)
        if not self.asset_role:
            object.__setattr__(self, "asset_role", default_role)

    @property
    def time_bucket(self) -> str:
        return self.timestamp.strftime("%H:%M")

    @property
    def is_vix(self) -> bool:
        return self.symbol == "VIX" or self.asset_role == "volatility_index"

    @property
    def put_call_premium_ratio(self) -> float:
        return safe_ratio(self.put_premium_bought, self.call_premium_bought)

    @property
    def call_put_premium_ratio(self) -> float:
        return safe_ratio(self.call_premium_bought, self.put_premium_bought)

    @property
    def otm_put_share(self) -> float:
        return safe_ratio(self.otm_put_oi, self.otm_put_oi + self.otm_call_oi)

    @property
    def short_dated_share(self) -> float:
        total = self.dtx1 + self.dtx2_5 + self.dtx6_30
        return safe_ratio(self.dtx1 + self.dtx2_5, total)

    @property
    def vix_term_spread(self) -> float:
        if not self.vix_front_month or not self.vix_second_month:
            return 0.0
        return self.vix_front_month - self.vix_second_month

    def metric_value(self, metric: str) -> float:
        value = getattr(self, metric)
        if callable(value):
            value = value()
        return float(value)

    def to_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        data["timestamp"] = self.timestamp.isoformat()
        data["put_call_premium_ratio"] = self.put_call_premium_ratio
        data["call_put_premium_ratio"] = self.call_put_premium_ratio
        data["otm_put_share"] = self.otm_put_share
        data["short_dated_share"] = self.short_dated_share
        data["vix_term_spread"] = self.vix_term_spread
        return data


@dataclass(frozen=True)
class Evidence:
    metric: str
    value: float
    baseline_mean: float | None
    z_score: float | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "value": self.value,
            "baseline_mean": self.baseline_mean,
            "z_score": self.z_score,
            "message": self.message,
        }


@dataclass(frozen=True)
class SymbolRiskReport:
    symbol: str
    group: str
    level: str
    score: int
    summary: str
    evidence: list[Evidence] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "group": self.group,
            "level": self.level,
            "score": self.score,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "caveats": self.caveats,
        }


@dataclass(frozen=True)
class PortfolioRiskReport:
    generated_at: datetime
    level: str
    score: int
    summary: str
    symbol_reports: list[SymbolRiskReport]
    data_delay_minutes: int
    watched_symbols: list[str]
    disclaimer: str = "투자 조언이 아니며, 15분 지연 옵션 플로우 기반의 이상 흐름 알림입니다."

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "level": self.level,
            "score": self.score,
            "summary": self.summary,
            "data_delay_minutes": self.data_delay_minutes,
            "watched_symbols": self.watched_symbols,
            "disclaimer": self.disclaimer,
            "symbol_reports": [report.to_dict() for report in self.symbol_reports],
        }


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0 if numerator == 0 else float("inf")
    return numerator / denominator
