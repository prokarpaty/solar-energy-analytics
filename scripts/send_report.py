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


TZ = ZoneInfo(os.getenv("REPORT_TIMEZONE", "Europe/Kyiv"))

REPORT_NAMES = {
    "daily": "Щоденний звіт",
    "weekly": "Щотижневий звіт",
    "monthly": "Щомісячний звіт",
    "quarterly": "Щоквартальний звіт",
    "yearly": "Річний звіт"
}

ENERGY_NAMES = {
    "production": ("Генерація", "#d97706"),
    "consumption": ("Споживання", "#2563eb"),
    "grid_import": ("Імпорт з мережі", "#ea580c"),
    "grid_export": ("Експорт в мережу", "#16a34a"),
    "battery_charge": ("Заряд АКБ", "#0891b2"),
    "battery_discharge": ("Розряд АКБ", "#9333ea"),
    "inverter_losses": ("Втрати інвертора", "#64748b")
}

STATUSES = {
    "complete": "Повні дані",
    "recovered": "За накопичувальним лічильником",
    "partial": "Неповні дані",
    "unavailable": "Немає даних"
}

logging.Formatter.converter = __import__("time").gmtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s UTC | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            "/app/logs/email-delivery.log",
            encoding="utf-8"
        )
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


def build_email(data):

    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    last = end.date() - timedelta(days=1)

    period = f"{start:%d.%m.%Y} — {last:%d.%m.%Y}"

    title = REPORT_NAMES[data["report_type"]]

    subject = f"☀ СЕС | {title} | {period}"

    rows = []
    plain_rows = []
    warnings = list(data.get("configuration_warnings", []))

    for key, (label, color) in ENERGY_NAMES.items():

        if key not in data["energy"]:
            continue
        item = data["energy"].get(key, {})

        value = fmt(item.get("total"))

        coverage = fmt(item.get("coverage"), 2)

        status = STATUSES.get(
            item.get("status"),
            "Невідомо"
        )

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
            f"{label}: {value} кВт·год "
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
                f"Чистий експорт: {fmt(net)} кВт·год"
            )
        else:
            net_text = (
                f"Чистий імпорт: {fmt(abs(net))} кВт·год"
            )

    warning_html = ""

    if warnings:
        warning_html = """
        <div style="background:#fffbeb;
                    border-left:4px solid #d97706;
                    padding:16px;margin:20px 0">
            <strong>Якість історичних даних</strong>
            <ul>
        """

        warning_html += "".join(
            f"<li>{escape(w)}</li>" for w in warnings
        )

        warning_html += "</ul></div>"

    now = datetime.now(TZ)

    html = f"""
    <!DOCTYPE html>
    <html lang="uk">
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
                ☀ Сонячна електростанція
            </h1>

            <p>{title}</p>

            <p style="color:#cbd5e1">{period}</p>

        </div>

        <div style="padding:24px">

            <p>Вітаємо!</p>

            <p>
                Автоматично сформовано аналітичний звіт
                щодо роботи сонячної електростанції
                за зазначений період.
            </p>

            <h2>Основні енергетичні показники</h2>

            <table style="width:100%;border-collapse:collapse;
                          font-size:14px">

                <tr style="background:#10233d;color:white">
                    <th style="padding:12px;text-align:left">
                        Показник
                    </th>
                    <th style="padding:12px;text-align:right">
                        кВт·год
                    </th>
                    <th style="padding:12px;text-align:right">
                        Повнота
                    </th>
                </tr>

                {''.join(rows)}

            </table>

            <p style="font-size:16px;font-weight:bold">
                {escape(net_text)}
            </p>

            {warning_html}

            <h2>Детальний звіт</h2>

            <p>До повідомлення додано:</p>

            <ul>
                <li>PDF — повний аналітичний звіт.</li>
                <li>HTML — інтерактивні графіки та статистика.</li>
            </ul>

            <p>
                Детальний звіт містить інформацію про
                генерацію, споживання, електромережу,
                акумуляторну систему та температурний
                моніторинг.
            </p>

        </div>

        <div style="background:#f8fafc;padding:20px;
                    color:#64748b;font-size:12px">

            <p>Джерело даних: Home Assistant / Deye</p>

            <p>Сформовано: {now:%d.%m.%Y %H:%M}</p>

            <p>Часовий пояс: Europe/Kyiv</p>

            <p>
                Це автоматичне повідомлення системи
                Solar Energy Analytics.
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
        "Детальні звіти у форматах PDF та HTML додано.",
        "Solar Energy Analytics"
    ])

    return subject, plain, html


def send_report(source):

    if os.environ.get("SMTP_ENABLED", "").lower() != "true":
        raise RuntimeError("SMTP delivery is disabled")

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

    username = os.environ["SMTP_USERNAME"]

    password = Path(
        os.environ["SMTP_PASSWORD_FILE"]
    ).read_text().strip()

    recipients = [
        address.strip()
        for address in os.environ["SMTP_TO"].split(",")
        if address.strip()
    ]

    if not recipients:
        raise RuntimeError("No SMTP recipients configured")

    subject, plain, html = build_email(data)

    message = EmailMessage()

    message["Subject"] = subject
    message["From"] = os.environ["SMTP_FROM"]
    message["To"] = ", ".join(recipients)
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

    args = parser.parse_args()

    try:
        send_report(args.source)
    except Exception:
        logger.exception("Email delivery failed")
        raise SystemExit(1)
