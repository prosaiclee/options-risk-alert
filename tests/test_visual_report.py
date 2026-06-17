from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from options_risk_alert.engine import OptionsRiskEngine
from options_risk_alert.models import OptionFlowSnapshot
from options_risk_alert.put_details import PutDetailSnapshot
from options_risk_alert.visual_report import generate_visual_report, write_visual_report


def make_snapshot(day: int, symbol: str, put_premium: float, call_premium: float, iv30: float) -> OptionFlowSnapshot:
    return OptionFlowSnapshot(
        timestamp=datetime(2026, 6, 1, 14, 45) + timedelta(days=day),
        symbol=symbol,
        put_premium_bought=put_premium,
        call_premium_bought=call_premium,
        puts_bought=int(put_premium / 10),
        calls_bought=int(call_premium / 10),
        iv30=iv30,
        norm_25d_skew_30=1.0 + day * 0.05,
        dtx1=10,
        dtx2_5=20,
        dtx6_30=70,
        underlying_price=500 + day,
    )


class VisualReportTest(unittest.TestCase):
    def test_generate_visual_report_contains_charts_and_details(self) -> None:
        history = [
            make_snapshot(0, "SPY", 100_000, 90_000, 18.0),
            make_snapshot(1, "SPY", 110_000, 92_000, 18.5),
            make_snapshot(0, "QQQ", 150_000, 120_000, 22.0),
            make_snapshot(1, "QQQ", 160_000, 125_000, 22.5),
        ]
        current = [
            make_snapshot(2, "SPY", 220_000, 80_000, 21.0),
            make_snapshot(2, "QQQ", 280_000, 100_000, 25.0),
        ]
        engine = OptionsRiskEngine(history, min_history_points=1)
        report = engine.evaluate(current)
        details = [
            PutDetailSnapshot(
                timestamp=current[0].timestamp,
                symbol="QQQ",
                expiration="2026-07-17",
                days_to_expiry=33,
                strike_bucket="5-10% OTM",
                put_premium=1_250_000,
                put_volume=4200,
                open_interest=8100,
                avg_iv=24.5,
                avg_mid=3.2,
            )
        ]

        html = generate_visual_report(
            report=report,
            snapshots=history + current,
            engine=engine,
            put_details=details,
        )

        self.assertIn("ETF Options Risk Dashboard", html)
        self.assertIn("<svg", html)
        self.assertIn("Put premium trend", html)
        self.assertIn("Put Expiration / Strike Detail", html)
        self.assertIn("QQQ", html)
        self.assertIn("2026-07-17", html)

    def test_write_visual_report_creates_parent_directory(self) -> None:
        history = [make_snapshot(0, "SMH", 100_000, 90_000, 20.0)]
        current = [make_snapshot(1, "SMH", 120_000, 80_000, 21.0)]
        engine = OptionsRiskEngine(history, min_history_points=1)
        report = engine.evaluate(current)

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "nested" / "dashboard.html"
            write_visual_report(path, report=report, snapshots=history + current, engine=engine)
            self.assertTrue(path.exists())
            self.assertIn("SMH", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
