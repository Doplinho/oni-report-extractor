"""Read cycle exports and retain valid reports across transient write failures."""
from datetime import datetime
import json
import logging
from pathlib import Path
import re

logger = logging.getLogger(__name__)
_cache = {}
_read_errors = set()
_CYCLE_FILE = re.compile(r'report_cycle_(\d+)\.json')


def revision(directory):
    """Return a cheap, deterministic file revision for polling."""
    path = Path(directory)
    try:
        files = list(path.glob('report_cycle_*.json')) + list(path.glob('colonies/*/report_cycle_*.json'))
        return tuple(sorted((str(file.relative_to(path)), file.stat().st_mtime_ns, file.stat().st_size) for file in files))
    except OSError:
        return ()


def has_read_errors(directory):
    root = str(Path(directory).resolve())
    return any(key == root or key.startswith(root + str(Path('/'))) for key in _read_errors)


def _read_report(file, warnings):
    """Read one report through the signature cache, preserving the last valid copy."""
    match = _CYCLE_FILE.fullmatch(file.name)
    if not match:
        return None
    cycle = int(match.group(1))
    key = str(file.resolve())
    try:
        stat = file.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = _cache.get(key)
        if cached and cached[0] == signature and key not in _read_errors:
            return cached[1]
        report = json.loads(file.read_text(encoding='utf-8-sig'))
        if int(report['Cycle']) != cycle:
            warnings.append(f'{file.name}: ciclo do conteúdo diverge do nome; arquivo descartado')
            return None
        report['_timestamp'] = datetime.fromisoformat(report['Timestamp'])
        report['Entries'] = [entry for entry in report.get('Entries', [])
                             if not str(entry.get('Category', '')).endswith('Header')]
        report['_source'] = str(file)
        _cache[key] = (signature, report)
        _read_errors.discard(key)
        return report
    except (OSError, ValueError, KeyError, TypeError) as error:
        _read_errors.add(key)
        cached = _cache.get(key)
        warnings.append(
            f'{file.name}: erro de leitura/interpretação ({type(error).__name__}); '
            'mantendo cache válido quando disponível'
        )
        logger.warning('Falha ao ler %s: %s', file, error)
        return cached[1] if cached else None


def load_reports(directory):
    path = Path(directory)
    warnings = []
    reports = {}
    if not path.exists():
        return [], [f'Pasta de exportação não encontrada: {path}']
    colony_dirs = sorted(item for item in (path / 'colonies').glob('*') if item.is_dir()) if (path / 'colonies').is_dir() else []
    candidates = []
    for folder in colony_dirs:
        for file in folder.glob('report_cycle_*.json'):
            report = _read_report(file, warnings)
            if report:
                candidates.append((report['_timestamp'], folder, report))
    active_folder = None
    active_id = active_name = None
    if candidates:
        _, active_folder, newest = max(candidates, key=lambda item: item[0])
        active_id = str(newest.get('ColonyId') or active_folder.name)
        active_name = newest.get('ColonyName')
        for file in active_folder.glob('report_cycle_*.json'):
            report = _read_report(file, warnings)
            if report:
                reports[report['Cycle']] = report
    else:
        for file in path.glob('report_cycle_*.json'):
            report = _read_report(file, warnings)
            if report:
                reports[report['Cycle']] = report

    if colony_dirs and active_folder and reports:
        first_active = min(reports)
        for file in path.glob('report_cycle_*.json'):
            report = _read_report(file, warnings)
            if report and report.get('ColonyId') is None and report['Cycle'] < first_active:
                reports.setdefault(report['Cycle'], report)
            # Copies for the active colony and reports for any other colony are ignored.
            elif report and report.get('ColonyId') not in (None, active_id):
                continue
    if not reports:
        return [], warnings
    current_cycle = max(reports, key=lambda item: reports[item]['_timestamp'])
    abandoned = sorted(cycle for cycle in reports if cycle > current_cycle)
    if abandoned:
        warnings.append(f'{len(abandoned)} ciclos de linha do tempo abandonada ocultos: {", ".join(map(str, abandoned))}')
    visible_cycles = sorted(cycle for cycle in reports if cycle <= current_cycle)
    missing = sorted(set(range(visible_cycles[0], current_cycle + 1)) - set(visible_cycles))
    if missing:
        warnings.append('Ciclos faltantes: ' + ', '.join(map(str, missing)))
    if len(abandoned) >= 50:
        warnings.append('Possível troca de colônia: 50 ou mais ciclos abandonados')
    if colony_dirs and len(colony_dirs) > 1:
        warnings.append(f'{len(colony_dirs)} colônias encontradas; exibindo {active_name or active_id}')
    return [reports[cycle] for cycle in visible_cycles], warnings


def entries(report, category):
    return [entry for entry in report.get('Entries', []) if entry.get('Category') == category]


def total(report, category):
    return next((entry for entry in entries(report, category) if entry.get('Context') is None), {})


def value(report, category, field='NetValue'):
    return float(total(report, category).get(field, 0) or 0)
