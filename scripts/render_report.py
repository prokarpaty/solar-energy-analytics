import json
import argparse
from localization import Localizer

from pathlib import Path
from datetime import datetime, timedelta

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML
from plotly.offline import get_plotlyjs

from report_charts import generate_charts
from ha_client import CONFIG



ENERGY = {'production': ('production', '#d97706'),
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


def fmt(value, decimals=2):
    if value is None:
        return "—"

    return (
        f"{value:,.{decimals}f}"
        .replace(",", " ")
        .replace(".", ",")
    )


def measurement(data, entity, name, decimals=2, *, loc=None):
    fmt = (loc or Localizer()).number
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


def build_context(data, language=None):
    loc = Localizer(language)
    fmt = loc.number
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])
    last = end.date() - timedelta(days=1)

    days = (end.date() - start.date()).days

    energy = []
    warnings = list(data.get("configuration_warnings", []))
    conclusions = []

    for key, (_, color) in ENERGY.items():
        label = loc.text("energy." + key)
        if key not in data["energy"]:
            continue
        item = data["energy"].get(key, {})

        energy.append({
            "label": label,
            "color": color,
            "value": fmt(item.get("total")),
            "coverage": fmt(item.get("coverage", 0), 2) + "%",
            "status": loc.text("status." + item["status"]) if item.get("status") in STATUSES else loc.text("presentation.not_configured")
        })

        if item.get("status") == "partial":
            warnings.append(
                loc.text("presentation.partial", label=label, coverage=fmt(item['coverage']), observed=fmt(item.get('observed_change')))
            )

        elif item.get("status") == "recovered":
            warnings.append(
                loc.text("presentation.recovered", label=label, missing=item.get('missing_hours', 0))
            )

        elif item.get("status") == "unavailable":
            warnings.append(
                loc.text("presentation.unavailable", label=label)
            )

    def total(key):
        return data["energy"].get(key, {}).get("total")

    production = total("production")
    consumption = total("consumption")
    imported = total("grid_import")
    exported = total("grid_export")

    if production is not None:
        conclusions.append(
            loc.text("presentation.avg_generation", value=fmt(production / days))
        )

    if consumption is not None:
        conclusions.append(
            loc.text("presentation.avg_consumption", value=fmt(consumption / days))
        )

    if production is not None and consumption:
        conclusions.append(
            loc.text("presentation.ratio", value=fmt(production / consumption * 100, 1))
        )

    if imported is not None and exported is not None:
        net = exported - imported

        if net >= 0:
            conclusions.append(
                loc.text("presentation.net_export", value=fmt(net))
            )
        else:
            conclusions.append(
                loc.text("presentation.net_import", value=fmt(abs(net)))
            )

    phases = []

    for phase, entity in CONFIG.get("grid", {}).get("voltage", {}).items():
        phases.append(
            measurement(data, entity, phase.upper(), loc=loc)
        )

        item = data["measurements"].get(entity, {})

        maximum = item.get("max")
        minimum = item.get("min")

        if maximum is not None and maximum > 253:
            warnings.append(
                loc.text("presentation.voltage_high", phase=phase.upper(), value=fmt(maximum))
            )

        if minimum is not None and minimum < 207:
            warnings.append(
                loc.text("presentation.voltage_low", phase=phase.upper(), value=fmt(minimum))
            )

    bank_labels = {
        "soc": loc.text("presentation.metric_0"),
        "soh": loc.text("presentation.metric_1"),
        "voltage": loc.text("presentation.metric_2"),
        "current": loc.text("presentation.metric_3"),
        "temperature": loc.text("presentation.metric_4"),
        "capacity": loc.text("presentation.metric_5")
    }

    battery_bank = [
        measurement(data, CONFIG.get("battery_bank", {})[key], label, loc=loc)
        for key, label in bank_labels.items() if key in CONFIG.get("battery_bank", {})
    ]

    battery_labels = {
        "soc": "SOC, %",
        "soh": "SOH, %",
        "voltage": loc.text("presentation.metric_2"),
        "current": loc.text("presentation.metric_3"),
        "temperature": loc.text("presentation.metric_4"),
        "mos_temperature": loc.text("presentation.metric_6"),
        "min_cell_voltage": loc.text("presentation.metric_7"),
        "max_cell_voltage": loc.text("presentation.metric_8"),
        "imbalance": loc.text("presentation.metric_9")
    }

    batteries = []

    for n, config in enumerate(CONFIG.get("batteries", {}).values(), 1):

        batteries.append({
            "name": loc.text("presentation.battery", n=n),
            "rows": [
                measurement(
                    data,
                    config[key],
                    label,
                    3 if "voltage" in key
                    or key == "imbalance" else 2, loc=loc
                )
                for key, label in battery_labels.items() if key in config
            ]
        })

    temperature_labels = {
        "inverter": loc.text("presentation.metric_10"),
        "inverter_dc": loc.text("presentation.metric_11"),
        "outside": loc.text("presentation.metric_12"),
        "garage": loc.text("presentation.metric_13"),
        "office": loc.text("presentation.metric_14"),
        "inverter_room": loc.text("presentation.metric_15")
    }

    temperatures = [
        measurement(data, CONFIG["temperature"][key], label, loc=loc)
        for key, label in temperature_labels.items() if key in CONFIG.get("temperature", {})
    ]

    return {
        "title": loc.text("presentation.title_" + data["report_type"]),
        "language": loc.language,
        "t": loc.text,
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


def render(source, language=None):
    source = Path(source)

    data = json.loads(
        source.read_text(encoding="utf-8")
    )

    context = build_context(data, language)

    print("Generating charts...")
    context["charts"] = generate_charts(data, language=language)

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
    parser.add_argument("--language", choices=("en", "uk"))
    args = parser.parse_args()
    render(args.source, args.language)
