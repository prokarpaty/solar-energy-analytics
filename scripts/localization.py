"""Shared translations; no dependency on Home Assistant or report calculations."""
import json
import os
from pathlib import Path


class Localizer:
    def __init__(self, language=None):
        self.language = (language if language is not None else os.getenv('REPORT_LANGUAGE', 'uk')).strip().lower()
        if self.language not in ('en', 'uk'):
            raise ValueError('REPORT_LANGUAGE must be en or uk')
        path = Path(__file__).resolve().parents[1] / 'locales' / (self.language + '.json')
        self.catalog = json.loads(path.read_text(encoding='utf-8'))

    def text(self, key, **values):
        result = self.catalog
        for part in key.split('.'):
            result = result[part]
        if not isinstance(result, str):
            raise ValueError(f'Not a translation string: {key}')
        return result.format(**values)

    def number(self, value, decimals=2):
        if value is None:
            return '—'
        result = f'{value:,.{decimals}f}'
        return result.replace(',', ' ').replace('.', ',') if self.language == 'uk' else result
