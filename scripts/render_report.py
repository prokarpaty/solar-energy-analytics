import json
import argparse

from pathlib import Path
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from plotly.offline import get_plotlyjs

from report_charts import generate_charts
from ha_client import CONFIG


REPORT_NAMES = {
    "daily": "Щоденний аналітичний звіт",
    "weekly": "Щотижневий аналітичний звіт",
    "monthly": "Щомісячний аналітичний звіт",
    "quarterly": "Щоквартальний аналітичний звіт",
    "yearly": "Річний аналітичний звіт"
}

ENERGY = {
    "production": ("Генерація", "#d97706"),
    "consumption": ("Споживання", "#2563eb"),
    "grid_import": ("Імпорт", "#ea580c"),
    "grid_export": ("Експорт", "#16a34a"),
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


def fmt(value, decimals=2):
    if value is None:
        return "—"

    return (
        f"{value:,.{decimals}f}"
        .replace(",", " ")
        .replace(".", ",")
    )


def measurement(data, entity, name, decimals=2):
    item = data["measurements"].get(entity, {})

    coverage = min(
        item.get(f"{metric}_coverage", 0)
        for metric in ("min", "mean", "max")
    )

    return {
        "name": name,
        "min": fmt(item.get("min"), decimals),
        "mean": fmt(item.get("mean"), decimals),
        "max": fmt(item.get("max"), decimals),
        "coverage": fmt(coverage, 1) + "%"
    }


def build_context(data):
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    last = end.date() - timedelta(days=1)

    days = (end.date() - start.date()).days

    energy = []
    warnings = list(data.get("configuration_warnings", []))
    conclusions = []

    for key, (label, color) in ENERGY.items():
        if key not in data["energy"]:
            continue
        item = data["energy"].get(key, {})

        energy.append({
            "label": label,
            "color": color,
            "value": fmt(item.get("total")),
            "coverage": fmt(item.get("coverage", 0), 2) + "%",
            "status": STATUSES.get(
                item.get("status"), "Не налаштовано"
            )
        })

        if item.get("status") == "partial":
            warnings.append(
                f"{label}: неповні історичні дані "
                f"({fmt(item['coverage'])}%). "
                f"Сума доступних змін лічильника: "
                f"{fmt(item.get('observed_change'))} кВт·год. "
                "Це не повний підсумок періоду."
            )

        elif item.get("status") == "recovered":
            warnings.append(
                f"{label}: підсумок узгоджується з "
                f"накопичувальним лічильником. "
                f"Пропущено {item.get('missing_hours', 0)} "
                "погодинних записів."
            )

        elif item.get("status") == "unavailable":
            warnings.append(
                f"{label}: історичні дані відсутні."
            )

    def total(key):
        return data["energy"].get(key, {}).get("total")

    production = total("production")
    consumption = total("consumption")
    imported = total("grid_import")
    exported = total("grid_export")

    if production is not None:
        conclusions.append(
            f"Середньодобова генерація: "
            f"{fmt(production / days)} кВт·год."
        )

    if consumption is not None:
        conclusions.append(
            f"Середньодобове споживання: "
            f"{fmt(consumption / days)} кВт·год."
        )

    if production is not None and consumption:
        conclusions.append(
            "Співвідношення генерації до споживання: "
            f"{fmt(production / consumption * 100, 1)}%."
        )

    if imported is not None and exported is not None:
        net = exported - imported

        if net >= 0:
            conclusions.append(
                f"Чистий експорт електроенергії: "
                f"{fmt(net)} кВт·год."
            )
        else:
            conclusions.append(
                f"Чистий імпорт електроенергії: "
                f"{fmt(abs(net))} кВт·год."
            )

    phases = []

    for phase, entity in CONFIG.get("grid", {}).get("voltage", {}).items():
        phases.append(
            measurement(data, entity, phase.upper())
        )

        item = data["measurements"].get(entity, {})

        maximum = item.get("max")
        minimum = item.get("min")

        if maximum is not None and maximum > 253:
            warnings.append(
                f"{phase.upper()}: максимальна напруга "
                f"{fmt(maximum)} В перевищує "
                "орієнтовну межу 253 В."
            )

        if minimum is not None and minimum < 207:
            warnings.append(
                f"{phase.upper()}: мінімальна напруга "
                f"{fmt(minimum)} В нижче 207 В. "
                "Потребує перевірки телеметрії."
            )

    bank_labels = {
        "soc": "Рівень заряду, %",
        "soh": "Стан здоров'я, %",
        "voltage": "Напруга, В",
        "current": "Струм, А",
        "temperature": "Температура, °C",
        "capacity": "Ємність за даними інвертора, кВт·год"
    }

    battery_bank = [
        measurement(data, CONFIG.get("battery_bank", {})[key], label)
        for key, label in bank_labels.items() if key in CONFIG.get("battery_bank", {})
    ]

    battery_labels = {
        "soc": "SOC, %",
        "soh": "SOH, %",
        "voltage": "Напруга, В",
        "current": "Струм, А",
        "temperature": "Температура, °C",
        "mos_temperature": "Температура MOS, °C",
        "min_cell_voltage": "Мін. напруга комірки, В",
        "max_cell_voltage": "Макс. напруга комірки, В",
        "imbalance": "Дисбаланс комірок, В"
    }

    batteries = []

    for n, config in enumerate(CONFIG.get("batteries", {}).values(), 1):

        batteries.append({
            "name": f"Акумулятор {n}",
            "rows": [
                measurement(
                    data,
                    config[key],
                    label,
                    3 if "voltage" in key
                    or key == "imbalance" else 2
                )
                for key, label in battery_labels.items() if key in config
            ]
        })

    temperature_labels = {
        "inverter": "Інвертор",
        "inverter_dc": "Інвертор DC",
        "outside": "Зовнішня температура",
        "garage": "Гараж",
        "office": "Офіс",
        "inverter_room": "Приміщення інвертора"
    }

    temperatures = [
        measurement(data, CONFIG["temperature"][key], label)
        for key, label in temperature_labels.items() if key in CONFIG.get("temperature", {})
    ]

    return {
        "title": REPORT_NAMES[data["report_type"]],
        "period": (
            f"{start:%d.%m.%Y} — {last:%d.%m.%Y}"
        ),
        "timezone": data["timezone"],
        "generated_at": datetime.fromisoformat(
            data["generated_at"]
        ).strftime("%d.%m.%Y %H:%M"),
        "kpis": energy[:6],
        "energy": energy,
        "phases": phases,
        "battery_bank": battery_bank,
        "batteries": batteries,
        "temperatures": temperatures,
        "warnings": warnings,
        "conclusions": conclusions
    }


def render(source):
    source = Path(source)

    data = json.loads(
        source.read_text(encoding="utf-8")
    )

    context = build_context(data)

    print("Generating charts...")
    context["charts"] = generate_charts(data)

    env = Environment(
        loader=FileSystemLoader("/app/templates"),
        autoescape=select_autoescape(["html", "xml"])
    )

    template = env.get_template("report_ua.html")

    html_path = source.with_suffix(".html")
    pdf_path = source.with_suffix(".pdf")

    print("Rendering interactive HTML...")

    html = template.render(
        **context,
        pdf=False,
        plotly_js=get_plotlyjs()
    )

    html_path.write_text(html, encoding="utf-8")

    print("Rendering PDF...")

    pdf_html = template.render(
        **context,
        pdf=True,
        plotly_js=""
    )

    HTML(string=pdf_html).write_pdf(pdf_path)

    print("\n=== REPORT COMPLETED ===")

    for path in (html_path, pdf_path):
        print(f"[OK] {path}")
        print(f"     {path.stat().st_size:,} bytes")

    return html_path, pdf_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    args = parser.parse_args()
    render(args.source)
