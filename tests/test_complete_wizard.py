import sys
import tempfile
import unittest
import yaml

from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "installer"))
sys.path.insert(0, str(ROOT / "scripts"))

from profile_wizard import configure_profile
from installation_config import load_installation
from smtp_check import check_smtp


class CompleteWizardTests(unittest.TestCase):

    def validate_profile(self, lang):
        profile = configure_profile(
            ROOT / "config/installation.example.yaml",
            lang=lang,
            ask=lambda _: "",
            show=lambda _: None
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "installation.yaml"
            path.write_text(
                yaml.safe_dump(profile, allow_unicode=True)
            )

            self.assertEqual(load_installation(path), profile)

        return profile

    def test_english_profile(self):
        profile = self.validate_profile("en")
        self.assertEqual(
            profile["installation"]["name"],
            "Home Solar Installation"
        )

    def test_ukrainian_profile(self):
        profile = self.validate_profile("uk")
        self.assertEqual(
            profile["installation"]["name"],
            "Домашня сонячна станція"
        )

    def settings(self):
        return {
            "host": "smtp.example.invalid",
            "port": 587,
            "username": "test@example.invalid",
            "password": "SYNTHETIC_TEST_SECRET"
        }

    def test_smtp_authentication(self):
        client = MagicMock()
        client.has_extn.return_value = True

        with patch(
            "smtp_check.smtplib.SMTP",
            return_value=client
        ):
            check_smtp(self.settings())

        client.starttls.assert_called_once()
        client.login.assert_called_once()
        client.close.assert_called_once()
        client.send_message.assert_not_called()
        client.sendmail.assert_not_called()

    def test_smtp_requires_tls(self):
        client = MagicMock()
        client.has_extn.return_value = False

        with patch(
            "smtp_check.smtplib.SMTP",
            return_value=client
        ):
            with self.assertRaises(RuntimeError):
                check_smtp(self.settings())

        client.login.assert_not_called()
        client.close.assert_called_once()

    def test_smtp_failure_confidentiality(self):
        client = MagicMock()
        client.has_extn.return_value = True
        client.login.side_effect = RuntimeError(
            "SYNTHETIC_TEST_SECRET"
        )

        with patch(
            "smtp_check.smtplib.SMTP",
            return_value=client
        ):
            with self.assertRaises(RuntimeError) as ctx:
                check_smtp(self.settings())

        self.assertNotIn(
            "SYNTHETIC_TEST_SECRET",
            str(ctx.exception)
        )

        client.close.assert_called_once()
