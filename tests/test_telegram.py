from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from options_risk_alert.telegram import multipart_form_data, read_env_file, truncate_caption, truncate_for_telegram


class TelegramTest(unittest.TestCase):
    def test_truncate_for_telegram(self) -> None:
        text = "x" * 5000
        truncated = truncate_for_telegram(text)
        self.assertLessEqual(len(truncated), 4096)
        self.assertTrue(truncated.endswith("... truncated"))

    def test_read_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / ".env"
            path.write_text('TELEGRAM_BOT_TOKEN="token"\nTELEGRAM_CHAT_ID=123\n', encoding="utf-8")
            values = read_env_file(path)
        self.assertEqual(values["TELEGRAM_BOT_TOKEN"], "token")
        self.assertEqual(values["TELEGRAM_CHAT_ID"], "123")

    def test_multipart_form_data_includes_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "dashboard.html"
            path.write_text("<html>ok</html>", encoding="utf-8")
            body, content_type = multipart_form_data(fields={"chat_id": "123", "caption": "report"}, files={"document": path})
        self.assertIn("multipart/form-data", content_type)
        self.assertIn(b'name="chat_id"', body)
        self.assertIn(b'filename="dashboard.html"', body)
        self.assertIn(b"<html>ok</html>", body)

    def test_truncate_caption(self) -> None:
        text = "x" * 1500
        truncated = truncate_caption(text)
        self.assertLessEqual(len(truncated), 1024)
        self.assertTrue(truncated.endswith("... truncated"))


if __name__ == "__main__":
    unittest.main()
