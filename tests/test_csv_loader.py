from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from options_risk_alert.csv_loader import load_snapshots, write_snapshots
from options_risk_alert.models import OptionFlowSnapshot


class CsvLoaderTest(unittest.TestCase):
    def test_write_and_load_snapshots(self) -> None:
        snapshot = OptionFlowSnapshot(
            timestamp=datetime(2026, 5, 26, 18, 45, tzinfo=timezone.utc),
            symbol="SPY",
            put_premium_bought=123,
            call_premium_bought=45,
            source="yahoo",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "snapshots.csv"
            write_snapshots(path, [snapshot])
            loaded = load_snapshots(path)

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].symbol, "SPY")
        self.assertEqual(loaded[0].source, "yahoo")
        self.assertEqual(loaded[0].put_premium_bought, 123)


if __name__ == "__main__":
    unittest.main()
