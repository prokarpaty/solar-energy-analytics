import sys
import io
import json
import getpass
import warnings
import tempfile
import unittest
import traceback

from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "installer")
)

import wizard
import sensor_wizard

MARKER = "SYNTHETIC_INSTALLER_SECRET_MARKER"


class InstallerSecurity(unittest.TestCase):

    def run_wizard(self, language, error):
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(wizard, "ROOT", Path(tmp)), \
                 patch.object(sys, "argv", ["wizard.py"]), \
                 patch.object(wizard, "prompt",
                              return_value=language), \
                 patch.object(wizard, "rest_open",
                              side_effect=error), \
                 redirect_stdout(output), \
                 redirect_stderr(output):

                result = wizard.main()

            self.assertFalse(
                (Path(tmp) / ".env").exists()
            )

            self.assertFalse(
                (Path(tmp) / "secrets").exists()
            )

        self.assertNotIn(MARKER, output.getvalue())

        return result, output.getvalue()

    def test_english_exception(self):
        code, output = self.run_wizard(
            "1", RuntimeError(MARKER)
        )
        self.assertEqual(code, 2)
        self.assertIn(
            wizard.I18N["en"]["invalid"], output
        )
        self.assertIn("[INSTALLATION_ERROR]", output)

    def test_ukrainian_exception(self):
        code, output = self.run_wizard(
            "2", RuntimeError(MARKER)
        )
        self.assertEqual(code, 2)
        self.assertIn(
            wizard.I18N["uk"]["invalid"], output
        )
        self.assertIn("[INSTALLATION_ERROR]", output)

    def test_startup_keyboard_interrupt(self):
        with patch.object(sys, "argv", ["wizard.py"]), \
             patch.object(wizard, "prompt",
                          side_effect=KeyboardInterrupt), \
             redirect_stderr(io.StringIO()):

            self.assertEqual(wizard.main(), 130)

    def test_startup_eof(self):
        with patch.object(sys, "argv", ["wizard.py"]), \
             patch("builtins.input", side_effect=EOFError), \
             redirect_stderr(io.StringIO()):

            self.assertEqual(wizard.main(), 130)

    def test_invalid_language_confidentiality(self):
        output = io.StringIO()

        with patch.object(sys, "argv", ["wizard.py"]), \
             patch.object(wizard, "prompt",
                          return_value=MARKER), \
             redirect_stderr(output):

            self.assertEqual(wizard.main(), 2)

        self.assertNotIn(MARKER, output.getvalue())

    def test_hidden_input(self):
        with patch.object(
            wizard.getpass,
            "getpass",
            return_value=MARKER
        ):
            self.assertEqual(
                wizard.hidden_input("Password: "),
                MARKER
            )

    def test_insecure_terminal_rejected(self):
        def insecure_input(*args, **kwargs):
            warnings.warn(
                "Cannot disable terminal echo",
                getpass.GetPassWarning
            )
            self.fail("Visible input must not be reached")

        with patch.object(
            wizard.getpass,
            "getpass",
            side_effect=insecure_input
        ):
            with self.assertRaises(getpass.GetPassWarning):
                wizard.hidden_input("Password: ")

    def test_discovery_error_confidentiality(self):
        with patch.object(
            sensor_wizard,
            "rest_open",
            side_effect=RuntimeError(MARKER)
        ):
            with self.assertRaises(RuntimeError) as ctx:
                sensor_wizard.discover(
                    "http://127.0.0.1:8123",
                    MARKER
                )

        self.assertNotIn(MARKER, str(ctx.exception))
        self.assertNotIn(
            MARKER,
            "".join(traceback.format_exception(ctx.exception))
        )

    def test_discovery_cleanup_failure(self):
        ws = MagicMock()

        ws.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({
                "type": "auth_invalid",
                "message": MARKER
            })
        ]

        ws.close.side_effect = RuntimeError(MARKER)

        response = MagicMock()
        response.__enter__.return_value = io.StringIO("[]")

        with patch.object(
            sensor_wizard, "rest_open",
            return_value=response
        ), patch.object(
            sensor_wizard, "connect_websocket",
            return_value=ws
        ):
            with self.assertRaises(RuntimeError) as ctx:
                sensor_wizard.discover(
                    "http://127.0.0.1:8123",
                    MARKER
                )

        ws.close.assert_called_once()

        self.assertEqual(
            str(ctx.exception),
            "HA sensor discovery failed"
        )

        self.assertNotIn(
            MARKER,
            "".join(traceback.format_exception(ctx.exception))
        )


if __name__ == "__main__":
    unittest.main()
