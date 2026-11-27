"""Minimal dependency-free terminal presentation for the bilingual installer.

Color is enabled only on interactive ANSI-capable terminals. Respect NO_COLOR
and TERM=dumb, and never emit terminal escapes into redirected logs.
"""
import os
import re
import sys

CSI = "\x1b["
_RESET = "\x1b[0m"


def color_enabled(stream=None, environ=None):
    stream = sys.stdout if stream is None else stream
    env = os.environ if environ is None else environ
    return (
        hasattr(stream, "isatty") and stream.isatty()
        and "NO_COLOR" not in env
        and env.get("TERM", "") != "dumb"
    )


def paint(value, style, enabled=None):
    value = str(value)
    use_color = color_enabled() if enabled is None else enabled
    return f"{CSI}{style}m{value}{_RESET}" if use_color else value


def banner(language="en"):
    title = "SOLAR ENERGY ANALYTICS"
    subtitle = (
        "Інтерактивний майстер налаштування"
        if language == "uk" else "Interactive setup wizard"
    )
    print()
    print(paint("━" * 60, "36;1"))
    print("  " + paint("☀  " + title, "1;33"))
    print("  " + paint(subtitle, "36"))
    print(paint("━" * 60, "36;1"))
    print()


def section(number, total, english, ukrainian, language="en"):
    label = ukrainian if language == "uk" else english
    print()
    print(paint(f"  [{number}/{total}]  {label}", "1;36"))
    print(paint("  " + "─" * 55, "36"))


def message(value):
    """Present existing wizard output without altering its text or semantics."""
    value = str(value)
    if value.lstrip().startswith("==="):
        print(paint(value, "1;36"))
    elif value.startswith("[OK]") or value.startswith("[PASS]"):
        print(paint(value, "1;32"))
    elif value.startswith("[ERROR]") or value.startswith("[FAIL]"):
        print(paint(value, "1;31"))
    elif value.startswith("Unmapped:") or value.startswith("Не зіставлено:"):
        print(paint(value, "33"))
    else:
        print(value)


def ask(label):
    """Read exactly one answer, preserving the application's prompt behavior."""
    return input(paint(label, "1;34"))


def secret(label, read_secret):
    """Colorize only the label; credentials are never displayed."""
    return read_secret(paint(label, "1;34"))


def summary(details, language="en"):
    """Readable human summary; callers pass only non-secret fields."""
    title = (
        "Підсумок налаштування" if language == "uk" else "Configuration summary"
    )
    section(7, 7, "Review and save", "Перевірка та збереження", language)
    print(paint("  " + title, "1;33"))
    lines = [
        ("Установка" if language == "uk" else "Installation",
         details["installation"]),
        ("Home Assistant", details["home_assistant"]),
        ("Часовий пояс" if language == "uk" else "Timezone", details["timezone"]),
        ("Мова звітів" if language == "uk" else "Report language",
         details["report_language"]),
        ("SMTP", "ON" if details["smtp_enabled"] else "OFF"),
    ]
    if details["smtp_enabled"]:
        lines.append(("SMTP сервер" if language == "uk" else "SMTP server",
                      f'{details["smtp_host"]}:{details["smtp_port"]}'))
    for label, value in lines:
        print(f"  {paint(label + ':', '1')} {value}")
    print()
    print(paint("  " + ("Розклад:" if language == "uk" else "Schedules:"), "1"))
    labels = {
        "daily": ("Daily", "Щоденні"),
        "weekly": ("Weekly", "Щотижневі"),
        "monthly": ("Monthly", "Щомісячні"),
        "quarterly": ("Quarterly", "Щоквартальні"),
        "yearly": ("Yearly", "Річні"),
    }
    for period, enabled in details["reports"].items():
        names = labels.get(period, (period, period))
        label = names[1] if language == "uk" else names[0]
        status = paint("● ON", "32") if enabled else paint("○ OFF", "2")
        print(f"    {label:<18} {status}")
    print()
