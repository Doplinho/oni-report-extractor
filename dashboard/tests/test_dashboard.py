import json
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import pytest
from urllib.request import urlopen

from oni_dashboard.app import (DEFAULT_EXPORT, MATERIAL_DEFAULTS, apply_x_range, build_figures, create_app, material_options,
                               default_export_dir, extract_x_range, format_brazilian,
                               is_user_zoom, _format_status)
from oni_dashboard.load import load_reports
from oni_dashboard.metrics import calculate, events, stress_data
from oni_dashboard import __main__ as cli
from oni_dashboard.metrics import source_breakdown

FIXTURES = Path(__file__).parent / 'fixtures' / 'export'
FIXTURES_V2 = Path(__file__).parent / 'fixtures' / 'export_v2'


def test_default_export_dir_uses_documents_and_has_no_user_path():
    target = default_export_dir()
    assert target.parts[-3:] == ('Klei', 'OxygenNotIncluded', 'export')
    assert DEFAULT_EXPORT.parts[-3:] == ('Klei', 'OxygenNotIncluded', 'export')
    source = Path(__file__).parents[1] / 'oni_dashboard' / 'app.py'
    assert 'C:\\Users' not in source.read_text(encoding='utf-8')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows known folder API')
def test_default_export_dir_matches_windows_documents_folder():
    documents = subprocess.check_output(
        ['powershell', '-NoProfile', '-Command', "[Environment]::GetFolderPath('MyDocuments')"],
        text=True,
    ).strip()
    assert default_export_dir() == Path(documents) / 'Klei' / 'OxygenNotIncluded' / 'export'


def test_default_export_dir_falls_back_when_windows_api_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setattr('oni_dashboard.app.ctypes.WinDLL',
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError('API unavailable')),
                        raising=False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert default_export_dir() == tmp_path / 'Documents' / 'Klei' / 'OxygenNotIncluded' / 'export'


def test_loads_all_fixture_cycles_without_warnings():
    reports, warnings = load_reports(FIXTURES)
    assert len(reports) == 83
    assert [reports[0]['Cycle'], reports[-1]['Cycle']] == [171, 253]
    assert warnings == []


def test_food_reconciles_for_all_fixture_cycles():
    reports, _ = load_reports(FIXTURES)
    result = calculate(reports)
    assert len(result) == 83
    assert result['food_reconciles'].all()


def test_food_reference_values():
    reports, _ = load_reports(FIXTURES)
    result = calculate(reports).set_index('cycle')
    assert result.loc[249, 'food_balance'] == 2437.649
    assert result.loc[249, 'food_rotted'] == -600
    assert result.loc[249, 'food_harvested'] == 10800
    assert result.loc[219, 'food_balance'] == 305.9
    assert result.loc[220, 'food_rotted'] == -18175.992


def test_energy_reference_totals():
    reports, _ = load_reports(FIXTURES)
    result = calculate(reports)
    assert round(result['energy_generated'].sum()) == 52485
    assert round(result['energy_balance'].sum()) == 171
    assert round(result['energy_net_created'].sum()) == 2326


def test_newest_timestamp_selects_timeline(tmp_path):
    for cycle in range(241, 254):
        shutil.copy(FIXTURES / f'report_cycle_{cycle}.json', tmp_path)
    path = tmp_path / 'report_cycle_241.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    report['Timestamp'] = '2099-01-01T00:00:00+00:00'
    path.write_text(json.dumps(report), encoding='utf-8')
    reports, warnings = load_reports(tmp_path)
    assert [report['Cycle'] for report in reports] == [241]
    assert any('12 ciclos de linha do tempo abandonada' in warning for warning in warnings)


def test_read_error_retains_cache_and_missing_cycle_warns(tmp_path):
    source = FIXTURES / 'report_cycle_171.json'
    path = tmp_path / source.name
    shutil.copy(source, path)
    good, _ = load_reports(tmp_path)
    assert len(good) == 1
    path.write_text('{corrupt json with different length', encoding='utf-8')
    retained, warnings = load_reports(tmp_path)
    assert retained[0]['Cycle'] == 171
    assert any('mantendo cache válido' in warning for warning in warnings)

    shutil.copy(FIXTURES / 'report_cycle_172.json', tmp_path)
    shutil.copy(FIXTURES / 'report_cycle_173.json', tmp_path)
    (tmp_path / 'report_cycle_172.json').unlink()
    reports, warnings = load_reports(tmp_path)
    assert [report['Cycle'] for report in reports] == [171, 173]
    assert any('172' in warning and 'faltantes' in warning for warning in warnings)


def test_filename_content_mismatch_is_discarded(tmp_path):
    report = json.loads((FIXTURES / 'report_cycle_171.json').read_text(encoding='utf-8-sig'))
    report['Cycle'] = 999
    (tmp_path / 'report_cycle_171.json').write_text(json.dumps(report), encoding='utf-8')
    reports, warnings = load_reports(tmp_path)
    assert reports == []
    assert any('diverge do nome' in warning for warning in warnings)


def test_events_include_incidents_and_duplicant_changes():
    reports, _ = load_reports(FIXTURES)
    event_list = events(reports)
    incident_cycles = {
        event['cycle'] for event in event_list if 'ToiletIncident' in event['text']
    }
    assert {187, 197, 211} <= incident_cycles
    assert any(event['cycle'] == 248 and event['text'] == 'Marie saiu dos relatórios'
               for event in event_list)
    assert any(event['cycle'] == 247 and event['text'] == 'Nisbet entrou nos relatórios'
               for event in event_list)
    assert event_list == sorted(event_list, key=lambda event: event['cycle'], reverse=True)


def test_unknown_json_fields_are_ignored(tmp_path):
    report = json.loads((FIXTURES / 'report_cycle_171.json').read_text(encoding='utf-8-sig'))
    report['FutureField'] = {'new': ['field']}
    (tmp_path / 'report_cycle_171.json').write_text(json.dumps(report), encoding='utf-8')
    reports, warnings = load_reports(tmp_path)
    assert len(reports) == 1
    assert warnings == []


def test_layout_and_all_graphs_build_with_fixture_data():
    reports, _ = load_reports(FIXTURES)
    app = create_app(FIXTURES)
    layout = app.layout()
    assert layout is not None
    graphs = [component for component in layout._traverse()
              if component.__class__.__name__ == 'Graph']
    assert graphs
    assert all(isinstance(graph.style, dict)
               and isinstance(graph.style.get('height'), str)
               and graph.style['height'].endswith('px')
               for graph in graphs)
    figures, _summaries, _leader = build_figures(reports)
    assert set(figures) == {'food', 'food-stock', 'oxygen', 'energy', 'materials', 'stress'}
    assert all(len(figure.data) > 0 for figure in figures.values())
    assert any(trace.name == 'Colheita' for trace in figures['food'].data)
    assert figures['food'].layout.barmode == 'relative'
    assert any(trace.name == 'Respiração' for trace in figures['oxygen'].data)
    assert any(trace.name == 'variação estimada armazenada' for trace in figures['energy'].data)
    assert figures['energy'].data[-2].y[0] == 0
    assert all(value is None or isinstance(value, float)
               for values in stress_data(reports).values() for value in values)


def test_threaded_server_handles_wait_and_simultaneous_layout_requests():
    app = create_app(FIXTURES)
    server = cli._create_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    idle_connection = socket.create_connection(('127.0.0.1', server.server_port), timeout=5)
    try:
        address = f'http://127.0.0.1:{server.server_port}/'
        started = time.monotonic()
        assert cli._wait_for_server(address, timeout=5)
        assert time.monotonic() - started < 5

        layout_url = address.rstrip('/') + '/_dash-layout'
        def request_layout():
            with urlopen(layout_url, timeout=5) as response:
                return response.status, response.read()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: request_layout(), range(2)))
        assert [status for status, _body in responses] == [200, 200]
        assert all(b'Dashboard ONI' in body for _status, body in responses)
    finally:
        idle_connection.close()
        server.shutdown()
        thread.join(timeout=5)


def test_possible_colony_switch_at_50_hidden_cycles(tmp_path):
    for cycle in range(201, 254):
        shutil.copy(FIXTURES / f'report_cycle_{cycle}.json', tmp_path)
    path = tmp_path / 'report_cycle_201.json'
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    report['Timestamp'] = '2099-01-01T00:00:00+00:00'
    path.write_text(json.dumps(report), encoding='utf-8')
    _reports, warnings = load_reports(tmp_path)
    assert any('50 ou mais ciclos' in warning.lower() for warning in warnings)


def test_is_user_zoom_ignores_initial_layout_but_accepts_ranges():
    assert not is_user_zoom({'autosize': True})
    assert is_user_zoom({'xaxis.range': [10, 20]})
    assert is_user_zoom({'xaxis.range[0]': 10})
    assert is_user_zoom({'xaxis.autorange': True})


def test_all_span_covers_all_cycles_and_food_outflows_are_negative():
    reports, _ = load_reports(FIXTURES)
    figures, _, _ = build_figures(reports, span='all')
    assert tuple(figures['food'].layout.xaxis.range) == (170.5, 253.5)
    frame = calculate(reports)
    assert (frame['food_consumed'] <= 0).all()
    assert (frame['food_rotted'] <= 0).all()


def test_stress_absence_and_leader_only_among_currently_present():
    reports, _ = load_reports(FIXTURES)
    data, summaries, leader = __import__('oni_dashboard.metrics', fromlist=['stress_summary']).stress_summary(reports)
    assert any(value is None for values in data.values() for value in values)
    assert leader != 'Marie'
    assert not summaries['Marie']['present_now']


def test_read_error_retries_even_when_signature_is_unchanged(tmp_path):
    source = FIXTURES / 'report_cycle_171.json'
    path = tmp_path / source.name
    good_text = source.read_text(encoding='utf-8-sig')
    path.write_text('{broken json'.ljust(len(good_text)), encoding='utf-8')
    reports, warnings = load_reports(tmp_path)
    assert reports == []
    assert warnings
    path.write_text(good_text, encoding='utf-8')
    reports, _ = load_reports(tmp_path)
    assert [report['Cycle'] for report in reports] == [171]


def test_status_formatter_updates_from_loaded_report_without_revision():
    reports, warnings = load_reports(FIXTURES)
    status = _format_status(reports, warnings, 'jogo fechado')
    assert 'ciclo 253' in status
    assert 'idade:' in status
    assert '/' in status and ':' in status


def test_manual_x_range_extracts_and_applies_to_new_figures():
    assert extract_x_range({'xaxis.range[0]': 12, 'xaxis.range[1]': 18}) == [12, 18]
    assert extract_x_range({'xaxis.range': [12, 18]}) == [12, 18]
    assert extract_x_range({'xaxis.autorange': True}) is None
    import plotly.graph_objects as go
    figure = apply_x_range(go.Figure(), [12, 18])
    assert tuple(figure.layout.xaxis.range) == (12, 18)
    reports, _ = load_reports(FIXTURES)
    figures, _, _ = build_figures(reports, manual_graphs=['food'], zoom_ranges={'food': [210, 220]})
    assert tuple(figures['food'].layout.xaxis.range) == (210, 220)


def test_redraw_callback_preserves_manual_zoom_and_reset_follow_clears_it():
    app = create_app(FIXTURES)
    client = app.server.test_client()
    callback_key, callback = next(
        (key, value) for key, value in app.callback_map.items()
        if value['callback'].__name__ == 'redraw'
    )
    selected_range = [210, 220]
    state_values = {
        'manual-graphs.data': ['oxygen'],
        'reset-count.data': 0,
        'zoom-ranges.data': {'oxygen': selected_range},
    }

    def post(trigger, relayout=None):
        input_values = {
            'revision-store.data': None,
            'material-filter.value': ['Algae', 'Carbon', 'Cuprite', 'Copper', 'GoldAmalgam', 'IronOre', 'Iron'],
            'range.value': '30',
            'reset-follow.n_clicks': 1 if trigger == 'reset-follow.n_clicks' else 0,
            'food.relayoutData': None,
            'food-stock.relayoutData': None,
            'oxygen.relayoutData': relayout,
            'energy.relayoutData': None,
            'materials.relayoutData': None,
            'stress.relayoutData': None,
        }
        inputs = [
            {**item, 'value': input_values[f"{item['id']}.{item['property']}"]}
            for item in callback['inputs']
        ]
        states = [
            {**item, 'value': state_values[f"{item['id']}.{item['property']}"]}
            for item in callback['state']
        ]
        outputs = [
            {'id': output.component_id, 'property': output.component_property}
            for output in callback['output']
        ]
        return client.post('/_dash-update-component', json={
            'output': callback_key,
            'outputs': outputs,
            'inputs': inputs,
            'state': states,
            'changedPropIds': [trigger],
        })

    response = post('oxygen.relayoutData', {'xaxis.range': selected_range})
    assert response.status_code == 200
    oxygen = response.get_json()['response']['oxygen']['figure']
    assert oxygen['layout']['xaxis']['range'] == selected_range

    response = post('material-filter.value')
    assert response.status_code == 200
    result = response.get_json()['response']
    assert result['manual-graphs']['data'] == ['oxygen']
    assert result['zoom-ranges']['data'] == {'oxygen': selected_range}

    response = post('reset-follow.n_clicks')
    assert response.status_code == 200
    result = response.get_json()['response']
    assert result['manual-graphs']['data'] == []
    assert result['reset-follow']['style']['display'] == 'none'


def test_recent_stress_heatmap_omits_rows_without_visible_values():
    reports, _ = load_reports(FIXTURES)
    recent, _, _ = build_figures(reports, span='30')
    all_cycles, _, _ = build_figures(reports, span='all')
    recent_names = set(recent['stress'].data[0].y)
    all_names = set(all_cycles['stress'].data[0].y)
    assert 'Ren' not in recent_names
    assert 'Banhi' not in recent_names
    assert {'Ren', 'Banhi'} <= all_names


def test_brazilian_number_format():
    assert format_brazilian(3590.6) == '3.590,6'


def test_source_has_no_replacement_question_marks_and_layout_wait_text():
    for path in (Path(__file__).parents[1] / 'oni_dashboard').rglob('*.py'):
        content = path.read_text(encoding='utf-8')
        assert '\ufffd' not in content
        assert not any(a == '?' and b.isalpha() for a, b in zip(content, content[1:]))
    layout_text = Path(__file__).parents[1] / 'oni_dashboard' / 'app.py'
    assert 'aguardando atualização do mod' in layout_text.read_text(encoding='utf-8')


def test_v2_snapshot_values_and_never_uses_battery_joules():
    reports, _ = load_reports(FIXTURES_V2)
    row = calculate(reports).set_index('cycle').loc[256]
    assert row.food_stock_kcal == pytest.approx(17132.928)
    assert row.energy_stored_kj == pytest.approx(288.929)
    assert row.materials['Carbon'] == pytest.approx(4187.2, abs=.1)
    assert row.materials['GoldAmalgam'] == pytest.approx(12117.9, abs=.1)
    assert row.energy_stored_kj != pytest.approx(sum(w.get('BatteryJoules', 0) for w in reports[-1]['Snapshot']['Worlds']) / 1000)


def test_legacy_and_v2_join_has_no_duplicate_or_gap(tmp_path):
    for cycle in range(171, 254): shutil.copy(FIXTURES / f'report_cycle_{cycle}.json', tmp_path)
    source = next(FIXTURES_V2.glob('colonies/*/report_cycle_256.json')).parent
    for cycle in range(254, 257):
        shutil.copy(source / f'report_cycle_{cycle}.json', tmp_path / f'report_cycle_{cycle}.json')
    reports, warnings = load_reports(tmp_path)
    assert [r['Cycle'] for r in reports] == list(range(171, 257))
    assert not any('faltantes' in w for w in warnings)


def test_colony_join_ignores_active_copies_and_other_colony_loose_file(tmp_path):
    colonies = tmp_path / 'colonies'
    active_id = next((FIXTURES_V2 / 'colonies').iterdir()).name
    shutil.copytree(FIXTURES_V2 / 'colonies' / active_id, colonies / active_id)
    shutil.copy(FIXTURES_V2 / 'colonies' / active_id / 'report_cycle_254.json', tmp_path / 'report_cycle_254.json')
    other = json.loads((tmp_path / 'report_cycle_254.json').read_text(encoding='utf-8-sig'))
    other['ColonyId'] = 'another-colony'; other['Cycle'] = 252
    (tmp_path / 'report_cycle_252.json').write_text(json.dumps(other), encoding='utf-8')
    legacy = json.loads((tmp_path / 'report_cycle_254.json').read_text(encoding='utf-8-sig'))
    legacy.pop('ColonyId', None); legacy['Cycle'] = 253
    (tmp_path / 'report_cycle_253.json').write_text(json.dumps(legacy), encoding='utf-8')
    reports, _ = load_reports(tmp_path)
    cycles = [r['Cycle'] for r in reports]
    assert cycles.count(254) == 1 and 252 not in cycles and 253 in cycles


def test_two_colonies_choose_most_recent_and_exclude_late_legacy(tmp_path):
    colonies = tmp_path / 'colonies'
    for index, name in enumerate(('Older', 'Newest')):
        folder = colonies / f'c{index}'; folder.mkdir(parents=True)
        source = next((FIXTURES_V2 / 'colonies').glob('*/report_cycle_256.json'))
        report = json.loads(source.read_text(encoding='utf-8-sig'))
        report.update(ColonyId=f'c{index}', ColonyName=name, Cycle=256,
                      Timestamp=f'2026-01-0{index+1}T00:00:00+00:00')
        (folder / 'report_cycle_256.json').write_text(json.dumps(report), encoding='utf-8')
    legacy = json.loads((next((FIXTURES_V2 / 'colonies').glob('*/report_cycle_256.json'))).read_text(encoding='utf-8-sig'))
    legacy.pop('ColonyId', None); legacy['Cycle'] = 256
    (tmp_path / 'report_cycle_256.json').write_text(json.dumps(legacy), encoding='utf-8')
    reports, warnings = load_reports(tmp_path)
    assert reports[-1]['ColonyName'] == 'Newest'
    assert any('2 colônias' in warning and 'Newest' in warning for warning in warnings)


def test_pre_snapshot_stock_is_none_and_stock_plot_has_gaps():
    reports, _ = load_reports(FIXTURES)
    frame = calculate(reports)
    assert frame.food_stock_kcal.isna().all()
    figures, _, _ = build_figures(reports)
    assert all(value is None for value in figures['food-stock'].data[0].y)


def test_food_cycles_remaining_hand_calculation_and_zero_consumption():
    reports, _ = load_reports(FIXTURES_V2)
    report = dict(reports[-1]); report['Cycle'] = 1
    report['Snapshot'] = {'Worlds': [{'RationKcalRaw': 100000}], 'Duplicants': []}
    report['Entries'] = [e for e in report['Entries'] if e.get('Category') != 'CaloriesCreated']
    report['Entries'] += [{'Category':'CaloriesCreated','Context':None,'NetValue':0,'PositiveValue':0,'NegativeValue':0}]
    assert calculate([report]).iloc[-1].food_cycles_remaining is None
    report['Entries'].append({'Category':'CaloriesCreated','Context':'Ada','NegativeValue':-5000})
    report['Snapshot']['Worlds'][0]['RationKcalRaw'] = 50000
    assert calculate([report]).iloc[-1].food_cycles_remaining == pytest.approx(10)


def test_sources_strip_links_sum_names_and_exclude_duplicants():
    report = {'Entries': [
        {'Category':'EnergyCreated','Notes':[{'Name':'<link="x">Generator</link>','Value':1000}]},
        {'Category':'EnergyCreated','Notes':[{'Name':'Generator','Value':2000}]},
        {'Category':'OxygenCreated','Notes':[{'Name':'Ada','Value':900},{'Name':'Oxygen Diffuser','Value':700}]},
    ], 'Snapshot': {'Duplicants':[{'Name':'Ada'}]}}
    result = source_breakdown(report)
    assert result['generators'] == [('Generator', 3000)]
    assert result['oxygen'] == [('Oxygen Diffuser', 700)]
    assert source_breakdown({'Entries':[]})['generators'] == []


def test_real_redraw_post_v2_and_materials_zoom():
    app = create_app(FIXTURES_V2); client = app.server.test_client()
    callback_key, callback = next((key, value) for key, value in app.callback_map.items() if value['callback'].__name__ == 'redraw')
    def post(trigger, zoom=None):
        values = {'revision-store.data':None, 'range.value':'30', 'reset-follow.n_clicks':0,
                  'material-filter.value':['Algae','Carbon','Cuprite','Copper','GoldAmalgam','IronOre','Iron'],
                  **{f'{graph}.relayoutData': ({'xaxis.range':[254,256]} if graph == 'materials' and zoom else None)
                     for graph in ('food','food-stock','oxygen','energy','materials','stress')}}
        inputs = [{**item,'value':values[f"{item['id']}.{item['property']}"]} for item in callback['inputs']]
        states = [{**item,'value': {'manual-graphs.data':[],'reset-count.data':0,'zoom-ranges.data':{}}[f"{item['id']}.{item['property']}"]} for item in callback['state']]
        outputs = [{'id':o.component_id,'property':o.component_property} for o in callback['output']]
        return client.post('/_dash-update-component',json={'output':callback_key,'outputs':outputs,'inputs':inputs,'state':states,'changedPropIds':[trigger]})
    for zoom in (False, True):
        response = post('materials.relayoutData' if zoom else 'revision-store.data', zoom)
        assert response.status_code == 200
        payload = response.get_json()['response']
        assert len(payload['cards']['children']) == 5
        assert payload['materials']['figure']['data']
        if zoom: assert payload['materials']['figure']['layout']['xaxis']['range'] == [254,256]


def test_material_filter_options_and_selection_behaviour(tmp_path):
    reports, _ = load_reports(FIXTURES_V2)
    generated = []
    for report in reports:
        copied = copy.deepcopy(report)
        copied['SchemaVersion'] = 3
        copied.setdefault('Snapshot', {}).setdefault('Worlds', [{}])[0].setdefault('Materials', []).append(
            {'Tag': 'Zinc', 'Name': 'Zinco', 'Kg': 4})
        generated.append(copied)
    generated_dir = tmp_path / 'generated-v3'
    generated_dir.mkdir()
    for report in generated:
        serializable = {key: value for key, value in report.items() if not key.startswith('_')}
        (generated_dir / f"report_cycle_{report['Cycle']}.json").write_text(
            json.dumps(serializable, ensure_ascii=False, default=lambda value: value.isoformat()), encoding='utf-8')
    generated, _ = load_reports(generated_dir)
    assert next(option for option in material_options(generated) if option['value'] == 'Zinc') == {'label': 'Zinco', 'value': 'Zinc'}
    # Name beats fallback; fallback beats the raw tag.
    carbon = next(item for item in generated[-1]['Snapshot']['Worlds'][0]['Materials'] if item.get('Tag') == 'Carbon')
    carbon['Name'] = 'Carvão refinado'
    assert next(item for item in material_options(generated) if item['value'] == 'Carbon')['label'] == 'Carvão refinado'
    assert next(item for item in material_options([{'Snapshot': {'Worlds': [{'Materials': [{'Tag': 'Carbon'}]}]}}]) if item['value'] == 'Carbon')['label'] == 'Coal'
    assert next(item for item in material_options([{'Snapshot': {'Worlds': [{'Materials': [{'Tag': 'Zzz'}]}]}}]) if item['value'] == 'Zzz')['label'] == 'Zzz'

    old = copy.deepcopy(reports)
    tag = 'Zinc'
    for report in old:
        report['SchemaVersion'] = 2
    old[-1].setdefault('Snapshot', {}).setdefault('Worlds', [{}])[0].setdefault('Materials', []).append({'Tag': tag, 'Kg': 5})
    old[0].setdefault('Snapshot', {}).setdefault('Worlds', [{}])[0].setdefault('Materials', [])
    old[0]['Snapshot']['Worlds'][0]['Materials'] = [m for m in old[0]['Snapshot']['Worlds'][0]['Materials'] if m.get('Tag') != tag]
    current = copy.deepcopy(old)
    current[0]['SchemaVersion'] = 3
    assert calculate(old).iloc[0][f'material_tag_{tag}'] != calculate(old).iloc[0][f'material_tag_{tag}']
    assert calculate(current).iloc[0][f'material_tag_{tag}'] == 0

    figures, _, _ = build_figures(generated, selected_materials=['Zinc'])
    assert [trace.meta['tag'] for trace in figures['materials'].data] == ['Zinc']
    empty, _, _ = build_figures(generated, selected_materials=[])
    assert not empty['materials'].data
    assert empty['materials'].layout.annotations[0].text == 'Selecione materiais na lista'
    both, _, _ = build_figures(generated, selected_materials=['Zinc', 'Carbon'])
    zinc_alone, _, _ = build_figures(generated, selected_materials=['Zinc'])
    assert next(trace for trace in both['materials'].data if trace.meta['tag'] == 'Zinc').line.color == zinc_alone['materials'].data[0].line.color
    defaults_figure, _, _ = build_figures(generated)
    default_colors = [next(trace for trace in defaults_figure['materials'].data if trace.meta['tag'] == tag).line.color for tag in MATERIAL_DEFAULTS]
    assert len(set(default_colors)) == len(MATERIAL_DEFAULTS)
    with_other, _, _ = build_figures(generated, selected_materials=['Algae', 'Zinc'])
    algae_alone, _, _ = build_figures(generated, selected_materials=['Algae'])
    assert next(trace for trace in with_other['materials'].data if trace.meta['tag'] == 'Algae').line.color == algae_alone['materials'].data[0].line.color


def test_material_dropdown_options_callback_no_update_and_layout_props():
    app = create_app(FIXTURES_V2)
    layout = app.layout()
    dropdown = layout.children[14].children[1]
    assert dropdown.id == 'material-filter' and dropdown.multi and dropdown.searchable
    assert dropdown.persistence and dropdown.persistence_type == 'local'
    assert set(MATERIAL_DEFAULTS).issubset({option['value'] for option in dropdown.options})
    from dash.dcc import Dropdown
    valid_label_keys = set(Dropdown.Labels.__annotations__)
    assert set(dropdown.labels) <= valid_label_keys
    assert dropdown.labels == {
        'select_all': 'Selecionar todos',
        'deselect_all': 'Limpar sele\u00e7\u00e3o',
        'selected_count': '{num_selected} selecionados',
        'search': 'Pesquisar',
        'clear_search': 'Limpar pesquisa',
        'clear_selection': 'Limpar sele\u00e7\u00e3o',
        'no_options_found': 'Nenhum material encontrado',
    }
    key, callback = next((key, item) for key, item in app.callback_map.items() if item['callback'].__name__ == 'update_material_options')
    options = material_options(load_reports(FIXTURES_V2)[0])
    response = app.server.test_client().post('/_dash-update-component', json={
        'output': key, 'outputs': {'id': 'material-filter', 'property': 'options'},
        'inputs': [{'id': 'revision-store', 'property': 'data', 'value': []}],
        'state': [{'id': 'material-filter', 'property': 'options', 'value': options}],
        'changedPropIds': ['revision-store.data'],
    })
    assert response.status_code == 200
    assert response.get_json()['response'] == {}


def test_material_units_axes_legend_and_table():
    reports, _ = load_reports(FIXTURES_V2)
    reports = reports[-1:]
    report = copy.deepcopy(reports[0])
    report['SchemaVersion'] = 3
    materials = report.setdefault('Snapshot', {}).setdefault('Worlds', [{}])[0].setdefault('Materials', [])
    materials.extend([
        {'Tag': 'AtmoSuit', 'Name': 'Atmo Suit', 'Kg': 5, 'Unit': 'un'},
        {'Tag': 'MealwoodSeed', 'Name': 'Mealwood Seed', 'Kg': 1.077, 'Unit': 'un'},
        {'Tag': 'Copper', 'Name': 'Copper', 'Kg': 12, 'Unit': 'kg'},
    ])
    frame = calculate([report])
    assert 'material_units' not in frame.columns
    no_unit = copy.deepcopy(report)
    del no_unit['Snapshot']['Worlds'][0]['Materials'][-3]['Unit']
    assert 'material_units' not in calculate([no_unit]).columns

    both, _, _ = build_figures([report], selected_materials=['AtmoSuit', 'Copper'])
    figure = both['materials']
    assert figure.layout.yaxis2.title.text == 'unidades'
    assert figure.layout.yaxis2.overlaying == 'y' and figure.layout.yaxis2.side == 'right'
    assert {trace.meta['tag']: trace.yaxis for trace in figure.data} == {'AtmoSuit': 'y2', 'Copper': 'y'}
    assert next(trace for trace in figure.data if trace.meta['tag'] == 'AtmoSuit').name == 'Atmo Suit (un)'
    kg_only, _, _ = build_figures([report], selected_materials=['Copper'])
    assert 'yaxis2' not in kg_only['materials'].layout
    un_only, _, _ = build_figures([report], selected_materials=['AtmoSuit'])
    assert un_only['materials'].data[0].yaxis == 'y2'

    app = create_app(FIXTURES_V2)
    layout = app.layout()
    dropdown = layout.children[14].children[1]
    assert dropdown.id == 'material-filter'


def test_material_table_keeps_unit_from_earlier_report_when_missing_latest(monkeypatch):
    reports, _ = load_reports(FIXTURES_V2)
    earlier = copy.deepcopy(reports[-2])
    latest = copy.deepcopy(reports[-1])
    earlier['SchemaVersion'] = latest['SchemaVersion'] = 3
    earlier.setdefault('Snapshot', {}).setdefault('Worlds', [{}])[0].setdefault('Materials', []).append(
        {'Tag': 'AtmoSuit', 'Name': 'Atmo Suit', 'Kg': 5, 'Unit': 'un'}
    )
    latest['Snapshot']['Worlds'][0]['Materials'] = [
        item for item in latest['Snapshot']['Worlds'][0].get('Materials', [])
        if item.get('Tag') != 'AtmoSuit'
    ]
    monkeypatch.setattr('oni_dashboard.app.load_reports', lambda _path: ([earlier, latest], []))
    app = create_app(FIXTURES_V2)
    key, callback = next((key, item) for key, item in app.callback_map.items()
                         if item['callback'].__name__ == 'redraw')
    inputs = []
    for item in callback['inputs']:
        if item['id'] == 'material-filter': value = ['AtmoSuit']
        elif item['id'] == 'range': value = 'all'
        elif item['id'] == 'reset-follow': value = 0
        elif item['id'] == 'revision-store': value = None
        else: value = None
        inputs.append({**item, 'value': value})
    states = [{**item, 'value': [] if item['id'] == 'manual-graphs' else 0 if item['id'] == 'reset-count' else {}}
              for item in callback['state']]
    outputs = [{'id': output.component_id, 'property': output.component_property} for output in callback['output']]
    response = app.server.test_client().post('/_dash-update-component', json={
        'output': key, 'outputs': outputs, 'inputs': inputs, 'state': states,
        'changedPropIds': ['material-filter.value'],
    })
    assert response.status_code == 200
    table = response.get_json()['response']['materials-table']['children']
    rows = table['props']['children'][1]['props']['children']
    atmo_row = next(row for row in rows if row['props']['children'][0]['props']['children'] == 'Atmo Suit')
    assert atmo_row['props']['children'][2]['props']['children'] == 'un'


def test_edge_resolution_uses_program_files_fallback_and_webbrowser(tmp_path, monkeypatch):
    import os, sys
    edge = tmp_path / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'; edge.parent.mkdir(parents=True); edge.touch()
    calls=[]
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setattr(os,'environ',{'ProgramFiles(x86)':str(tmp_path)})
    monkeypatch.setattr('shutil.which',lambda _name:None)
    monkeypatch.setattr('subprocess.Popen',lambda args,**kwargs:calls.append(args))
    cli._open_dashboard('http://127.0.0.1:8050/')
    assert calls == [[str(edge),'--app=http://127.0.0.1:8050/']]
    monkeypatch.setattr(os,'environ',{})
    opened=[]; monkeypatch.setattr(cli.webbrowser,'open',lambda address:opened.append(address))
    cli._open_dashboard('http://127.0.0.1:8050/')
    assert opened == ['http://127.0.0.1:8050/']


def test_open_argument_opens_existing_instance_without_starting_server(monkeypatch):
    import sys
    monkeypatch.setattr(sys,'platform','win32')
    class Kernel:
        def CreateMutexW(self,*_args): return 1
    monkeypatch.setattr(cli.ctypes,'WinDLL',lambda *_args,**_kwargs:Kernel(),raising=False)
    monkeypatch.setattr(cli.ctypes,'get_last_error',lambda:183)
    opened=[]; monkeypatch.setattr(cli,'_wait_for_server',lambda address:True)
    monkeypatch.setattr(cli,'_open_dashboard',lambda address:opened.append(address))
    monkeypatch.setattr(sys,'argv',['oni_dashboard','--open','--port','8999'])
    assert cli.main() == 0
    assert opened == ['http://127.0.0.1:8999/']


def test_open_argument_starts_server_then_opens_without_instance(monkeypatch):
    import sys
    class Kernel:
        def CreateMutexW(self,*_args): return 1
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setattr(cli.ctypes,'WinDLL',lambda *_args,**_kwargs:Kernel(),raising=False)
    monkeypatch.setattr(cli.ctypes,'get_last_error',lambda:0)
    monkeypatch.setattr(cli,'create_app',lambda _path: type('App',(),{'server':object(),'run':lambda *a,**k:None})())
    monkeypatch.setattr(cli,'_wait_for_server',lambda address:True)
    opened=[]; monkeypatch.setattr(cli,'_open_dashboard',lambda address:opened.append(address))
    monkeypatch.setattr(cli.threading.Thread,'start',lambda self:None)
    monkeypatch.setattr(cli.time,'sleep',lambda _seconds:(_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(sys,'argv',['oni_dashboard','--open','--port','8998'])
    with pytest.raises(KeyboardInterrupt): cli.main()
    assert opened == ['http://127.0.0.1:8998/']
