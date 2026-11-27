from localization import Localizer
from chart_security import plain_label, plotly_label
import base64
import io
import math

import pandas as pd
import plotly.graph_objects as go
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from datetime import datetime
from zoneinfo import ZoneInfo


COLORS = {
    "solar": "#EAB308",
    "house": "#2563EB",
    "grid": "#EA580C",
    "battery": "#0891B2",
    "export": "#16A34A",
    "l1": "#DC2626",
    "l2": "#2563EB",
    "l3": "#16A34A",
    "purple": "#9333EA"
}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.18,
    "figure.facecolor": "white",
    "axes.facecolor": "white"
})


def numeric(value):
    return (
        isinstance(value, (int, float))
        and math.isfinite(value)
    )


def build_series(data, entity, source, metric):
    start = datetime.fromisoformat(data["start"])
    end = datetime.fromisoformat(data["end"])

    tz = ZoneInfo(data["timezone"])

    index = pd.date_range(
        start=pd.Timestamp(start).tz_convert("UTC"),
        end=pd.Timestamp(end).tz_convert("UTC"),
        freq="h",
        inclusive="left"
    ).tz_convert(tz)

    rows = data["raw"][source].get(entity, [])

    values = {
        row["start"]: row.get(metric)
        for row in rows
        if numeric(row.get(metric))
    }

    series = pd.Series(
        [
            values.get(int(t.timestamp() * 1000))
            for t in index
        ],
        index=index,
        dtype="float64"
    )

    report_type = data["report_type"]

    if report_type == "daily":
        return series

    frequency = (
        "MS" if report_type == "yearly" else "D"
    )

    grouped = series.resample(frequency)

    if metric == "change":
        result = grouped.sum(min_count=1)

        # Do not display incomplete intervals
        # as complete energy totals.
        return result.where(
            grouped.count() == grouped.size()
        )

    if metric == "min":
        return grouped.min()

    if metric == "max":
        return grouped.max()

    return grouped.mean()


def create_chart(
    data,
    title,
    ylabel,
    definitions,
    source="measurements",
    metric="mean",
    chart_type="line",
    limits=None,
    nominal=None,
    language=None
):
    loc = Localizer(language)
    fig = go.Figure()

    mpl_fig, ax = plt.subplots(
        figsize=(11, 3.6),
        dpi=130
    )

    has_data = False

    for definition in definitions:
        entity, label, color = definition
        label = plain_label(label)

        series = build_series(
            data, entity, source, metric
        )

        if not series.notna().any():
            continue

        has_data = True

        if chart_type == "bar":
            fig.add_trace(go.Bar(
                x=series.index,
                y=series.values,
                name=plotly_label(label),
                marker_color=color
            ))
        else:
            fig.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                name=plotly_label(label),
                mode="lines",
                connectgaps=False,
                line=dict(color=color, width=2)
            ))

        ax.plot(
            series.index,
            series.values,
            color=color,
            linewidth=1.6,
            label=label,
            marker="o" if chart_type == "bar" else None,
            markersize=3
        )

    if limits:
        low, high = limits

        fig.add_hrect(
            y0=low,
            y1=high,
            fillcolor="#16A34A",
            opacity=0.08,
            line_width=0
        )

        ax.axhspan(
            low, high,
            color="#16A34A",
            alpha=0.08
        )

    if nominal is not None:
        fig.add_hline(y=nominal, line_dash="dot", line_color="#64748b")
        ax.axhline(nominal, linestyle=":", color="#64748b")

    fig.update_layout(
        title=plotly_label(title),
        separators=", " if loc.language == "uk" else ".,",
        template="plotly_white",
        height=390,
        barmode="group",
        hovermode="x unified",
        margin=dict(l=55, r=20, t=60, b=85),
        yaxis_title=plotly_label(ylabel),
        legend=dict(
            orientation="h",
            y=-0.22
        ),
        font=dict(
            family="Arial, sans-serif",
            size=12
        )
    )

    ax.set_title(
        title,
        loc="left",
        fontsize=13,
        fontweight="bold",
        pad=12
    )

    ax.set_ylabel(plain_label(ylabel))
    from matplotlib.ticker import FuncFormatter
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: loc.number(value, 6).rstrip("0").rstrip("," if loc.language == "uk" else ".")))

    tz = ZoneInfo(data["timezone"])

    date_format = {
        "daily": "%H:%M",
        "weekly": "%d.%m",
        "monthly": "%d.%m",
        "quarterly": "%d.%m",
        "yearly": "%m.%Y"
    }[data["report_type"]]

    ax.xaxis.set_major_formatter(
        mdates.DateFormatter(date_format, tz=tz)
    )

    if has_data:
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.20),
            ncol=3,
            frameon=False,
            fontsize=8
        )
    else:
        ax.text(
            0.5, 0.5,
            loc.text("chart.no_data"),
            transform=ax.transAxes,
            ha="center",
            va="center"
        )

        fig.add_annotation(
            text=loc.text("chart.no_data"),
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False
        )

    mpl_fig.autofmt_xdate(rotation=0)
    mpl_fig.tight_layout()

    buffer = io.BytesIO()

    mpl_fig.savefig(
        buffer,
        format="png",
        bbox_inches="tight"
    )

    plt.close(mpl_fig)

    image = base64.b64encode(
        buffer.getvalue()
    ).decode("ascii")

    return {
        "title": title,
        "html": fig.to_html(
            full_html=False,
            include_plotlyjs=False,
            config={
                "displaylogo": False,
                "responsive": True
            }
        ),
        "image": f"data:image/png;base64,{image}"
    }


def generate_charts(data, language=None, profile=None):
    from installation_config import load_installation
    profile = load_installation() if profile is None else profile
    voltage = profile["thresholds"]["grid_voltage"]
    loc = Localizer(language)
    t = loc.text
    from ha_client import CONFIG
    charts = []
    energy = CONFIG.get("energy", {})
    power = CONFIG.get("power", {})
    grid = CONFIG.get("grid", {})
    house = CONFIG.get("house", {}).get("phases", {})
    bank = CONFIG.get("battery_bank", {})
    batteries = CONFIG.get("batteries", {})
    palette = [COLORS[k] for k in ("l1", "l2", "l3", "purple", "battery", "solar")]

    def add(title, unit, definitions, **kwargs):
        definitions = [d for d in definitions if isinstance(d[0], str) and d[0].startswith("sensor.")]
        if definitions:
            charts.append(create_chart(data, title, unit, definitions, language=loc.language, **kwargs))

    def mapped(mapping, specs):
        return [(mapping.get(key), label, COLORS[color]) for key, label, color in specs]

    def battery_series(key):
        return [(b.get(key), t("chart.battery_number", number=i+1), palette[i % len(palette)]) for i, b in enumerate(batteries.values())]

    add(t("chart.generation_consumption"), t("chart.energy_unit"), mapped(energy, [("production", t("chart.generation"), "solar"), ("consumption", t("chart.consumption"), "house")]), source="energy", metric="change", chart_type="bar")
    add(t("chart.import_export"), t("chart.energy_unit"), mapped(energy, [("grid_import", t("chart.import"), "grid"), ("grid_export", t("chart.export"), "export")]), source="energy", metric="change", chart_type="bar")
    pv = [(v, k.upper(), palette[i % len(palette)]) for i, (k,v) in enumerate((item for item in power.items() if item[0].startswith("pv") and item[0][2:].isdigit()))]
    add(t("chart.pv_power"), t("chart.power_unit"), pv + [(power.get("solar"), t("chart.total"), COLORS["export"])])
    add(t("chart.system_power"), t("chart.power_unit"), mapped(power, [("solar", t("chart.solar"), "solar"), ("house", t("chart.consumption"), "house"), ("grid", t("chart.grid"), "grid"), ("battery", t("chart.battery"), "battery")]))
    add(t("chart.grid_voltage"), t("chart.voltage_unit"), [(v, k.upper(), palette[i % len(palette)]) for i,(k,v) in enumerate(grid.get("voltage", {}).items())], limits=(voltage["minimum"], voltage["maximum"]), nominal=voltage["nominal"])
    add(t("chart.phase_load"), t("chart.power_unit"), [(v.get("power"), v.get("name", k.upper()), palette[i % len(palette)]) for i,(k,v) in enumerate(house.items())])
    add(t("chart.charge_discharge"), t("chart.energy_unit"), mapped(energy, [("battery_charge", t("chart.charge"), "battery"), ("battery_discharge", t("chart.discharge"), "purple")]), source="energy", metric="change", chart_type="bar")
    add(t("chart.battery_soc"), "%", [(bank.get("soc"), t("chart.total_soc"), COLORS["battery"])] + battery_series("soc"))
    add(t("chart.battery_temperature"), "°C", battery_series("temperature"))
    add(t("chart.cell_imbalance"), t("chart.voltage_unit"), battery_series("imbalance"), metric="max")
    add(t("chart.temperature"), "°C", mapped(CONFIG.get("temperature", {}), [("inverter", t("chart.inverter"), "grid"), ("inverter_dc", t("chart.inverter_dc"), "purple"), ("outside", t("chart.outside"), "house"), ("garage", t("chart.garage"), "battery"), ("office", t("chart.office"), "export"), ("inverter_room", t("chart.inverter_room"), "solar")]))
    return charts
