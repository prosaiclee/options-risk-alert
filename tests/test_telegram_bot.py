from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from options_risk_alert.telegram_bot import answer_question, read_offset, write_offset


class TelegramBotTest(unittest.TestCase):
    def test_help_question(self) -> None:
        answer = answer_question("도움말", "unused.csv")
        self.assertIn("Options Risk Alert Bot", answer)

    def test_offset_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "offset.txt"
            self.assertIsNone(read_offset(path))
            write_offset(path, 42)
            self.assertEqual(read_offset(path), 42)


if __name__ == "__main__":
    unittest.main()
