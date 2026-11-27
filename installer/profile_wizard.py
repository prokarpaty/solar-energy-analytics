"""Bilingual installation and report profile configuration."""

import math
import re
import yaml

from pathlib import Path


def configure_profile(template, lang="en", ask=input, show=print):
    uk = lang == "uk"

    def tr(en, ua):
        return ua if uk else en

    def field(en, ua, default=None):
        label = tr(en, ua)
        suffix = f" [{default}]" if default is not None else ""
        return ask(f"{label}{suffix}: ").strip() or default

    def number(en, ua, integer=False):
        while True:
            value = field(en, ua)

            if value is None:
                return None

            try:
                result = int(value) if integer else float(
                    value.replace(",", ".")
                )

                if not math.isfinite(result) or result <= 0:
                    raise ValueError

                return result

            except (ValueError, OverflowError):
                show(tr(
                    "Enter a positive number or leave blank.",
                    "Введіть додатне число або залиште поле порожнім."
                ))

    def boolean(en, ua, default=True):
        while True:
            value = field(
                en, ua, "Y" if default else "N"
            ).lower()

            if value in ("y", "yes", "т", "так"):
                return True

            if value in ("n", "no", "н", "ні"):
                return False

            show(tr("Enter Y or N.", "Введіть Y або N."))

    def color(en, ua, default):
        while True:
            value = field(en, ua, default)

            if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                return value

            show(tr(
                "Use a hexadecimal color, e.g. #10233d.",
                "Використовуйте HEX-колір, наприклад #10233d."
            ))

    profile = yaml.safe_load(
        Path(template).read_text(encoding="utf-8")
    )

    show("\n" + tr(
        "=== Installation information ===",
        "=== Інформація про установку ==="
    ))

    installation = profile["installation"]

    installation["name"] = field(
        "Installation name",
        "Назва установки",
        tr("Home Solar Installation", "Домашня сонячна станція")
    )

    installation["location"] = field(
        "Location (optional)", "Місцезнаходження (необов'язково)"
    ) or ""

    installation["description"] = field(
        "Description (optional)", "Опис (необов'язково)"
    ) or ""

    show("\n" + tr(
        "=== Equipment specifications ===",
        "=== Характеристики обладнання ==="
    ))

    equipment = profile["equipment"]

    equipment["inverter"]["manufacturer"] = field(
        "Inverter manufacturer", "Виробник інвертора", "Deye"
    )

    equipment["inverter"]["model"] = field(
        "Inverter model", "Модель інвертора"
    )

    equipment["inverter"]["rated_power_kw"] = number(
        "Rated inverter power (kW)",
        "Номінальна потужність інвертора (кВт)"
    )

    equipment["solar"]["installed_capacity_kwp"] = number(
        "Installed solar capacity (kWp)",
        "Встановлена потужність панелей (кВт·пік)"
    )

    equipment["solar"]["panel_count"] = number(
        "Number of solar panels",
        "Кількість сонячних панелей",
        integer=True
    )

    equipment["battery"]["manufacturer"] = field(
        "Battery manufacturer", "Виробник АКБ"
    )

    equipment["battery"]["model"] = field(
        "Battery model", "Модель АКБ"
    )

    equipment["battery"]["nominal_capacity_kwh"] = number(
        "Nominal battery capacity (kWh)",
        "Номінальна ємність АКБ (кВт·год)"
    )

    show("\n" + tr(
        "=== Report branding ===",
        "=== Оформлення звітів ==="
    ))

    branding = profile["branding"]

    branding["name"] = field(
        "Report brand name",
        "Назва бренду у звітах",
        branding["name"]
    )

    branding["primary_color"] = color(
        "Primary color",
        "Основний колір",
        branding["primary_color"]
    )

    branding["accent_color"] = color(
        "Accent color",
        "Акцентний колір",
        branding["accent_color"]
    )

    if boolean(
        "Customize report sections?",
        "Налаштувати розділи звітів?",
        False
    ):
        sections = {
            "kpi_summary": ("Key indicators", "Ключові показники"),
            "energy_summary": ("Energy summary", "Енергетичний баланс"),
            "charts": ("Charts", "Графіки"),
            "grid_analysis": ("Grid analysis", "Аналіз мережі"),
            "battery_analysis": ("Battery analysis", "Аналіз АКБ"),
            "temperature_analysis": ("Temperatures", "Температури"),
            "data_quality": ("Data quality", "Якість даних"),
            "conclusions": ("Conclusions", "Висновки")
        }

        for key, (en, ua) in sections.items():
            profile["report"]["sections"][key] = boolean(
                en, ua, profile["report"]["sections"][key]
            )

    return profile
