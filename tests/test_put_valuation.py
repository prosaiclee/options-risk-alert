from __future__ import annotations

import unittest
from datetime import date, datetime, timezone

from options_risk_alert.models import OptionFlowSnapshot
from options_risk_alert.put_valuation import (
    build_put_value_candidates,
    historical_iv_values,
    percentile_rank,
    render_put_value_report,
    value_rating,
)


class PutValuationTest(unittest.TestCase):
    def test_build_put_value_candidates(self) -> None:
        rows = [
            {"strike": 95, "bid": 1.0, "ask": 1.2, "lastPrice": 1.1, "volume": 100, "openInterest": 500, "impliedVolatility": 0.20},
            {"strike": 90, "bid": 0.5, "ask": 0.7, "lastPrice": 0.6, "volume": 50, "openInterest": 800, "impliedVolatility": 0.18},
            {"strike": 99, "bid": 3.0, "ask": 3.4, "lastPrice": 3.2, "volume": 50, "openInterest": 200, "impliedVolatility": 0.25},
            {"strike": 70, "bid": 0.1, "ask": 0.2, "lastPrice": 0.15, "volume": 10, "openInterest": 100, "impliedVolatility": 0.30},
        ]
        candidates = build_put_value_candidates(
            "SMH",
            100,
            [("2026-07-17", rows)],
            current_date=date(2026, 6, 12),
            history_snapshots=[
                OptionFlowSnapshot(datetime(2026, 1, 1, tzinfo=timezone.utc), "SMH", iv30=15),
                OptionFlowSnapshot(datetime(2026, 2, 1, tzinfo=timezone.utc), "SMH", iv30=20),
                OptionFlowSnapshot(datetime(2026, 3, 1, tzinfo=timezone.utc), "SMH", iv30=25),
            ],
        )
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].symbol, "SMH")
        self.assertGreater(candidates[0].value_score, 0)
        self.assertIn(candidates[0].rating, {"저렴", "보통", "비쌈"})
        self.assertIsNotNone(candidates[0].one_year_iv_percentile)
        self.assertGreater(candidates[0].one_year_observations, 0)

    def test_percentile_and_rating(self) -> None:
        self.assertAlmostEqual(percentile_rank([10, 20, 30], 20), 66.66666666666666)
        self.assertEqual(value_rating(80), "저렴")
        self.assertEqual(value_rating(60), "보통")
        self.assertEqual(value_rating(40), "비쌈")

    def test_render_report(self) -> None:
        report = render_put_value_report({})
        self.assertIn("풋옵션 가치 스크리닝", report)

    def test_historical_iv_values_filters_to_one_year_and_symbol(self) -> None:
        values = historical_iv_values(
            [
                OptionFlowSnapshot(datetime(2025, 6, 11, tzinfo=timezone.utc), "SMH", iv30=10),
                OptionFlowSnapshot(datetime(2025, 6, 12, tzinfo=timezone.utc), "SMH", iv30=20),
                OptionFlowSnapshot(datetime(2026, 1, 1, tzinfo=timezone.utc), "QQQ", iv30=30),
                OptionFlowSnapshot(datetime(2026, 1, 1, tzinfo=timezone.utc), "SMH", iv30=40),
            ],
            "SMH",
            date(2026, 6, 12),
        )
        self.assertEqual(values, [20.0, 40.0])


if __name__ == "__main__":
    unittest.main()
