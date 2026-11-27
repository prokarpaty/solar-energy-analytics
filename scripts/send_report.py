import os
import ssl
import json
import smtplib
import argparse
import logging

from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from localization import Localizer


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
                {value}
            </td>
            <td style="padding:12px;text-align:right;
                       border-bottom:1px solid #e2e8f0">
                {coverage}%
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
            <strong>{t('email.t4')}</strong>
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
                ☀ {t('email.t5')}
            </h1>

            <p>{title}</p>

            <p style="color:#cbd5e1">{period}</p>

        </div>

        <div style="padding:24px">

            <p>{t('email.t6')}</p>

            <p>
                {t('email.t7')}
            </p>

            <h2>{t('email.t8')}</h2>

            <table style="width:100%;border-collapse:collapse;
                          font-size:14px">

                <tr style="background:#10233d;color:white">
                    <th style="padding:12px;text-align:left">
                        {t('email.t9')}
                    </th>
                    <th style="padding:12px;text-align:right">
                        {unit}
                    </th>
                    <th style="padding:12px;text-align:right">
                        {t('email.t10')}
                    </th>
                </tr>

                {''.join(rows)}

            </table>

            <p style="font-size:16px;font-weight:bold">
                {escape(net_text)}
            </p>

            {warning_html}

            <h2>{t('email.t11')}</h2>

            <p>{t('email.t12')}</p>

            <ul>
                <li>{t('email.t13')}</li>
                <li>{t('email.t14')}</li>
            </ul>

            <p>
                {t('email.t15')}
            </p>

        </div>

        <div style="background:#f8fafc;padding:20px;
                    color:#64748b;font-size:12px">

            <p>{t('email.t16')}</p>

            <p>{t('email.t17')} {now:%d.%m.%Y %H:%M}</p>

            <p>{t('email.t18')} {escape(str(tz))}</p>

            <p>
                {t('email.t19')}
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

    if not source.is_file():
        raise FileNotFoundError(source)

    data = json.loads(
        source.read_text(encoding="utf-8")
    )

    attachments = [
        (source.with_suffix(".pdf"), "application", "pdf"),
        (source.with_suffix(".html"), "text", "html")
    ]

    for path, _, _ in attachments:
        if not path.is_file():
            raise FileNotFoundError(
                f"Report attachment missing: {path}"
            )

    recipients = [address.strip() for address in os.getenv("SMTP_TO", "").split(",") if address.strip()]
    if not preview and not recipients:
        raise RuntimeError("No SMTP recipients configured")
    subject, plain, html = build_email(data, language)

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = "preview@example.invalid" if preview else os.environ["SMTP_FROM"]
    message["To"] = "preview@example.invalid" if preview else ", ".join(recipients)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(
        domain="solar-reports.local"
    )

    message.set_content(plain)
    message.add_alternative(html, subtype="html")

    for path, maintype, subtype in attachments:

        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name
        )

        logger.info(
            "Attachment: %s | %.2f MB",
            path.name,
            path.stat().st_size / 1024**2
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
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
        handle.write(message.as_bytes())
    path.chmod(0o600)
    return path


def send_report(source, language=None):
    if os.environ.get("SMTP_ENABLED", "").lower() != "true":
        raise RuntimeError("SMTP delivery is disabled")
    logging.getLogger().addHandler(logging.FileHandler("/app/logs/email-delivery.log", encoding="utf-8"))
    source = Path(source)
    message = build_message(source, language)
    username = os.environ["SMTP_USERNAME"]
    password = Path(os.environ["SMTP_PASSWORD_FILE"]).read_text().strip()

    logger.info("Sending report: %s", source.name)

    with smtplib.SMTP(
        os.environ["SMTP_HOST"],
        int(os.environ["SMTP_PORT"]),
        timeout=60
    ) as smtp:

        smtp.ehlo()

        smtp.starttls(
            context=ssl.create_default_context()
        )

        smtp.ehlo()

        smtp.login(username, password)

        refused = smtp.send_message(message)

        if refused:
            raise RuntimeError(
                "One or more recipients were rejected"
            )

    logger.info(
        "SUCCESS | %s | Message-ID: %s",
        source.name,
        message["Message-ID"]
    )

    print("\n=== REPORT ACCEPTED BY GMAIL SMTP ===")


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
    except Exception:
        logger.exception("Email delivery failed")
        raise SystemExit(1)
