"""Dashboard calculations, kept independent from Dash and Plotly."""
import pandas as pd
import re

from .load import entries, total, value

DISEASE_ALERT = 25000
FOOD_SPECIAL_CONTEXTS = {'Harvested', 'Butchered', 'Rotted'}


def _context_value(report, category, context, field):
    entry = next(
        (item for item in entries(report, category) if item.get('Context') == context),
        None,
    )
    return float(entry.get(field, 0) or 0) if entry else 0.0


def calculate(reports):
    rows = []
    for report in reports:
        food_entries = entries(report, 'CaloriesCreated')
        duplicants = [
            entry for entry in food_entries
            if entry.get('Context') is not None
            and entry.get('Context') not in FOOD_SPECIAL_CONTEXTS
        ]
        harvested = _context_value(report, 'CaloriesCreated', 'Harvested', 'PositiveValue')
        butchered = _context_value(report, 'CaloriesCreated', 'Butchered', 'PositiveValue')
        rotted = abs(_context_value(report, 'CaloriesCreated', 'Rotted', 'NegativeValue'))
        duplicate_negative = sum(float(entry.get('NegativeValue', 0) or 0) for entry in duplicants)
        positive_ok = abs(
            value(report, 'CaloriesCreated', 'PositiveValue') - harvested - butchered
        ) <= 5
        negative_ok = abs(
            value(report, 'CaloriesCreated', 'NegativeValue') - duplicate_negative
            - _context_value(report, 'CaloriesCreated', 'Rotted', 'NegativeValue')
        ) <= 5
        energy_net = value(report, 'EnergyCreated') + value(report, 'EnergyWasted')
        snapshot = report.get('Snapshot') or {}
        worlds = snapshot.get('Worlds') or []
        food_stock = sum(float(world.get('RationKcalRaw', 0) or 0) for world in worlds) / 1000 if snapshot else None
        stored = sum(float(world.get('TrackerBatteryRaw', 0) or 0) for world in worlds) / 1000 if snapshot else None
        capacity = sum(float(world.get('BatteryCapacityJoules', 0) or 0) for world in worlds) / 1000 if snapshot else None
        materials = {}
        for world in worlds:
            for item in world.get('Materials', []):
                tag = item.get('Tag')
                materials[tag] = materials.get(tag, 0) + float(item.get('Kg', 0) or 0)
        stress = {item.get('Name'): float(item.get('Stress', 0) or 0) for item in (snapshot.get('Duplicants') or [])}
        rows.append({
            'cycle': int(report['Cycle']),
            'food_balance': value(report, 'CaloriesCreated') / 1000,
            'food_harvested': harvested / 1000,
            'food_butchered': butchered / 1000,
            'food_consumed': -abs(duplicate_negative) / 1000,
            'food_rotted': -rotted / 1000,
            'food_reconciles': positive_ok and negative_ok,
            'oxygen_produced': value(report, 'OxygenCreated', 'PositiveValue'),
            'oxygen_breathing': value(report, 'OxygenCreated', 'NegativeValue'),
            'oxygen_balance': value(report, 'OxygenCreated'),
            'energy_generated': value(report, 'EnergyCreated', 'PositiveValue') / 1000,
            'energy_consumed': value(report, 'EnergyCreated', 'NegativeValue') / 1000,
            'energy_wasted': value(report, 'EnergyWasted') / 1000,
            'energy_net_created': value(report, 'EnergyCreated') / 1000,
            'energy_balance': energy_net / 1000,
            'food_stock_kcal': food_stock,
            'energy_stored_kj': stored,
            'energy_capacity_kj': capacity,
            'materials': materials if snapshot else None,
            'schema_version': int(report.get('SchemaVersion', 1) or 1),
            'duplicant_stress': stress if snapshot else None,
            'snapshot_errors': snapshot.get('Errors') or [],
        })

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame['food_average_10'] = frame['food_balance'].rolling(10, min_periods=1).mean()
    frame['food_minimum_10'] = frame['food_balance'].rolling(10, min_periods=1).min()
    frame['food_maximum_10'] = frame['food_balance'].rolling(10, min_periods=1).max()
    frame['oxygen_average_10'] = frame['oxygen_balance'].rolling(10, min_periods=1).mean()
    frame['energy_stored_estimate'] = frame['energy_balance'].cumsum() - frame['energy_balance'].iloc[0]
    consumption = frame['food_consumed'].abs()
    frame['food_consumption_average_10'] = consumption.rolling(10, min_periods=1).mean()
    frame['food_cycles_remaining'] = frame.apply(
        lambda row: row['food_stock_kcal'] / row['food_consumption_average_10']
        if pd.notna(row['food_stock_kcal']) and row['food_stock_kcal'] > 0 and row['food_consumption_average_10'] > 0 else None,
        axis=1,
    )
    tags = sorted({'Algae', 'Carbon', 'Cuprite', 'Copper', 'GoldAmalgam', 'IronOre', 'Iron'} |
                  {tag for materials in frame['materials'] if isinstance(materials, dict) for tag in materials if tag})
    for tag in tags:
        column = f'material_tag_{tag}'
        values = []
        for materials, schema in zip(frame['materials'], frame['schema_version']):
            if isinstance(materials, dict) and tag in materials:
                values.append(materials[tag])
            else:
                values.append(0 if schema >= 3 and isinstance(materials, dict) else float('nan'))
        frame[column] = pd.to_numeric(pd.Series(values, index=frame.index), errors='coerce')
        frame[f'{column}_change'] = frame[column].diff()
        frame[f'{column}_average_10'] = frame[f'{column}_change'].rolling(10, min_periods=1).mean()
    return frame


def source_breakdown(report):
    """Return sorted energy sources/consumers/losses and oxygen producers with markup removed."""
    def clean(text):
        return re.sub(r'<link="[^"]*">(.*?)</link>', r'\1', str(text or ''))
    energy, losses, oxygen = {}, {}, {}
    for category, destination, positive_only in (('EnergyCreated', energy, False), ('EnergyWasted', losses, False), ('OxygenCreated', oxygen, True)):
        for entry in entries(report, category):
            for note in entry.get('Notes') or []:
                name = clean(note.get('Name') or note.get('Note'))
                value = float(note.get('Value', 0) or 0)
                if not name or (positive_only and value <= 0):
                    continue
                if category == 'OxygenCreated' and name in {d.get('Name') for d in (report.get('Snapshot') or {}).get('Duplicants', [])}:
                    continue
                destination[name] = destination.get(name, 0) + value
    return {
        'generators': sorted(((n, v) for n, v in energy.items() if v > 0), key=lambda item: item[1], reverse=True),
        'consumers': sorted(((n, v) for n, v in energy.items() if v < 0), key=lambda item: item[1]),
        'losses': sorted(losses.items(), key=lambda item: abs(item[1]), reverse=True),
        'oxygen': sorted(oxygen.items(), key=lambda item: item[1], reverse=True),
    }


def stress_data(reports):
    """Map duplicants to their per-cycle stress deltas; absence stays None."""
    names = sorted({
        entry.get('Context') for report in reports
        for entry in entries(report, 'StressDelta') if entry.get('Context')
    })
    values = {}
    for name in names:
        values[name] = []
        for report in reports:
            entry = next(
                (item for item in entries(report, 'StressDelta') if item.get('Context') == name),
                None,
            )
            values[name].append(float(entry.get('NetValue', 0)) if entry else None)
    return values


def stress_summary(reports):
    data = stress_data(reports)
    present = set()
    if reports:
        present = {
            entry.get('Context') for entry in entries(reports[-1], 'StressDelta')
            if entry.get('Context')
        }
    summaries = {}
    for name, deltas in data.items():
        consecutive = 0
        for delta in reversed(deltas):
            if delta is None or delta <= 0:
                break
            consecutive += 1
        positive_10 = sum(max(0, delta) for delta in deltas[-10:] if delta is not None)
        summaries[name] = {
            'consecutive_positive_cycles': consecutive,
            'positive_delta_10': positive_10,
            'present_now': name in present,
        }
    pressured = [name for name in present if name in summaries]
    leader = max(pressured, key=lambda name: summaries[name]['positive_delta_10'], default=None)
    return data, summaries, leader


def events(reports):
    result = []
    previous = set()
    for index, report in enumerate(reports):
        present = {
            entry.get('Context')
            for category in ('StressDelta', 'OxygenCreated')
            for entry in entries(report, category)
            if entry.get('Context')
        }
        if index:
            for name in sorted(present - previous):
                result.append({'cycle': report['Cycle'], 'text': f'{name} entrou nos relatórios'})
            for name in sorted(previous - present):
                result.append({'cycle': report['Cycle'], 'text': f'{name} saiu dos relatórios'})
        previous = present
        for category in (
            'ToiletIncident', 'ContaminatedOxygenToilet', 'ContaminatedOxygenSublimation'
        ):
            for entry in entries(report, category):
                net = float(entry.get('NetValue', 0) or 0)
                if net != 0:
                    result.append({
                        'cycle': report['Cycle'],
                        'text': f'{category}: {net:g}',
                    })
        disease = total(report, 'DiseaseStatus')
        disease_value = float(disease.get('NetValue', 0) or 0)
        if disease_value > DISEASE_ALERT:
            result.append({
                'cycle': report['Cycle'],
                'text': f'Alerta de doença: {disease_value:g}',
            })
    return sorted(result, key=lambda event: event['cycle'], reverse=True)
