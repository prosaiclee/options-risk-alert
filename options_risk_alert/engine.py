from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite, sqrt
from statistics import mean

from .models import Evidence, LEVEL_ORDER, OptionFlowSnapshot, PortfolioRiskReport, SymbolRiskReport


@dataclass(frozen=True)
class BaselineStats:
    mean: float
    stddev: float
    count: int


class OptionsRiskEngine:
    """Detect abnormal downside or volatility-hedge option demand."""

    def __init__(self, history: list[OptionFlowSnapshot], min_history_points: int = 10) -> None:
        self.history = history
        self.min_history_points = min_history_points
        self._by_symbol_bucket: dict[tuple[str, str], list[OptionFlowSnapshot]] = defaultdict(list)
        self._by_symbol: dict[str, list[OptionFlowSnapshot]] = defaultdict(list)
        for snapshot in history:
            self._by_symbol_bucket[(snapshot.symbol, snapshot.time_bucket)].append(snapshot)
            self._by_symbol[snapshot.symbol].append(snapshot)

    def evaluate(self, current: list[OptionFlowSnapshot]) -> PortfolioRiskReport:
        symbol_reports = [self.evaluate_symbol(snapshot) for snapshot in current]
        symbol_reports.sort(key=lambda report: (-LEVEL_ORDER[report.level], -report.score, report.symbol))
        cross_asset_score, cross_asset_messages = self._cross_asset_score(symbol_reports)
        strongest = max((report.score for report in symbol_reports), default=0)
        portfolio_score = strongest + cross_asset_score
        evidence_count = sum(len(report.evidence) for report in symbol_reports if report.level != "정상")
        level = self._level_from_score(portfolio_score, evidence_count)
        strongest_level = self._strongest_symbol_level(symbol_reports)
        if LEVEL_ORDER[strongest_level] > LEVEL_ORDER[level]:
            level = strongest_level
        summary = self._portfolio_summary(level, symbol_reports, cross_asset_messages)
        delay = max((snapshot.source_delay_minutes for snapshot in current), default=15)
        generated_at = max((snapshot.timestamp for snapshot in current), default=datetime.now(timezone.utc))
        disclaimer = self._disclaimer(current)
        return PortfolioRiskReport(
            generated_at=generated_at,
            level=level,
            score=portfolio_score,
            summary=summary,
            symbol_reports=symbol_reports,
            data_delay_minutes=delay,
            watched_symbols=[snapshot.symbol for snapshot in current],
            disclaimer=disclaimer,
        )

    def evaluate_symbol(self, snapshot: OptionFlowSnapshot) -> SymbolRiskReport:
        if snapshot.is_vix:
            return self._evaluate_vix(snapshot)
        return self._evaluate_downside_flow(snapshot)

    def baseline(self, snapshot: OptionFlowSnapshot, metric: str) -> BaselineStats | None:
        peers = self._by_symbol_bucket.get((snapshot.symbol, snapshot.time_bucket), [])
        if len(peers) < self.min_history_points:
            peers = self._by_symbol.get(snapshot.symbol, [])
        values = [peer.metric_value(metric) for peer in peers if isfinite(peer.metric_value(metric))]
        if len(values) < self.min_history_points:
            return None
        avg = mean(values)
        variance = sum((value - avg) ** 2 for value in values) / max(len(values) - 1, 1)
        return BaselineStats(mean=avg, stddev=sqrt(variance), count=len(values))

    def z_score(self, snapshot: OptionFlowSnapshot, metric: str) -> tuple[float | None, BaselineStats | None]:
        stats = self.baseline(snapshot, metric)
        if stats is None or stats.stddev <= 0:
            return None, stats
        return (snapshot.metric_value(metric) - stats.mean) / stats.stddev, stats

    def _evaluate_downside_flow(self, snapshot: OptionFlowSnapshot) -> SymbolRiskReport:
        score = 0
        evidence: list[Evidence] = []
        caveats: list[str] = []

        put_z, put_stats = self.z_score(snapshot, "put_premium_bought")
        if put_z is not None and put_z >= 3:
            score += 3
            evidence.append(self._evidence(snapshot, "put_premium_bought", put_stats, put_z, "풋 매수 프리미엄이 같은 시간대 기준선 대비 급증했습니다."))

        ratio_z, ratio_stats = self.z_score(snapshot, "put_call_premium_ratio")
        if ratio_z is not None and ratio_z >= 2.5 and snapshot.put_call_premium_ratio >= 1.5:
            score += 2
            evidence.append(self._evidence(snapshot, "put_call_premium_ratio", ratio_stats, ratio_z, "풋/콜 프리미엄 비율이 평소보다 높아 하방 수요가 우세합니다."))

        otm_z, otm_stats = self.z_score(snapshot, "otm_put_share")
        if otm_z is not None and otm_z >= 2:
            score += 1
            evidence.append(self._evidence(snapshot, "otm_put_share", otm_stats, otm_z, "외가격 풋 비중이 증가해 꼬리위험 헤지 수요가 보입니다."))

        iv_z, iv_stats = self.z_score(snapshot, "iv30")
        skew_z, skew_stats = self.z_score(snapshot, "norm_25d_skew_30")
        if iv_z is not None and skew_z is not None and iv_z >= 1.5 and skew_z >= 1.5:
            score += 2
            evidence.append(self._evidence(snapshot, "iv30", iv_stats, iv_z, "30일 내재변동성이 상승했습니다."))
            evidence.append(self._evidence(snapshot, "norm_25d_skew_30", skew_stats, skew_z, "풋 스큐가 함께 상승해 단순 거래량 증가보다 방어적 성격이 강합니다."))

        short_z, short_stats = self.z_score(snapshot, "short_dated_share")
        if short_z is not None and short_z >= 1.5 and snapshot.short_dated_share >= 0.45:
            score += 1
            evidence.append(self._evidence(snapshot, "short_dated_share", short_stats, short_z, "0DTE/단기 만기 거래 비중이 높아 단기 충격 헤지 가능성이 있습니다."))

        delta_z, delta_stats = self.z_score(snapshot, "net_option_delta")
        if delta_z is not None and delta_z <= -2:
            score += 1
            evidence.append(self._evidence(snapshot, "net_option_delta", delta_stats, delta_z, "옵션 순델타가 평소보다 더 음수로 치우쳤습니다."))

        if snapshot.is_event_day:
            caveats.append("주요 이벤트일에는 정상적인 사전 헤지 수요도 급증할 수 있습니다.")
        if snapshot.source == "yahoo":
            caveats.append("Yahoo Finance 옵션 체인 기반 추정치입니다. 체결 방향과 실제 매수 주도 여부는 확인할 수 없습니다.")

        level = self._symbol_level(score, evidence)
        if level == "위험" and snapshot.large_trade_count <= 1 and snapshot.total_trade_count <= 3:
            level = "주의"
            caveats.append("소수 대형 거래만으로 구성되어 위험 등급을 한 단계 낮췄습니다.")

        summary = self._symbol_summary(snapshot, level, evidence)
        return SymbolRiskReport(snapshot.symbol, snapshot.underlying_group, level, score, summary, evidence, caveats)

    def _evaluate_vix(self, snapshot: OptionFlowSnapshot) -> SymbolRiskReport:
        score = 0
        evidence: list[Evidence] = []
        caveats: list[str] = ["VIX는 주식 하방 베팅이 아니라 변동성 방향 베팅으로 해석합니다."]
        if snapshot.source == "yahoo":
            caveats.append("Yahoo Finance에서 VIX 옵션 체인이 안정적으로 제공되지 않을 수 있으므로 결과를 보조 지표로만 봅니다.")

        call_z, call_stats = self.z_score(snapshot, "call_premium_bought")
        if call_z is not None and call_z >= 3:
            score += 3
            evidence.append(self._evidence(snapshot, "call_premium_bought", call_stats, call_z, "VIX 콜 매수 프리미엄이 급증해 변동성 확대 헤지 수요가 보입니다."))

        call_put_z, call_put_stats = self.z_score(snapshot, "call_put_premium_ratio")
        if call_put_z is not None and call_put_z >= 2.5 and snapshot.call_put_premium_ratio >= 1.5:
            score += 2
            evidence.append(self._evidence(snapshot, "call_put_premium_ratio", call_put_stats, call_put_z, "VIX 콜/풋 프리미엄 비율이 높아 변동성 상승 베팅이 우세합니다."))

        if snapshot.vix_term_spread >= 0.5:
            score += 1
            evidence.append(Evidence("vix_term_spread", snapshot.vix_term_spread, None, None, "VIX 근월물이 차월물보다 높아 단기 스트레스 신호가 있습니다."))

        put_z, put_stats = self.z_score(snapshot, "put_premium_bought")
        if put_z is not None and put_z >= 3 and score < 3:
            evidence.append(self._evidence(snapshot, "put_premium_bought", put_stats, put_z, "VIX 풋 매수 급증은 변동성 하락 또는 공포 완화 베팅일 수 있습니다."))
            caveats.append("VIX 풋 급증만으로는 주식시장 위험 확대 신호로 보지 않습니다.")

        level = self._symbol_level(score, evidence)
        summary = self._symbol_summary(snapshot, level, evidence)
        return SymbolRiskReport(snapshot.symbol, snapshot.underlying_group, level, score, summary, evidence, caveats)

    def _evidence(
        self,
        snapshot: OptionFlowSnapshot,
        metric: str,
        stats: BaselineStats | None,
        z_score: float | None,
        message: str,
    ) -> Evidence:
        return Evidence(
            metric=metric,
            value=snapshot.metric_value(metric),
            baseline_mean=stats.mean if stats else None,
            z_score=z_score,
            message=message,
        )

    def _symbol_level(self, score: int, evidence: list[Evidence]) -> str:
        if score >= 6 and len(evidence) >= 3:
            return "위험"
        if score >= 3:
            return "주의"
        if score >= 1:
            return "관찰"
        return "정상"

    def _level_from_score(self, score: int, evidence_count: int) -> str:
        if score >= 8 and evidence_count >= 3:
            return "위험"
        if score >= 4:
            return "주의"
        if score >= 1:
            return "관찰"
        return "정상"

    def _cross_asset_score(self, reports: list[SymbolRiskReport]) -> tuple[int, list[str]]:
        messages: list[str] = []
        stressed_groups = {
            report.group
            for report in reports
            if report.group != "VOLATILITY" and LEVEL_ORDER[report.level] >= LEVEL_ORDER["주의"]
        }
        has_vix_stress = any(report.group == "VOLATILITY" and LEVEL_ORDER[report.level] >= LEVEL_ORDER["주의"] for report in reports)
        score = 0
        if len(stressed_groups) >= 3:
            score += 2
            messages.append("SP500, Nasdaq, 반도체 등 여러 축에서 동시에 방어적 옵션 수요가 관측됩니다.")
        elif len(stressed_groups) >= 2:
            score += 1
            messages.append("두 개 이상 핵심 그룹에서 하방 옵션 수요가 동시에 증가했습니다.")
        if has_vix_stress and stressed_groups:
            score += 1
            messages.append("VIX 변동성 확대 베팅과 주식/ETF 하방 헤지가 함께 나타납니다.")
        return score, messages

    def _symbol_summary(self, snapshot: OptionFlowSnapshot, level: str, evidence: list[Evidence]) -> str:
        if level == "정상":
            return f"{snapshot.symbol}: 같은 시간대 기준선 대비 뚜렷한 위험 옵션 플로우가 없습니다."
        lead = evidence[0].message if evidence else "비정상 옵션 플로우가 감지되었습니다."
        return f"{snapshot.symbol}: {level} - {lead}"

    def _portfolio_summary(
        self,
        level: str,
        reports: list[SymbolRiskReport],
        cross_asset_messages: list[str],
    ) -> str:
        active = [report for report in reports if report.level != "정상"]
        if not active:
            return "핵심 지수/ETF 옵션 플로우에서 위험 알림 기준을 넘는 흐름이 없습니다."
        symbols = ", ".join(report.symbol for report in active[:4])
        parts = [f"{symbols}에서 {level} 수준의 옵션 플로우 이상 신호가 감지되었습니다."]
        parts.extend(cross_asset_messages)
        parts.append("매수/매도 신호가 아니라 데이터 지연을 포함한 위험 알림으로 해석해야 합니다.")
        return " ".join(parts)

    def _disclaimer(self, snapshots: list[OptionFlowSnapshot]) -> str:
        if any(snapshot.source == "yahoo" for snapshot in snapshots):
            return "투자 조언이 아니며, Yahoo Finance/yfinance 옵션 체인 기반의 개인 실험용 추정 알림입니다. 체결 방향, 매수 주도 여부, 데이터 안정성은 보장되지 않습니다."
        return "투자 조언이 아니며, 15분 지연 옵션 플로우 기반의 이상 흐름 알림입니다."

    def _strongest_symbol_level(self, reports: list[SymbolRiskReport]) -> str:
        if not reports:
            return "정상"
        return max((report.level for report in reports), key=lambda level: LEVEL_ORDER[level])
