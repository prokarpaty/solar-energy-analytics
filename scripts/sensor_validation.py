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

ENERGY_ROLES = ('production', 'consumption', 'grid_import', 'grid_export', 'battery_charge', 'battery_discharge', 'inverter_losses')
REQUIRED_ENERGY = frozenset(('production', 'consumption'))

def validate_configuration(config, registry):
    """Return valid mappings, units and warnings; never substitute zero."""
    import re
    energy, units, targets, measurement_units, warnings = {}, {}, {}, {}, []
    def entity_id(value):
        return isinstance(value, str) and re.fullmatch(r'sensor\.[a-z0-9_]+', value)
    configured = config.get('energy', {})
    if not isinstance(configured, dict):
        raise ValueError('energy must be a mapping')
    seen = {}
    for role, sensor in configured.items():
        if role not in ENERGY_ROLES:
            raise ValueError(f'Unknown energy role: {role}')
        if sensor is None or sensor == '': continue
        if not entity_id(sensor): raise ValueError(f'Invalid entity ID for {role}: {sensor!r}')
        if sensor in seen: raise ValueError(f'Duplicate energy mapping: {seen[sensor]} and {role}: {sensor}')
        seen[sensor] = role
    for role in ENERGY_ROLES:
        sensor = configured.get(role)
        if not sensor:
            if role in REQUIRED_ENERGY: raise ValueError(f'Missing required energy sensor: {role}')
            continue
        try: units[sensor] = validate(registry.get(sensor), 'kWh', True)
        except ValueError as exc:
            if role in REQUIRED_ENERGY: raise ValueError(f'{role}: {sensor}: {exc}') from exc
            warnings.append(f'{role}: {sensor}: {exc}')
            continue
        energy[role] = sensor
    def walk(value, path):
        if isinstance(value, dict):
            for key, child in value.items(): yield from walk(child, path + [key])
        elif value is not None and value != '' and path[-1] not in ('name','cycles'):
            if not entity_id(value): raise ValueError(f'Invalid entity ID at {".".join(path)}: {value!r}')
            if value.endswith(('_cycles','_life_cycles')): return
            yield value, measurement_target(path)
    for section in ('power','grid','house','battery_bank','batteries','temperature'):
        for sensor, target in walk(config.get(section, {}), [section]):
            if sensor in targets and targets[sensor] != target:
                raise ValueError(f'Conflicting measurement roles for {sensor}')
            targets[sensor] = target
    for sensor, target in sorted(targets.items()):
        try: measurement_units[sensor] = validate(registry.get(sensor), target)
        except ValueError as exc: warnings.append(f'{sensor}: {exc}')
    return energy, units, measurement_units, warnings
