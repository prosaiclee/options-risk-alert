from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from options_risk_alert.put_details import PutDetailSnapshot, latest_put_detail_summary, load_put_details, write_put_details
from options_risk_alert.yahoo_provider import build_put_detail_snapshots


class PutDetailsTest(unittest.TestCase):
    def test_build_put_detail_snapshots(self) -> None:
        details = build_put_detail_snapshots(
            "QQQ",
            100,
            "2026-07-17",
            [
                {"strike": 96, "bid": 1, "ask": 1.2, "volume": 10, "openInterest": 100, "impliedVolatility": 0.2},
                {"strike": 90, "bid": 0.5, "ask": 0.7, "volume": 20, "openInterest": 200, "impliedVolatility": 0.3},
            ],
            timestamp=datetime(2026, 6, 13, tzinfo=timezone.utc),
        )
        buckets = {detail.strike_bucket for detail in details}
        self.assertIn("0-5% OTM", buckets)
        self.assertIn("10-20% OTM", buckets)

    def test_write_load_and_summary(self) -> None:
        detail = PutDetailSnapshot(
            datetime(2026, 6, 13, tzinfo=timezone.utc),
            "QQQ",
            "2026-07-17",
            34,
            "5-10% OTM",
            1234,
            10,
            100,
            25,
            1.2,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "details.csv"
            write_put_details(path, [detail])
            loaded = load_put_details(path)
            summary = latest_put_detail_summary(path)
        self.assertEqual(len(loaded), 1)
        self.assertIn("QQQ", summary)


if __name__ == "__main__":
    unittest.main()
