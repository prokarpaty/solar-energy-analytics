"""Validate recorder capabilities independently of live entity state."""
from unit_normalization import UNITS

def statistics_unit(meta):
    return meta.get('statistics_unit_of_measurement', meta.get('unit_of_measurement'))

def validate(meta, target, cumulative=False):
    if not meta:
        raise ValueError('No registered historical statistics')
    unit = statistics_unit(meta)
    if unit not in UNITS or UNITS[unit][0] != target:
        raise ValueError(f'Incompatible statistics unit: {unit!r}; expected {target}')
    if not meta.get('has_sum' if cumulative else 'has_mean'):
        raise ValueError('Required historical statistics capability missing')
    return unit

def measurement_target(path):
    section, *rest = path
    key = rest[-1]
    if section == 'power' or 'power' in rest: return 'W'
    if section == 'temperature' or 'temperature' in key: return '°C'
    if 'voltage' in rest or 'voltage' in key or key == 'imbalance': return 'V'
    if key == 'current': return 'A'
    if key in ('soc', 'soh'): return '%'
    if key == 'frequency': return 'Hz'
    if key == 'capacity': return 'kWh' if section == 'battery_bank' else 'Ah'
    raise ValueError(f'Unknown measurement role: {path}')
