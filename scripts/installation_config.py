"""Validated presentation configuration; independent of sensor collection."""
import math
import re
from pathlib import Path
import yaml

CONFIG_DIR = Path(__file__).resolve().parents[1] / 'config'
KPI_KEYS = frozenset(('production', 'consumption', 'grid_import', 'grid_export',
                      'battery_charge', 'battery_discharge', 'inverter_losses'))


def _read(path):
    with path.open(encoding='utf-8') as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f'{path.name}: expected a YAML mapping')
    return value


def _merge(defaults, overrides, prefix=''):
    result = dict(defaults)
    for key, value in overrides.items():
        path = f'{prefix}{key}'
        if key not in defaults:
            raise ValueError(f'{path}: unknown setting')
        if isinstance(defaults[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f'{path}: expected a mapping')
            result[key] = _merge(defaults[key], value, path + '.')
        else:
            result[key] = value
    return result


def _require(condition, path, message):
    if not condition:
        raise ValueError(f'{path}: {message}')


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def load_installation(path=None):
    """Load defaults and optional local overrides; reject invalid settings."""
    defaults = _read(CONFIG_DIR / 'installation.example.yaml')
    path = CONFIG_DIR / 'installation.yaml' if path is None else Path(path)
    config = _merge(defaults, _read(path)) if path.exists() else defaults
    for key, value in config['installation'].items():
        _require(isinstance(value, str), f'installation.{key}', 'expected text')
    for group, fields in config['equipment'].items():
        for key, value in fields.items():
            if value is None:
                continue
            path = f'equipment.{group}.{key}'
            if key in ('manufacturer', 'model'):
                _require(isinstance(value, str) and bool(value.strip()), path, 'expected nonempty text')
            elif key == 'panel_count':
                _require(type(value) is int and value > 0, path, 'expected positive integer')
            else:
                _require(_positive(value), path, 'expected finite positive number')
    branding = config['branding']
    _require(isinstance(branding['name'], str) and bool(branding['name'].strip()), 'branding.name', 'expected nonempty text')
    for key in ('primary_color', 'accent_color'):
        value = branding[key]
        _require(isinstance(value, str) and bool(re.fullmatch(r'#[0-9a-fA-F]{6}', value)), f'branding.{key}', 'expected #RRGGBB')
    _require(branding['logo'] is None, 'branding.logo', 'custom logos are not supported yet')
    for key, value in config['report']['sections'].items():
        _require(type(value) is bool, f'report.sections.{key}', 'expected boolean')
    kpis = config['report']['kpis']
    _require(isinstance(kpis, list) and all(isinstance(k, str) and k in KPI_KEYS for k in kpis), 'report.kpis', 'expected list of supported KPI identifiers')
    _require(len(kpis) == len(set(kpis)), 'report.kpis', 'duplicate KPI')
    voltage = config['thresholds']['grid_voltage']
    for key, value in voltage.items():
        _require(_positive(value), f'thresholds.grid_voltage.{key}', 'expected finite positive number')
    _require(voltage['minimum'] < voltage['nominal'] < voltage['maximum'], 'thresholds.grid_voltage', 'expected minimum < nominal < maximum')
    return config
