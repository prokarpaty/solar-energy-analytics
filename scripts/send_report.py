import os
import ssl
import smtplib
import argparse
import logging

from pathlib import Path
from secret_reader import read_secret
from report_loader import load_validated_report
from report_integrity import (
    IntegrityError,
    load_manifest,
    verify_manifest
)
from attachment_security import read_attachment
from email_security import MAX_RAW_ATTACHMENT_BYTES
from report_validation import ReportValidationError
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from email_security import (
    validate_mailbox,
    validate_recipients,
    validate_subject,
    validate_attachment_filename,
    validate_attachment_size,
)
from email.utils import formatdate, make_msgid
from html import escape
from localization import Localizer
from secure_files import write_private, PrivateFileHandler


TZ = ZoneInfo(os.getenv("REPORT_TIMEZONE", "Europe/Kyiv"))


ENERGY_NAMES = {'production': ('production', '#d97706'),
 'consumption': ('consumption', '#2563eb'),
 'grid_import': ('grid_import', '#ea580c'),
 'grid_export': ('grid_export', '#16a34a'),
 'battery_charge': ('battery_charge', '#0891b2'),
 'battery_discharge': ('battery_discharge', '#9333ea'),
 'inverter_losses': ('inverter_losses', '#64748b')}

STATUSES = {'complete': 'complete',
 'recovered': 'recovered',
 'partial': 'partial',
 'unavailable': 'unavailable'}

logging.Formatter.converter = __import__("time").gmtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("solar-reports-mail")


def fmt(value, decimals=1):
    if value is None:
        return "—"

    return (
        f"{value:,.{decimals}f}"
        .replace(",", " ")
        .replace(".", ",")
    )


def build_email(data, language=None):
    loc = Localizer(language)
    t = loc.text
    fmt = loc.number
    unit = t("unit.energy")
    tz = ZoneInfo(data.get("timezone") or str(TZ))

    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    last = end.date() - timedelta(days=1)

    period = f"{start:%d.%m.%Y} — {last:%d.%m.%Y}"

    title = t("report." + data["report_type"])

    subject = f"☀ {t('email.t0')} | {title} | {period}"

    rows = []
    plain_rows = []
    warnings = list(data.get("configuration_warnings", []))

    for key, (_, color) in ENERGY_NAMES.items():
        label = t("energy." + key)

        if key not in data["energy"]:
            continue
        item = data["energy"].get(key, {})

        value = fmt(item.get("total"), 1)

        coverage = fmt(item.get("coverage"), 2)

        status = t("status." + item["status"]) if item.get("status") in STATUSES else t("email.t1")

        rows.append(f"""
        <tr>
            <td style="padding:12px;border-bottom:1px solid #e2e8f0">
                {escape(label)}
            </td>
            <td style="padding:12px;text-align:right;
                       font-weight:bold;color:{color};
                       border-bottom:1px solid #e2e8f0">
                {escape(value)}
            </td>
            <td style="padding:12px;text-align:right;
                       border-bottom:1px solid #e2e8f0">
                {escape(coverage)}%
            </td>
        </tr>
        """)

        plain_rows.append(
            f"{label}: {value} {unit} "
            f"({coverage}%; {status})"
        )

        if item.get("status") != "complete":
            warnings.append(f"{label}: {status}")

    energy = data["energy"]

    imported = energy.get("grid_import", {}).get("total")
    exported = energy.get("grid_export", {}).get("total")

    net_text = ""

    if imported is not None and exported is not None:

        net = exported - imported

        if net >= 0:
            net_text = (
                f"{t('email.t2')}: {fmt(net, 1)} {unit}"
            )
        else:
            net_text = (
                f"{t('email.t3')}: {fmt(abs(net), 1)} {unit}"
            )

    warning_html = ""

    if warnings:
        warning_html = f"""
        <div style="background:#fffbeb;
                    border-left:4px solid #d97706;
                    padding:16px;margin:20px 0">
            <strong>{escape(t('email.t4'))}</strong>
            <ul>
        """

        warning_html += "".join(
            f"<li>{escape(w)}</li>" for w in warnings
        )

        warning_html += "</ul></div>"

    now = datetime.now(tz)

    html = f"""
    <!DOCTYPE html>
    <html lang="{loc.language}">
    <head>
        <meta charset="UTF-8">
    </head>
    <body style="margin:0;background:#f1f5f9;
                 font-family:Arial,sans-serif;color:#10233d">

    <div style="max-width:680px;margin:20px auto;
                background:white">

        <div style="background:#10233d;color:white;
                    padding:30px">

            <div style="color:#facc15;font-size:11px;
                        letter-spacing:2px">
                DEYE / SOLAR ENERGY ANALYTICS
            </div>

            <h1 style="font-size:26px;margin:12px 0">
                ☀ {escape(t('email.t5'))}
            </h1>

            <p>{escape(title)}</p>

            <p style="color:#cbd5e1">{escape(period)}</p>

        </div>

        <div style="padding:24px">

            <p>{escape(t('email.t6'))}</p>

            <p>
                {escape(t('email.t7'))}
            </p>

            <h2>{escape(t('email.t8'))}</h2>

            <table style="width:100%;border-collapse:collapse;
                          font-size:14px">

                <tr style="background:#10233d;color:white">
                    <th style="padding:12px;text-align:left">
                        {escape(t('email.t9'))}
                    </th>
                    <th style="padding:12px;text-align:right">
                        {escape(unit)}
                    </th>
                    <th style="padding:12px;text-align:right">
                        {escape(t('email.t10'))}
                    </th>
                </tr>

                {''.join(rows)}

            </table>

            <p style="font-size:16px;font-weight:bold">
                {escape(net_text)}
            </p>

            {warning_html}

            <h2>{escape(t('email.t11'))}</h2>

            <p>{escape(t('email.t12'))}</p>

            <ul>
                <li>{escape(t('email.t13'))}</li>
                <li>{escape(t('email.t14'))}</li>
            </ul>

            <p>
                {escape(t('email.t15'))}
            </p>

        </div>

        <div style="background:#f8fafc;padding:20px;
                    color:#64748b;font-size:12px">

            <p>{escape(t('email.t16'))}</p>

            <p>{escape(t('email.t17'))} {now:%d.%m.%Y %H:%M}</p>

            <p>{escape(t('email.t18'))} {escape(str(tz))}</p>

            <p>
                {escape(t('email.t19'))}
            </p>

        </div>

    </div>

    </body>
    </html>
    """

    plain = "\n".join([
        title,
        period,
        "",
        *plain_rows,
        "",
        net_text,
        "",
        *warnings,
        "",
        t("email.t20"),
        "Solar Energy Analytics"
    ])

    return subject, plain, html


def build_message(source, language=None, preview=False):
    source = Path(source)

    language = Localizer(language).language

    data, dataset_identity = load_validated_report(
        source,
        with_identity=True
    )

    manifest = load_manifest(source)

    attachments = [
        (source.with_suffix(".pdf"), "application", "pdf"),
        (source.with_suffix(".html"), "text", "html")
    ]

    verified_attachments = []
    remaining = MAX_RAW_ATTACHMENT_BYTES

    for path, maintype, subtype in attachments:

        filename = validate_attachment_filename(path.name)

        payload = read_attachment(
            path,
            maximum=remaining
        )

        remaining -= len(payload)

        verified_attachments.append(
            (filename, maintype, subtype, payload)
        )

    validate_attachment_size(
        len(payload)
        for _, _, _, payload in verified_attachments
    )

    # Verify the exact attachment bytes that will be
    # included in the MIME message. Never reopen attachments.
    attachment_payloads = {
        subtype: payload
        for _, _, subtype, payload in verified_attachments
    }

    if not verify_manifest(
        manifest,
        data,
        dataset_identity,
        language,
        pdf_bytes=attachment_payloads["pdf"],
        html_bytes=attachment_payloads["html"]
    ):
        raise IntegrityError("Report integrity verification failed")

    logger.info("Report bundle integrity verified")

    if preview:
        sender = validate_mailbox("preview@example.invalid")
        recipients = validate_recipients("preview@example.invalid")
    else:
        sender = validate_mailbox(os.environ["SMTP_FROM"])
        recipients = validate_recipients(os.environ["SMTP_TO"])
    subject, plain, html = build_email(data, language)

    message = EmailMessage()

    message["Subject"] = validate_subject(subject)
    message["From"] = sender
    message["To"] = recipients
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(
        domain="solar-reports.local"
    )

    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    for filename, maintype, subtype, payload in verified_attachments:

        message.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=filename
        )

        logger.info(
            "Attachment: %s | %.2f MB",
            filename,
            len(payload) / 1024**2
        )

    message_size = len(message.as_bytes())

    if message_size > 24_000_000:
        raise RuntimeError(
            "Encoded email exceeds configured size limit"
        )

    logger.info(
        "Total encoded email size: %.2f MB",
        message_size / 1024**2
    )

    return message


def preview_report(source, language=None):
    message = build_message(source, language, preview=True)
    path = Path(source).with_suffix(".eml")
    write_private(path, message.as_bytes(), exclusive=True)
    return path


class DeliveryError(RuntimeError):
    def __init__(self, outcome, reason):
        super().__init__(reason)
        self.outcome = outcome


DELIVERY_EXIT = {"retry": 20, "failed": 21, "unknown": 22}


def classify_smtp(exc, submitting):
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [value[0] for value in exc.recipients.values()]
        return "retry" if codes and all(400 <= c < 500 for c in codes) else "failed"
    if isinstance(exc, ssl.SSLCertVerificationError):
        return "failed"
    if isinstance(exc, smtplib.SMTPResponseException):
        if not submitting or isinstance(exc, (smtplib.SMTPDataError, smtplib.SMTPSenderRefused)):
            return "retry" if 400 <= exc.smtp_code < 500 else "failed"
        return "unknown"
    if submitting:
        return "unknown"
    if isinstance(exc, (smtplib.SMTPNotSupportedError, ssl.SSLError)):
        return "failed"
    if isinstance(exc, (OSError, smtplib.SMTPServerDisconnected)):
        return "retry"
    return "failed"


def send_report(source, language=None):
    if os.environ.get("SMTP_ENABLED", "").lower() != "true":
        raise DeliveryError("failed", "SMTP delivery is disabled")
    handler = None
    smtp = None
    submitting = False
    try:
        try:
            source = Path(source)
            message = build_message(source, language)
            username = os.environ["SMTP_USERNAME"]
            password = read_secret(os.environ["SMTP_PASSWORD_FILE"])
            host = os.environ["SMTP_HOST"]
            port = int(os.environ["SMTP_PORT"])
            if not all((username.strip(), password, host.strip(), str(message["From"]).strip())) or not 1 <= port <= 65535:
                raise ValueError("Invalid SMTP settings")
            handler = PrivateFileHandler("/app/logs/email-delivery.log", encoding="utf-8")
            logging.getLogger().addHandler(handler)
        except Exception as exc:
            raise DeliveryError("failed", f"Email preparation failed ({type(exc).__name__})") from None
        try:
            smtp = smtplib.SMTP(host, port, timeout=60)
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.login(username, password)
            submitting = True
            refused = smtp.send_message(message)
            if refused:
                raise DeliveryError("unknown", "Partial recipient acceptance")
        except DeliveryError:
            raise
        except Exception as exc:
            raise DeliveryError(classify_smtp(exc, submitting), f"SMTP failure ({type(exc).__name__})") from None
        logger.info("SUCCESS | %s | Message-ID: %s", source.name, message["Message-ID"])
        print("\n=== REPORT ACCEPTED BY SMTP SERVER ===")
    finally:
        if smtp is not None:
            try:
                smtp.close()
            except Exception:
                pass
        if handler is not None:
            logging.getLogger().removeHandler(handler)
            handler.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Send Solar Reports via Gmail"
    )

    parser.add_argument(
        "source",
        help="Path to report JSON file"
    )

    parser.add_argument("--language", choices=("en", "uk"))
    parser.add_argument("--preview", action="store_true", help="Write local EML without SMTP")
    args = parser.parse_args()

    try:
        if args.preview:
            print(preview_report(args.source, args.language))
        else:
            send_report(args.source, args.language)
    except DeliveryError as exc:
        logger.error("Delivery %s: %s", exc.outcome, exc)
        raise SystemExit(DELIVERY_EXIT[exc.outcome])
    except ReportValidationError:
        logger.error("Report dataset validation failed")
        raise SystemExit(2)
    except IntegrityError:
        logger.error("Report bundle integrity verification failed")
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception:
        logger.error("Email operation failed")
        raise SystemExit(1)
