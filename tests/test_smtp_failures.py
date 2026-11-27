import os, sys, ssl, smtplib, unittest, tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import send_report as mail

class SMTPFailures(unittest.TestCase):
    def test_pre_submission(self):
        for exc in (OSError(), TimeoutError(), ConnectionRefusedError(), smtplib.SMTPServerDisconnected()):
            self.assertEqual(mail.classify_smtp(exc, False), 'retry')
    def test_auth(self):
        self.assertEqual(mail.classify_smtp(smtplib.SMTPAuthenticationError(535,b'bad'),False),'failed')
    def test_tls(self):
        self.assertEqual(mail.classify_smtp(ssl.SSLCertVerificationError(),False),'failed')
    def test_data(self):
        for code, outcome in [(421,'retry'),(450,'retry'),(451,'retry'),(452,'retry'),(550,'failed')]:
            self.assertEqual(mail.classify_smtp(smtplib.SMTPDataError(code,b'x'),True),outcome)
    def test_recipients(self):
        for codes,outcome in [([450,451],'retry'),([450,550],'failed'),([550],'failed')]:
            exc=smtplib.SMTPRecipientsRefused({str(i):(c,b'x') for i,c in enumerate(codes)})
            self.assertEqual(mail.classify_smtp(exc,True),outcome)
    def test_uncertain(self):
        for exc in (TimeoutError(), OSError(), smtplib.SMTPServerDisconnected()):
            self.assertEqual(mail.classify_smtp(exc,True),'unknown')
    def test_disabled(self):
        with patch.dict(os.environ,{'SMTP_ENABLED':'false'}), patch.object(mail.smtplib,'SMTP') as smtp:
            with self.assertRaises(mail.DeliveryError) as ctx: mail.send_report('x')
            self.assertEqual(ctx.exception.outcome,'failed'); smtp.assert_not_called()
    def test_preparation(self):
        with patch.dict(os.environ,{'SMTP_ENABLED':'true'}), patch.object(mail,'build_message',side_effect=FileNotFoundError()), patch.object(mail.smtplib,'SMTP') as smtp:
            with self.assertRaises(mail.DeliveryError) as ctx: mail.send_report('x')
            self.assertEqual(ctx.exception.outcome,'failed'); smtp.assert_not_called()
    def test_submission(self):
        with tempfile.TemporaryDirectory() as directory:
            password = Path(directory) / "smtp_password"
            password.write_text("synthetic-password")
            password.chmod(0o600)

            env = {
                "SMTP_ENABLED": "true",
                "SMTP_USERNAME": "test",
                "SMTP_PASSWORD_FILE": str(password),
                "SMTP_HOST": "test",
                "SMTP_PORT": "587"
            }

            for refused, outcome in [
                ({}, None),
                ({"x": (450, b"x")}, "unknown")
            ]:
                with patch.dict(os.environ, env), \
                     patch.object(mail, "build_message") as build, \
                     patch.object(mail, "PrivateFileHandler"), \
                     patch.object(mail.logging, "getLogger"), \
                     patch.object(mail.smtplib, "SMTP") as smtp:

                    build.return_value = {
                        "From": "test@example.invalid",
                        "Message-ID": "<test>"
                    }

                    smtp.return_value.send_message.return_value = refused

                    if outcome:
                        with self.assertRaises(mail.DeliveryError) as ctx:
                            mail.send_report("x")
                        self.assertEqual(ctx.exception.outcome, outcome)
                    else:
                        mail.send_report("x")

                    smtp.return_value.login.assert_called_once_with(
                        "test", "synthetic-password"
                    )

                    smtp.return_value.starttls.assert_called_once()
                    smtp.return_value.close.assert_called_once()

    def test_insecure_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            password = Path(directory) / "smtp_password"
            password.write_text("synthetic-password")
            password.chmod(0o644)

            env = {
                "SMTP_ENABLED": "true",
                "SMTP_USERNAME": "test",
                "SMTP_PASSWORD_FILE": str(password),
                "SMTP_HOST": "test",
                "SMTP_PORT": "587"
            }

            with patch.dict(os.environ, env), \
                 patch.object(mail, "build_message") as build, \
                 patch.object(mail, "PrivateFileHandler"), \
                 patch.object(mail.smtplib, "SMTP") as smtp:

                build.return_value = {
                    "From": "test@example.invalid",
                    "Message-ID": "<test>"
                }

                with self.assertRaises(mail.DeliveryError) as ctx:
                    mail.send_report("x")

                self.assertEqual(ctx.exception.outcome, "failed")
                self.assertNotIn(
                    "synthetic-password",
                    str(ctx.exception)
                )
                smtp.assert_not_called()

    def test_authentication_error_sanitization(self):
        marker = "SYNTHETIC_PASSWORD_LEAK_MARKER"

        with tempfile.TemporaryDirectory() as directory:
            password = Path(directory) / "smtp_password"
            password.write_text(marker)
            password.chmod(0o600)

            env = {
                "SMTP_ENABLED": "true",
                "SMTP_USERNAME": "test",
                "SMTP_PASSWORD_FILE": str(password),
                "SMTP_HOST": "test",
                "SMTP_PORT": "587"
            }

            with patch.dict(os.environ, env), \
                 patch.object(mail, "build_message") as build, \
                 patch.object(mail, "PrivateFileHandler"), \
                 patch.object(mail.logging, "getLogger") as logger, \
                 patch.object(mail.smtplib, "SMTP") as smtp:

                build.return_value = {
                    "From": "test@example.invalid",
                    "Message-ID": "<test>"
                }

                smtp.return_value.login.side_effect = (
                    smtplib.SMTPAuthenticationError(
                        535, marker.encode()
                    )
                )

                with self.assertRaises(mail.DeliveryError) as ctx:
                    mail.send_report("x")

                self.assertEqual(ctx.exception.outcome, "failed")
                self.assertNotIn(marker, str(ctx.exception))
                self.assertNotIn(marker, str(logger.mock_calls))

                smtp.return_value.send_message.assert_not_called()
                smtp.return_value.close.assert_called_once()
