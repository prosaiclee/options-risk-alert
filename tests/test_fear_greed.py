from __future__ import annotations

import unittest

from datetime import datetime, timezone

from options_risk_alert.fear_greed import (
    FearGreedIndex,
    classify_fear_greed,
    fetch_with_fear_and_greed_package,
    format_fear_greed,
    korean_rating,
    one_year_position,
    parse_fear_greed_payload,
)


class FearGreedTest(unittest.TestCase):
    def test_classification(self) -> None:
        self.assertEqual(classify_fear_greed(10), "Extreme Fear")
        self.assertEqual(classify_fear_greed(35), "Fear")
        self.assertEqual(classify_fear_greed(50), "Neutral")
        self.assertEqual(classify_fear_greed(65), "Greed")
        self.assertEqual(classify_fear_greed(90), "Extreme Greed")

    def test_parse_cnn_like_payload(self) -> None:
        parsed = parse_fear_greed_payload(
            {
                "fear_and_greed": {
                    "score": 17,
                    "rating": "extreme_fear",
                    "timestamp": 1781097600000,
                },
                "fear_and_greed_historical": {
                    "data": [{"y": 10}, {"y": 20}, {"y": 30}, {"y": 40}],
                },
            }
        )
        self.assertEqual(parsed.value, 17)
        self.assertEqual(parsed.rating, "Extreme Fear")
        self.assertEqual(parsed.one_year_percentile, 25)
        self.assertIsNotNone(parsed.timestamp)

    def test_format_unavailable(self) -> None:
        message = format_fear_greed(FearGreedIndex(None, "unavailable", None, error="blocked"))
        self.assertIn("조회 실패", message)

    def test_package_result_conversion(self) -> None:
        class FakePackage:
            @staticmethod
            def get():
                class Result:
                    value = 72.5
                    description = "greed"
                    last_update = datetime(2026, 6, 10, 11, 14, tzinfo=timezone.utc)

                return Result()

        import sys

        original = sys.modules.get("fear_and_greed")
        sys.modules["fear_and_greed"] = FakePackage
        try:
            result = fetch_with_fear_and_greed_package()
        finally:
            if original is None:
                del sys.modules["fear_and_greed"]
            else:
                sys.modules["fear_and_greed"] = original

        self.assertEqual(result.value, 72.5)
        self.assertEqual(result.rating, "Greed")

    def test_korean_rating_and_position_format(self) -> None:
        self.assertEqual(korean_rating("Extreme Fear"), "극단적 공포")
        index = FearGreedIndex(34, "Fear", None, one_year_percentile=18, one_year_min=3, one_year_max=82)
        self.assertIn("34 / 100 / 공포 / 1년 내 하위 18%", format_fear_greed(index))

    def test_one_year_position(self) -> None:
        position = one_year_position({"fear_and_greed_historical": {"data": [{"y": 10}, {"y": 20}, {"y": 30}]}}, 20)
        self.assertAlmostEqual(position["one_year_percentile"], 66.66666666666666)


if __name__ == "__main__":
    unittest.main()
