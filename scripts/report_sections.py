"""Presentation-only selection of report sections and KPI ordering."""
def apply_sections(context):
    settings = context['profile']['report']
    by_key = {row['key']: row for row in context['energy']}
    context['kpis'] = [by_key[key] for key in settings['kpis'] if key in by_key]
    context['batteries'] = [b for b in context['batteries'] if b['rows']]
    available = {
        'kpi_summary': context['kpis'], 'energy_summary': context['energy'],
        'charts': context['charts'], 'grid_analysis': context['phases'],
        'battery_analysis': context['battery_bank'] or context['batteries'],
        'temperature_analysis': context['temperatures'],
        'data_quality': True, 'conclusions': True,
    }
    context['section_numbers'] = {
        key: f'{i:02d}' for i, key in enumerate(
            (key for key, value in available.items() if value and settings['sections'][key]), 1)
    }
    context['kpi_columns'] = min(3, max(1, len(context['kpis'])))
    if len(context['kpis']) == 4:
        context['kpi_columns'] = 2
    return context
