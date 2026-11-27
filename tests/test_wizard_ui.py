"""Terminal UI is safe for redirected logs and remains bilingual."""
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "installer"))
import ui


class UI(unittest.TestCase):
    def test_plain_output_when_redirected(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            ui.banner("uk")
            ui.section(1, 7, "Connection", "Підключення", "uk")
            ui.message("[PASS] Ready")
            ui.summary({
                "installation": "Test", "home_assistant": "http://127.0.0.1:8123",
                "timezone": "Europe/Kyiv", "report_language": "uk",
                "smtp_enabled": True, "smtp_host": "smtp.example.com",
                "smtp_port": 587, "reports": {"daily": True, "weekly": False},
            }, "uk")
        self.assertNotIn("\x1b[", out.getvalue())
        self.assertIn("Підключення", out.getvalue())
        self.assertIn("Щоденні", out.getvalue())

    def test_color_opt_out(self):
        tty = type("FakeTTY", (), {"isatty": lambda self: True})()
        self.assertFalse(ui.color_enabled(tty, {"TERM": "xterm", "NO_COLOR": ""}))
        self.assertFalse(ui.color_enabled(tty, {"TERM": "dumb"}))
        self.assertTrue(ui.color_enabled(tty, {"TERM": "xterm-256color"}))

    def test_paint_only_when_enabled(self):
        self.assertEqual(ui.paint("abc", "32", False), "abc")
        self.assertEqual(ui.paint("abc", "32", True), "\x1b[32mabc\x1b[0m")

    def test_summary_never_includes_password(self):
        out = io.StringIO()
        with patch("sys.stdout", out):
            ui.summary({
                "installation": "Test", "home_assistant": "http://127.0.0.1:8123",
                "timezone": "Europe/Kyiv", "report_language": "en",
                "smtp_enabled": False, "smtp_host": "", "smtp_port": 587,
                "reports": {},
            }, "en")
        self.assertNotIn("password", out.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
