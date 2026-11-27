import sys
import io
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, MagicMock

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "installer")
)

import wizard
import sensor_wizard
import profile_wizard
import yaml

MARKER = "SYNTHETIC_ROLLBACK_SECRET"

class InstallerRollback(unittest.TestCase):

    def simulate_installation(self, fail_at=None,
                              failure=OSError):
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()

            template = (
                Path(__file__).resolve().parents[1]
                / "config/installation.example.yaml"
            )
            profile = yaml.safe_load(template.read_text())

            original_create = wizard.create_exclusive
            calls = []

            def create(path, content, mode=0o600):
                calls.append(path)

                if len(calls) == fail_at:
                    raise failure(MARKER)

                return original_create(
                    path, content, mode
                )

            answers = [
                "1",
                "http://127.0.0.1:8123",
                "y",
                "Europe/Kyiv",
                "1",
                "y", "08:00", "y", "08:00", "y", "08:00", "n", "y", "08:00",
                "y",
                "smtp.example.invalid",
                "587",
                "test@example.invalid",
                "test@example.invalid",
                "recipient@example.invalid",
                "n",
                "y"
            ]

            mapping = {
                "energy": {
                    "production":
                        "sensor.inverter_total_production",
                    "consumption":
                        "sensor.inverter_total_load_consumption"
                }
            }

            with patch.object(wizard, "ROOT", root), \
                 patch.object(sys, "argv", ["wizard.py"]), \
                 patch.object(wizard, "prompt",
                              side_effect=answers), \
                 patch.object(wizard, "hidden_input",
                              return_value=MARKER), \
                 patch.object(wizard, "rest_open",
                              return_value=MagicMock()), \
                 patch.object(wizard, "check_api"), \
                 patch.object(sensor_wizard, "discover",
                              return_value=([], [])), \
                 patch.object(sensor_wizard, "configure",
                              return_value=mapping), \
                 patch.object(profile_wizard, "configure_profile",
                              return_value=profile), \
                 patch.object(wizard, "create_exclusive",
                              side_effect=create), \
                 redirect_stdout(output), \
                 redirect_stderr(output):

                result = wizard.main()

            files = [
                root / ".env",
                root / "secrets/ha_token",
                root / "secrets/smtp_password",
                root / "config/sensors.yaml",
                root / "config/schedule.yaml",
                root / "config/installation.yaml"
            ]

            self.assertNotIn(
                MARKER, output.getvalue()
            )

            if fail_at is not None:
                expected = (
                    130 if failure is KeyboardInterrupt
                    else 2
                )

                self.assertEqual(result, expected)
                self.assertEqual(len(calls), fail_at)

                for path in files:
                    self.assertFalse(
                        path.exists(),
                        f"Residual file: {path.name}"
                    )

            else:
                self.assertEqual(result, 0)
                self.assertEqual(len(calls), 6)

                for path in files:
                    self.assertTrue(path.is_file())
                    self.assertEqual(
                        path.stat().st_mode & 0o777,
                        0o600
                    )

                for name in (
                    "secrets", "reports",
                    "logs", "state"
                ):
                    self.assertEqual(
                        (root / name).stat().st_mode & 0o777,
                        0o700
                    )

                for name in (
                    "ha_token", "smtp_password"
                ):
                    self.assertEqual(
                        (root / "secrets" / name)
                        .read_text().strip(),
                        MARKER
                    )

                self.assertNotIn(
                    MARKER,
                    (root / ".env").read_text()
                )

    def test_successful_private_installation(self):
        self.simulate_installation()

    def test_failure_creating_env(self):
        self.simulate_installation(1)

    def test_failure_creating_ha_token(self):
        self.simulate_installation(2)

    def test_failure_creating_smtp_password(self):
        self.simulate_installation(3)

    def test_failure_creating_sensor_mapping(self):
        self.simulate_installation(4)

    def test_failure_creating_schedule(self):
        self.simulate_installation(5)

    def test_failure_creating_installation_profile(self):
        self.simulate_installation(6)

    def test_interrupted_installation(self):
        self.simulate_installation(
            4, KeyboardInterrupt
        )

    def test_interrupted_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential"

            with patch.object(
                wizard.os,
                "fsync",
                side_effect=OSError(MARKER)
            ):
                with self.assertRaises(OSError):
                    wizard.create_exclusive(
                        path, MARKER
                    )

            self.assertFalse(path.exists())

    def test_existing_secret_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential"

            wizard.create_exclusive(
                path, "original"
            )

            with self.assertRaises(FileExistsError):
                wizard.create_exclusive(
                    path, MARKER
                )

            self.assertEqual(
                path.read_text(), "original"
            )


if __name__ == "__main__":
    unittest.main()
