from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from options_risk_alert import OptionFlowSnapshot, OptionsRiskEngine


def make_snapshot(
    day_offset: int,
    symbol: str,
    *,
    put_premium_bought: float = 100.0,
    call_premium_bought: float = 90.0,
    puts_bought: int = 100,
    calls_bought: int = 95,
    otm_put_oi: int = 1000,
    otm_call_oi: int = 1200,
    iv30: float = 20.0,
    skew: float = 1.0,
    net_delta: float = -100.0,
    dtx1: int = 20,
    dtx2_5: int = 20,
    dtx6_30: int = 160,
    large_trade_count: int = 4,
    total_trade_count: int = 20,
    vix_front_month: float = 18.0,
    vix_second_month: float = 19.0,
) -> OptionFlowSnapshot:
    return OptionFlowSnapshot(
        timestamp=datetime(2026, 5, 1, 14, 45) + timedelta(days=day_offset),
        symbol=symbol,
        put_premium_bought=put_premium_bought,
        call_premium_bought=call_premium_bought,
        puts_bought=puts_bought,
        calls_bought=calls_bought,
        otm_put_oi=otm_put_oi,
        otm_call_oi=otm_call_oi,
        iv30=iv30,
        hv20=16.0,
        norm_25d_skew_30=skew,
        net_option_delta=net_delta,
        dtx1=dtx1,
        dtx2_5=dtx2_5,
        dtx6_30=dtx6_30,
        large_trade_count=large_trade_count,
        total_trade_count=total_trade_count,
        vix_front_month=vix_front_month,
        vix_second_month=vix_second_month,
    )


class OptionsRiskEngineTest(unittest.TestCase):
    def baseline(self, symbols: list[str]) -> list[OptionFlowSnapshot]:
        history = []
        for symbol in symbols:
            for index in range(30):
                history.append(
                    make_snapshot(
                        index,
                        symbol,
                        put_premium_bought=100 + index,
                        call_premium_bought=90 + index,
                        otm_put_oi=1000 + index * 3,
                        otm_call_oi=1200,
                        iv30=20 + index * 0.05,
                        skew=1 + index * 0.01,
                        net_delta=-100 - index,
                        dtx1=20,
                        dtx2_5=20,
                        dtx6_30=160,
                    )
                )
        return history

    def test_downside_flow_generates_risk(self) -> None:
        engine = OptionsRiskEngine(self.baseline(["QQQ"]))
        report = engine.evaluate(
            [
                make_snapshot(
                    31,
                    "QQQ",
                    put_premium_bought=280,
                    call_premium_bought=55,
                    otm_put_oi=2500,
                    otm_call_oi=800,
                    iv30=25,
                    skew=1.8,
                    net_delta=-260,
                    dtx1=90,
                    dtx2_5=70,
                    dtx6_30=100,
                )
            ]
        )
        self.assertEqual(report.level, "위험")
        self.assertEqual(report.symbol_reports[0].level, "위험")
        self.assertGreaterEqual(len(report.symbol_reports[0].evidence), 3)

    def test_vix_put_surge_is_not_downside_risk_by_itself(self) -> None:
        engine = OptionsRiskEngine(self.baseline(["VIX"]))
        report = engine.evaluate(
            [
                make_snapshot(
                    31,
                    "VIX",
                    put_premium_bought=280,
                    call_premium_bought=50,
                    vix_front_month=18,
                    vix_second_month=19,
                )
            ]
        )
        self.assertNotEqual(report.level, "위험")
        self.assertIn("VIX 풋", report.symbol_reports[0].evidence[0].message)

    def test_cross_asset_confirmation_raises_portfolio_level(self) -> None:
        engine = OptionsRiskEngine(self.baseline(["SPY", "QQQ", "SOXX", "VIX"]))
        current = [
            make_snapshot(31, "SPY", put_premium_bought=260, call_premium_bought=65, iv30=24, skew=1.7, net_delta=-240),
            make_snapshot(31, "QQQ", put_premium_bought=260, call_premium_bought=65, iv30=24, skew=1.7, net_delta=-240),
            make_snapshot(31, "SOXX", put_premium_bought=260, call_premium_bought=65, iv30=24, skew=1.7, net_delta=-240),
            make_snapshot(31, "VIX", put_premium_bought=80, call_premium_bought=260, vix_front_month=21, vix_second_month=19),
        ]
        report = engine.evaluate(current)
        self.assertEqual(report.level, "위험")
        self.assertIn("여러 축", report.summary)

    def test_single_block_trade_caps_danger_to_caution(self) -> None:
        engine = OptionsRiskEngine(self.baseline(["QQQ"]))
        report = engine.evaluate(
            [
                make_snapshot(
                    31,
                    "QQQ",
                    put_premium_bought=300,
                    call_premium_bought=50,
                    otm_put_oi=2600,
                    otm_call_oi=700,
                    iv30=25,
                    skew=1.8,
                    net_delta=-280,
                    large_trade_count=1,
                    total_trade_count=1,
                )
            ]
        )
        self.assertEqual(report.symbol_reports[0].level, "주의")
        self.assertIn("소수 대형 거래", report.symbol_reports[0].caveats[0])


if __name__ == "__main__":
    unittest.main()
