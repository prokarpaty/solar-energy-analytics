"""Verify SMTP authentication without sending email."""

import smtplib
import ssl


def check_smtp(settings):
    client = None

    try:
        client = smtplib.SMTP(
            settings["host"],
            settings["port"],
            timeout=15
        )

        client.ehlo()

        if not client.has_extn("starttls"):
            raise RuntimeError("STARTTLS required")

        client.starttls(
            context=ssl.create_default_context()
        )

        client.ehlo()

        client.login(
            settings["username"],
            settings["password"]
        )

    except Exception:
        raise RuntimeError(
            "SMTP connection or authentication failed"
        ) from None

    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
