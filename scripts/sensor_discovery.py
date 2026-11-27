"""Read-only discovery and conservative candidate ranking."""
import re
from sensor_validation import validate

ALIASES = {
 'production': ('production', 'solar energy', 'pv energy', 'yield'),
 'consumption': ('consumption', 'load energy', 'house energy'),
 'grid_import': ('import', 'grid purchase'),
 'grid_export': ('export', 'feed in'),
 'battery_charge': ('battery charge', 'battery charging'),
 'battery_discharge': ('battery discharge', 'battery discharging'),
 'inverter_losses': ('losses', 'loss'),
}

def candidates(states, metadata, role, target='kWh', cumulative=True, *, include_unmatched=False):
    registry = {m['statistic_id']: m for m in metadata}
    result = []
    for state in states:
        entity = state.get('entity_id', '')
        if not entity.startswith('sensor.'): continue
        try: unit = validate(registry.get(entity), target, cumulative)
        except ValueError: continue
        name = state.get('attributes', {}).get('friendly_name', '') or ''
        words = re.sub(r'[^\w]+|_', ' ', (entity + ' ' + name).lower())
        score = sum(10 for alias in ALIASES.get(role, (role.replace('_',' '),)) if re.search(r'\b'+re.escape(alias)+r'\b', words))
        if not score and not include_unmatched: continue
        matched = bool(score)
        periodic = bool(cumulative and re.search(r'\b(today|daily|monthly|yearly|weekly)\b', words))
        if periodic: score -= 20
        if cumulative and re.search(r'\b(total|lifetime)\b', words): score += 3
        available = state.get('state') not in ('unknown','unavailable',None)
        result.append(dict(entity_id=entity, name=name, unit=unit, available=available, score=score, category=('periodic' if periodic else 'preferred' if matched else 'manual')))
    return sorted(result, key=lambda x: (-x['score'], not x['available'], x['entity_id']))
