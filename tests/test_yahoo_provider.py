from __future__ import annotations

import unittest
from datetime import datetime, timezone

from options_risk_alert.yahoo_provider import YahooExpirationRows, build_yahoo_snapshot


class YahooProviderTest(unittest.TestCase):
    def test_build_snapshot_from_option_rows(self) -> None:
        timestamp = datetime(2026, 5, 26, 18, 45, tzinfo=timezone.utc)
        chain = YahooExpirationRows(
            expiration="2026-05-29",
            puts=[
                {"strike": 515, "bid": 2.0, "ask": 2.2, "lastPrice": 2.1, "volume": 10, "openInterest": 100, "impliedVolatility": 0.22},
                {"strike": 500, "bid": 1.0, "ask": 1.2, "lastPrice": 1.1, "volume": 20, "openInterest": 200, "impliedVolatility": 0.25},
                {"strike": 540, "bid": 12.0, "ask": 12.4, "lastPrice": 12.2, "volume": 3, "openInterest": 40, "impliedVolatility": 0.20},
            ],
            calls=[
                {"strike": 525, "bid": 1.8, "ask": 2.0, "lastPrice": 1.9, "volume": 5, "openInterest": 80, "impliedVolatility": 0.18},
                {"strike": 550, "bid": 0.8, "ask": 1.0, "lastPrice": 0.9, "volume": 6, "openInterest": 120, "impliedVolatility": 0.19},
                {"strike": 510, "bid": 12.0, "ask": 12.5, "lastPrice": 12.2, "volume": 2, "openInterest": 30, "impliedVolatility": 0.17},
            ],
        )

        snapshot = build_yahoo_snapshot("SPY", 520, [chain], timestamp=timestamp)

        self.assertEqual(snapshot.source, "yahoo")
        self.assertEqual(snapshot.symbol, "SPY")
        self.assertAlmostEqual(snapshot.put_premium_bought, 4300.0)
        self.assertAlmostEqual(snapshot.call_premium_bought, 1490.0)
        self.assertEqual(snapshot.puts_bought, 30)
        self.assertEqual(snapshot.calls_bought, 11)
        self.assertEqual(snapshot.otm_put_oi, 300)
        self.assertEqual(snapshot.otm_call_oi, 200)
        self.assertEqual(snapshot.dtx2_5, 30)
        self.assertGreater(snapshot.iv30, 0)
        self.assertGreater(snapshot.norm_25d_skew_30, 0)


if __name__ == "__main__":
    unittest.main()
