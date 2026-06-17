from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from options_risk_alert.market_calendar import is_us_market_trading_day, is_us_regular_market_open


NY = ZoneInfo("America/New_York")


class MarketCalendarTest(unittest.TestCase):
    def test_regular_weekday_session_is_open(self) -> None:
        self.assertTrue(is_us_regular_market_open(datetime(2026, 5, 27, 10, 0, tzinfo=NY)))

    def test_weekend_is_closed(self) -> None:
        self.assertFalse(is_us_regular_market_open(datetime(2026, 5, 31, 10, 0, tzinfo=NY)))

    def test_weekday_before_open_is_closed(self) -> None:
        self.assertFalse(is_us_regular_market_open(datetime(2026, 5, 27, 8, 0, tzinfo=NY)))
        self.assertTrue(is_us_market_trading_day(datetime(2026, 5, 27, 8, 0, tzinfo=NY)))

    def test_us_market_holiday_is_closed(self) -> None:
        self.assertFalse(is_us_regular_market_open(datetime(2026, 7, 3, 10, 0, tzinfo=NY)))
        self.assertFalse(is_us_market_trading_day(datetime(2026, 7, 3, 10, 0, tzinfo=NY)))

    def test_weekend_is_not_trading_day(self) -> None:
        self.assertFalse(is_us_market_trading_day(datetime(2026, 5, 31, 10, 0, tzinfo=NY)))


if __name__ == "__main__":
    unittest.main()
