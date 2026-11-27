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
    limits=None
):
    fig = go.Figure()

    mpl_fig, ax = plt.subplots(
        figsize=(11, 3.6),
        dpi=130
    )

    has_data = False

    for definition in definitions:
        entity, label, color = definition

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
                name=label,
                marker_color=color
            ))
        else:
            fig.add_trace(go.Scatter(
                x=series.index,
                y=series.values,
                name=label,
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

    fig.update_layout(
        title=title,
        template="plotly_white",
        height=390,
        barmode="group",
        hovermode="x unified",
        margin=dict(l=55, r=20, t=60, b=85),
        yaxis_title=ylabel,
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

    ax.set_ylabel(ylabel)

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
            "Немає історичних даних",
            transform=ax.transAxes,
            ha="center",
            va="center"
        )

        fig.add_annotation(
            text="Немає історичних даних",
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


def generate_charts(data):
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
            charts.append(create_chart(data, title, unit, definitions, **kwargs))

    def mapped(mapping, specs):
        return [(mapping.get(key), label, COLORS[color]) for key, label, color in specs]

    def battery_series(key):
        return [(b.get(key), f"АКБ {i+1}", palette[i % len(palette)]) for i, b in enumerate(batteries.values())]

    add("Генерація та споживання електроенергії", "кВт·год", mapped(energy, [("production", "Генерація", "solar"), ("consumption", "Споживання", "house")]), source="energy", metric="change", chart_type="bar")
    add("Імпорт та експорт електроенергії", "кВт·год", mapped(energy, [("grid_import", "Імпорт", "grid"), ("grid_export", "Експорт", "export")]), source="energy", metric="change", chart_type="bar")
    pv = [(v, k.upper(), palette[i % len(palette)]) for i, (k,v) in enumerate((item for item in power.items() if item[0].startswith("pv") and item[0][2:].isdigit()))]
    add("Потужність сонячних панелей", "Вт", pv + [(power.get("solar"), "Загальна", COLORS["export"])])
    add("Потужність енергетичної системи", "Вт", mapped(power, [("solar", "Сонце", "solar"), ("house", "Споживання", "house"), ("grid", "Мережа", "grid"), ("battery", "АКБ", "battery")]))
    add("Напруга електромережі по фазах", "В", [(v, k.upper(), palette[i % len(palette)]) for i,(k,v) in enumerate(grid.get("voltage", {}).items())], limits=(207,253))
    add("Навантаження по фазах", "Вт", [(v.get("power"), v.get("name", k.upper()), palette[i % len(palette)]) for i,(k,v) in enumerate(house.items())])
    add("Заряд та розряд акумуляторів", "кВт·год", mapped(energy, [("battery_charge", "Заряд", "battery"), ("battery_discharge", "Розряд", "purple")]), source="energy", metric="change", chart_type="bar")
    add("Рівень заряду акумуляторної системи", "%", [(bank.get("soc"), "Загальний SOC", COLORS["battery"])] + battery_series("soc"))
    add("Температура акумуляторів", "°C", battery_series("temperature"))
    add("Максимальний дисбаланс комірок АКБ", "В", battery_series("imbalance"), metric="max")
    add("Температурний моніторинг", "°C", mapped(CONFIG.get("temperature", {}), [("inverter", "Інвертор", "grid"), ("inverter_dc", "Інвертор DC", "purple"), ("outside", "Вулиця", "house"), ("garage", "Гараж", "battery"), ("office", "Офіс", "export"), ("inverter_room", "Приміщення інвертора", "solar")]))
    return charts
