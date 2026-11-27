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

def normalize_rows(rows, unit):
    target, scale, offset = UNITS[unit]
    if scale == 1 and offset == 0:
        return rows
    output = []
    for row in rows:
        converted = dict(row)
        for key in ('min', 'mean', 'max', 'state', 'sum', 'change'):
            value = row.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                converted[key] = value * scale + (0 if key in ('sum', 'change') else offset)
        output.append(converted)
    return output
