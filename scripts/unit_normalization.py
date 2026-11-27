"""Convert recorder statistics, never timestamps or metadata."""
import math

UNITS = {
    'Wh': ('kWh', .001, 0), 'kWh': ('kWh', 1, 0), 'MWh': ('kWh', 1000, 0),
    'W': ('W', 1, 0), 'kW': ('W', 1000, 0), 'MW': ('W', 1000000, 0),
    'V': ('V', 1, 0), 'mV': ('V', .001, 0),
    'A': ('A', 1, 0), 'mA': ('A', .001, 0),
    'Ah': ('Ah', 1, 0), 'mAh': ('Ah', .001, 0),
    '°C': ('°C', 1, 0), '°F': ('°C', 5/9, -32*5/9), 'K': ('°C', 1, -273.15),
    '%': ('%', 1, 0), 'Hz': ('Hz', 1, 0),
}

def response_unit(meta, storage_unit):
    """Conservative guard for unqualified recorder API responses.

    Until the response unit is explicitly negotiated, differing display and
    storage units are ambiguous. Never guess which scale the API returned.
    """
    display = meta.get('display_unit_of_measurement')
    if display is not None and display != storage_unit:
        raise ValueError(
            f'Ambiguous recorder response unit: storage={storage_unit!r}, '
            f'display={display!r}; explicit unit negotiation required'
        )
    return storage_unit


def normalize_rows(rows, unit):
    if unit not in UNITS:
        raise ValueError(f"Unsupported statistics unit: {unit!r}")
    target, scale, offset = UNITS[unit]
    if scale == 1 and offset == 0:
        return rows
    output = []
    for row in rows:
        if not isinstance(row, dict):
            output.append(row)
            continue
        converted = dict(row)
        for key in ('min', 'mean', 'max', 'state', 'sum', 'change'):
            value = row.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                converted[key] = value * scale + (0 if key in ('sum', 'change') else offset)
        output.append(converted)
    return output
