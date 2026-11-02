"""Dash interface for local Oxygen Not Included reports."""
from datetime import datetime, timezone
import ctypes
from pathlib import Path
import subprocess
import sys
import time

from dash import Dash, Input, Output, State, dcc, html, callback_context, no_update
import plotly.graph_objects as go

from .load import has_read_errors, load_reports, revision
from .metrics import calculate, events, stress_summary, source_breakdown


def default_export_dir():
    """Return the ONI export directory under the current user's Documents folder."""
    documents = None
    if sys.platform == 'win32':
        try:
            class GUID(ctypes.Structure):
                _fields_ = [('Data1', ctypes.c_ulong), ('Data2', ctypes.c_ushort),
                            ('Data3', ctypes.c_ushort), ('Data4', ctypes.c_ubyte * 8)]

            folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                             (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            result = ctypes.c_wchar_p()
            shell32 = ctypes.WinDLL('shell32', use_last_error=True)
            get_folder = shell32.SHGetKnownFolderPath
            get_folder.argtypes = [ctypes.POINTER(GUID), ctypes.c_ulong, ctypes.c_void_p,
                                   ctypes.POINTER(ctypes.c_wchar_p)]
            get_folder.restype = ctypes.c_long
            if get_folder(ctypes.byref(folder_id), 0, None, ctypes.byref(result)) == 0 and result.value:
                documents = Path(result.value)
                ctypes.WinDLL('ole32').CoTaskMemFree(result)
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    if documents is None:
        documents = Path.home() / 'Documents'
    return documents / 'Klei' / 'OxygenNotIncluded' / 'export'


DEFAULT_EXPORT = default_export_dir()
GRAPH_IDS = ('food', 'food-stock', 'oxygen', 'energy', 'materials', 'stress')


def is_user_zoom(relayout):
    """True only for a user supplied x-axis range, including autorange reset."""
    if not isinstance(relayout, dict):
        return False
    return any(key in relayout for key in ('xaxis.range', 'xaxis.range[0]', 'xaxis.range[1]', 'xaxis.autorange'))


def extract_x_range(relayout):
    """Return an explicit x range from Plotly relayout data, if present."""
    if not isinstance(relayout, dict) or relayout.get('xaxis.autorange'):
        return None
    value = relayout.get('xaxis.range')
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return list(value)
    start, end = relayout.get('xaxis.range[0]'), relayout.get('xaxis.range[1]')
    return [start, end] if start is not None and end is not None else None


def apply_x_range(figure, stored_range):
    """Apply a stored manual range to a freshly built figure."""
    if stored_range and len(stored_range) == 2:
        figure.update_xaxes(range=list(stored_range), autorange=False)
    return figure


def format_brazilian(value):
    """Format a numeric value with Brazilian thousands and decimal separators."""
    return f'{value:,.1f}'.replace(',', '\0').replace('.', ',').replace('\0', '.')


def _figure_style(figure, graph_id, follows, last_cycle, span='30', reset_count=0, stored_range=None):
    figure.update_layout(
        template='plotly_dark',
        uirevision=f'{graph_id}-{reset_count}',
        margin={'l': 55, 'r': 20, 't': 90, 'b': 100},
        legend={'orientation': 'h', 'y': -0.25, 'x': 0},
    )
    figure.update_xaxes(title='Ciclo')
    if follows and last_cycle is not None:
        if span == 'all':
            first_cycle = min(
                (min(trace.x) for trace in figure.data if trace.x is not None and len(trace.x)),
                default=last_cycle,
            )
            figure.update_xaxes(range=[first_cycle - 0.5, last_cycle + 0.5])
        else:
            figure.update_xaxes(range=[max(0, last_cycle - 29.5), last_cycle + 0.5])
    if not follows:
        apply_x_range(figure, stored_range)
    return figure


MATERIAL_FALLBACK_NAMES = {'Algae': 'Algae', 'Carbon': 'Coal', 'Cuprite': 'Copper Ore', 'Copper': 'Copper', 'GoldAmalgam': 'Gold Amalgam', 'IronOre': 'Iron Ore', 'Iron': 'Iron'}
MATERIAL_DEFAULTS = ['Algae', 'Carbon', 'Cuprite', 'Copper', 'GoldAmalgam', 'IronOre', 'Iron']
MATERIAL_COLORS = ('#2E91E5','#E15F99','#1CA71C','#FB0D0D','#DA16FF','#B68100','#750D86','#EB663B','#511CFB','#00A08B','#FB00D1','#FC0080','#B2828D','#6C7C32','#778AAE','#862A16','#A777F1','#620042','#1616A7','#DA60CA','#6C4516','#0D2A63','#AF0038','#6F6E00')


def material_options(reports):
    return _material_data(reports)[0]


def _material_data(reports):
    """Build the shared material names, options, and stable color assignments."""
    names, tags = {}, set(MATERIAL_DEFAULTS)
    for report in reports:
        for world in ((report.get('Snapshot') or {}).get('Worlds') or []):
            for item in world.get('Materials') or []:
                tag = item.get('Tag')
                if tag:
                    tags.add(tag)
                    if item.get('Name'):
                        names[tag] = item['Name']
    options = [{'label': names.get(tag) or MATERIAL_FALLBACK_NAMES.get(tag) or tag, 'value': tag} for tag in tags]
    options = sorted(options, key=lambda option: (option['label'].casefold(), option['value']))
    by_tag = {option['value']: option['label'] for option in options}
    ordered = list(MATERIAL_DEFAULTS)
    for report in reports:
        for world in ((report.get('Snapshot') or {}).get('Worlds') or []):
            for item in world.get('Materials') or []:
                tag = item.get('Tag')
                if tag and tag not in ordered:
                    ordered.append(tag)
    colors = {tag: MATERIAL_COLORS[index % len(MATERIAL_COLORS)] for index, tag in enumerate(ordered)}
    return options, by_tag, colors


def build_figures(reports, span='30', manual_graphs=(), reset_count=0, zoom_ranges=None, selected_materials=None):
    frame = calculate(reports)
    visible_reports = reports if span == 'all' else reports[-30:]
    visible = frame if span == 'all' else frame.tail(30).copy()
    last_cycle = reports[-1]['Cycle'] if reports else None
    following = set(manual_graphs)
    figures = {}

    food = go.Figure()
    if not visible.empty:
        x = visible['cycle']
        food.add_bar(x=x, y=visible['food_harvested'], name='Colheita')
        food.add_bar(x=x, y=visible['food_butchered'], name='Abate')
        food.add_bar(x=x, y=visible['food_consumed'], name='Consumo')
        food.add_bar(x=x, y=visible['food_rotted'], name='Apodrecida')
        food.add_scatter(x=x, y=visible['food_balance'], mode='lines+markers', name='Saldo')
        food.add_scatter(x=x, y=visible['food_minimum_10'], mode='lines', line={'width': 0},
                         showlegend=False, hoverinfo='skip')
        food.add_scatter(x=x, y=visible['food_maximum_10'], mode='lines', line={'width': 0},
                         fill='tonexty', fillcolor='rgba(99, 179, 237, 0.12)',
                         name='Faixa mín–máx (10 ciclos)', zorder=0)
        food.add_scatter(x=x, y=visible['food_average_10'], mode='lines', name='Média (10 ciclos)')
    food.update_layout(title='Comida', yaxis_title='kcal', barmode='relative')
    figures['food'] = _figure_style(food, 'food', 'food' not in following, last_cycle, span, reset_count, (zoom_ranges or {}).get('food'))

    stock = go.Figure()
    if not visible.empty:
        stock.add_scatter(x=visible['cycle'], y=visible['food_stock_kcal'], mode='lines+markers', name='Reserva')
    stock.update_layout(title='Reserva de comida', yaxis_title='kcal')
    figures['food-stock'] = _figure_style(stock, 'food-stock', 'food-stock' not in following, last_cycle, span, reset_count, (zoom_ranges or {}).get('food-stock'))

    oxygen = go.Figure()
    if not visible.empty:
        x = visible['cycle']
        oxygen.add_scatter(x=x, y=visible['oxygen_produced'], mode='lines', name='Produzido')
        oxygen.add_scatter(x=x, y=visible['oxygen_breathing'], mode='lines', name='Respiração')
        oxygen.add_scatter(x=x, y=visible['oxygen_balance'], mode='lines', name='Saldo')
        oxygen.add_scatter(x=x, y=visible['oxygen_average_10'], mode='lines', name='Média (10 ciclos)')
    oxygen.update_layout(title='Oxigênio', yaxis_title='kg')
    figures['oxygen'] = _figure_style(oxygen, 'oxygen', 'oxygen' not in following, last_cycle, span, reset_count, (zoom_ranges or {}).get('oxygen'))

    energy = go.Figure()
    if not visible.empty:
        x = visible['cycle']
        energy.add_scatter(x=x, y=visible['energy_generated'], mode='lines', name='Gerada')
        energy.add_scatter(x=x, y=visible['energy_consumed'], mode='lines', name='Consumida')
        energy.add_scatter(x=x, y=visible['energy_wasted'], mode='lines', name='Desperdiçada')
        energy.add_scatter(x=x, y=visible['energy_balance'], mode='lines', name='Saldo real')
        estimate = visible['energy_balance'].cumsum() - visible['energy_balance'].iloc[0]
        energy.add_scatter(x=x, y=estimate, mode='lines', name='variação estimada armazenada')
        energy.add_scatter(x=x, y=visible['energy_stored_kj'], mode='lines+markers', name='Armazenada')
    energy.update_layout(
        title='Energia', yaxis_title='kJ',
        annotations=[{'text': 'A variação estimada não mede a carga: use a linha Armazenada.',
                      'xref': 'paper', 'yref': 'paper', 'x': 0, 'y': 1.12,
                      'showarrow': False, 'xanchor': 'left'}],
    )
    figures['energy'] = _figure_style(energy, 'energy', 'energy' not in following, last_cycle, span, reset_count, (zoom_ranges or {}).get('energy'))

    materials = go.Figure()
    selected_materials = MATERIAL_DEFAULTS if selected_materials is None else set(selected_materials)
    available_tags = sorted(set(MATERIAL_DEFAULTS) | ({tag for values in frame['materials'] if isinstance(values, dict) for tag in values} if not frame.empty else set()))
    _options, name_by_tag, colors = _material_data(reports)
    for tag in available_tags:
        if tag not in selected_materials:
            continue
        column = f'material_tag_{tag}'
        if column in visible:
            materials.add_scatter(x=visible['cycle'], y=visible[column], mode='lines+markers', name=name_by_tag.get(tag) or MATERIAL_FALLBACK_NAMES.get(tag, tag), line={'color': colors[tag]}, meta={'tag': tag})
    materials.update_layout(title='Materiais disponíveis', yaxis_title='kg')
    if not selected_materials:
        materials.add_annotation(text='Selecione materiais na lista', xref='paper', yref='paper', x=.5, y=.5, showarrow=False, font={'size': 16})
    figures['materials'] = _figure_style(materials, 'materials', 'materials' not in following, last_cycle, span, reset_count, (zoom_ranges or {}).get('materials'))

    stress_values, summaries, leader = stress_summary(reports)
    visible_stress = {
        name: values[-len(visible_reports):] if visible_reports else []
        for name, values in stress_values.items()
    }
    if span != 'all' and visible_reports:
        visible_stress = {name: values for name, values in visible_stress.items()
                          if any(value is not None for value in values)}
    magnitudes = sorted(
        abs(delta) for values in visible_stress.values()
        for delta in values if delta is not None
    )
    limit = magnitudes[max(0, int(.95 * (len(magnitudes) - 1)))] if magnitudes else 1
    heatmap = go.Figure(go.Heatmap(
        z=[visible_stress[name] for name in sorted(visible_stress)],
        x=[report['Cycle'] for report in visible_reports],
        y=sorted(visible_stress), zmid=0, zmin=-limit, zmax=limit,
        colorscale='RdBu_r', colorbar={'title': 'Δ stress'},
    ))
    heatmap.update_layout(title='Stress por duplicante', yaxis_title='Duplicante')
    latest_snapshot = (reports[-1].get('Snapshot') or {}) if reports else {}
    real_stress = {item.get('Name'): float(item.get('Stress', 0) or 0)
                   for item in latest_snapshot.get('Duplicants', [])}
    real_leader = max(real_stress.items(), key=lambda item: item[1], default=(None, None))
    pressure_text = (f'Maior stress real: {real_leader[0]} ({format_brazilian(real_leader[1])}%)'
                     if real_leader[0] else f'Maior pressão de stress (estimativa): {leader or "—"}')
    heatmap.add_annotation(
        text=pressure_text,
        xref='paper', yref='paper', x=0, y=1.12, showarrow=False, xanchor='left',
    )
    figures['stress'] = _figure_style(
        heatmap, 'stress', 'stress' not in following, last_cycle, span, reset_count,
        (zoom_ranges or {}).get('stress')
    )
    return figures, summaries, leader


def _game_status():
    try:
        result = subprocess.check_output(
            ['tasklist', '/FI', 'IMAGENAME eq OxygenNotIncluded.exe'],
            text=True, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return 'jogo aberto' if 'OxygenNotIncluded.exe' in result else 'jogo fechado'
    except (OSError, subprocess.SubprocessError):
        return 'jogo fechado'


_game_status_value = 'jogo fechado'
_game_status_checked = 0.0


def _cached_game_status():
    global _game_status_value, _game_status_checked
    now = time.monotonic()
    if now - _game_status_checked >= 30:
        _game_status_value = _game_status()
        _game_status_checked = now
    return _game_status_value


def _age(timestamp):
    now = datetime.now(timezone.utc)
    seconds = max(0, int((now - timestamp.astimezone(timezone.utc)).total_seconds()))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f'{hours} h {minutes} min'
    if minutes:
        return f'{minutes} min {seconds} s'
    return f'{seconds} s'


def _format_status(reports, warnings, game):
    if not reports:
        return f'{game} · aguardando exportação · avisos: {len(warnings)}'
    latest = reports[-1]
    age = _age(latest['_timestamp'])
    if game == 'jogo aberto' and (datetime.now(timezone.utc) - latest['_timestamp'].astimezone(timezone.utc)).total_seconds() > 900:
        game = 'exportação atrasada'
    local_time = latest['_timestamp'].astimezone().strftime('%d/%m %H:%M:%S')
    colony = f" · colônia: {latest.get('ColonyName')}" if latest.get('ColonyName') else ''
    snapshot_errors = latest.get('Snapshot', {}).get('Errors') or []
    snapshot_warning = f" · erro no snapshot do ciclo {latest['Cycle']}" if snapshot_errors else ''
    return f"{game} · ciclo {latest['Cycle']} · {local_time} · idade: {age}{colony}{snapshot_warning} · avisos: {len(warnings)}"


def create_app(export_dir=DEFAULT_EXPORT):
    app = Dash(__name__, assets_folder=str(Path(__file__).parent / 'assets'), title='Dashboard ONI')
    def serve_layout():
      initial_reports, _warnings = load_reports(export_dir)
      initial_options = material_options(initial_reports)
      return html.Main([
        html.H1('Dashboard ONI'),
        html.Section([html.H2('Estado'), html.Div(id='status'), html.Div(id='warnings')],
                     className='panel'),
        html.Section([html.H2('O que olhar agora'), html.Div(id='cards', className='cards')],
                     className='panel'),
        dcc.RadioItems(
            id='range', options=[
                {'label': 'Últimos 30', 'value': '30'}, {'label': 'Todos', 'value': 'all'}
            ], value='30', inline=True, className='range-control',
        ),
        html.Button('Voltar ao atual', id='reset-follow', n_clicks=0,
                    style={'display': 'none'}),
        dcc.Store(id='revision-store', data=None),
        dcc.Store(id='manual-graphs', data=[]),
        dcc.Store(id='zoom-ranges', data={}),
        dcc.Store(id='reset-count', data=0),
        dcc.Interval(id='revision-poll', interval=5000, n_intervals=0),
        html.Section([dcc.Graph(id='food', config={'responsive': True}, style={'height': '420px'})], className='panel'),
        html.Section([dcc.Graph(id='food-stock', config={'responsive': True}, style={'height': '420px'})], className='panel'),
        html.Section([dcc.Graph(id='oxygen', config={'responsive': True}, style={'height': '420px'}), html.Div(id='oxygen-sources')], className='panel'),
        html.Section([dcc.Graph(id='energy', config={'responsive': True}, style={'height': '420px'}), html.H2('Detalhe de fontes'), html.Div(id='energy-sources')], className='panel'),
        html.Section([html.Label('Materiais no gráfico', htmlFor='material-filter'),
                      dcc.Dropdown(id='material-filter', multi=True, searchable=True, persistence=True,
                                   persistence_type='local', value=MATERIAL_DEFAULTS, options=initial_options,
                                   search_value='', labels={
                                       'select_all': 'Selecionar todos',
                                       'deselect_all': 'Limpar sele\u00e7\u00e3o',
                                       'selected_count': '{num_selected} selecionados',
                                       'search': 'Pesquisar',
                                       'clear_search': 'Limpar pesquisa',
                                       'clear_selection': 'Limpar sele\u00e7\u00e3o',
                                       'no_options_found': 'Nenhum material encontrado',
                                   }),
                      dcc.Graph(id='materials', config={'responsive': True}, style={'height': '420px'}), html.Div(id='materials-table')], className='panel'),
        html.Section([dcc.Graph(id='stress', config={'responsive': True}, style={'height': '560px'}),
                      html.Div(id='stress-summary-table')], className='panel'),
        html.Section([
            html.H2('Eventos'), html.Ul(id='events-list'),
        ], className='panel'),
      ], className='dashboard')
    app.layout = serve_layout

    @app.callback(
        Output('revision-store', 'data'),
        Input('revision-poll', 'n_intervals'),
        State('revision-store', 'data'),
    )
    def poll_revision(_interval, previous):
        current = [list(item) for item in revision(export_dir)]
        if has_read_errors(export_dir):
            current.append(['retry-after-read-error', _interval])
        if current != previous:
            return current
        return no_update

    @app.callback(Output('material-filter', 'options'), Input('revision-store', 'data'),
                  State('material-filter', 'options'))
    def update_material_options(_revision, previous_options):
        reports, _warnings = load_reports(export_dir)
        options = material_options(reports)
        return options if options != (previous_options or []) else no_update

    @app.callback(
        Output('warnings', 'children'), Output('cards', 'children'), Output('events-list', 'children'),
        *[Output(graph_id, 'figure') for graph_id in GRAPH_IDS],
        Output('manual-graphs', 'data'), Output('zoom-ranges', 'data'), Output('reset-follow', 'style'),
        Output('reset-count', 'data'), Output('stress-summary-table', 'children'),
        Output('energy-sources', 'children'), Output('oxygen-sources', 'children'), Output('materials-table', 'children'),
        Input('revision-store', 'data'), Input('range', 'value'), Input('reset-follow', 'n_clicks'),
        *[Input(graph_id, 'relayoutData') for graph_id in GRAPH_IDS],
        Input('material-filter', 'value'),
        State('manual-graphs', 'data'), State('reset-count', 'data'), State('zoom-ranges', 'data'),
    )
    def redraw(_file_revision, span, reset_clicks, *args):
        relayout = args[:len(GRAPH_IDS)]
        selected_materials = args[-4]
        manual_graphs = set(args[-3] or [])
        reset_count = int(args[-2] or 0)
        zoom_ranges = dict(args[-1] or {})
        trigger = callback_context.triggered_id
        if trigger == 'reset-follow':
            manual_graphs.clear()
            zoom_ranges.clear()
            reset_count = int(reset_clicks or 0)
        elif trigger in GRAPH_IDS and is_user_zoom(relayout[GRAPH_IDS.index(trigger)]):
            changed = relayout[GRAPH_IDS.index(trigger)]
            if changed.get('xaxis.autorange'):
                manual_graphs.discard(trigger)
                zoom_ranges.pop(trigger, None)
            else:
                manual_graphs.add(trigger)
                selected = extract_x_range(changed)
                if selected is not None:
                    zoom_ranges[trigger] = selected

        reports, warnings = load_reports(export_dir)
        frame = calculate(reports)
        visible_frame = frame if span == 'all' else frame.tail(30)
        figures, stress_stats, pressure = build_figures(reports, span, manual_graphs, reset_count, zoom_ranges, selected_materials)
        event_list = events(reports)
        latest_cycle = reports[-1]['Cycle'] if reports else 0
        recent_events = [event for event in event_list if event['cycle'] >= latest_cycle - 9]
        event_list = event_list[:30]
        food_average = visible_frame['food_average_10'].iloc[-1] if not visible_frame.empty else None
        pressure_value = stress_stats[pressure]['positive_delta_10'] if pressure else 0
        latest = reports[-1] if reports else {}
        latest_metrics = frame.iloc[-1] if not frame.empty else None
        snapshot = latest.get('Snapshot') or {}
        stock = latest_metrics.get('food_stock_kcal') if latest_metrics is not None else None
        stored = latest_metrics.get('energy_stored_kj') if latest_metrics is not None else None
        capacity = latest_metrics.get('energy_capacity_kj') if latest_metrics is not None else None
        remaining = latest_metrics.get('food_cycles_remaining') if latest_metrics is not None else None
        stress_values = {item.get('Name'): float(item.get('Stress', 0) or 0) for item in snapshot.get('Duplicants', [])}
        highest_stress = max(stress_values.items(), key=lambda item: item[1], default=(None, None))
        cards = [
            html.Div(['Reserva de comida', html.Strong(f'{format_brazilian(stock)} kcal' if stock is not None else 'aguardando atualização do mod'), html.Span(f'{format_brazilian(remaining)} ciclos sem nova colheita (estimativa)' if remaining is not None else '—')], className='card'),
            html.Div(['Energia armazenada', html.Strong(f'{format_brazilian(stored)} kJ' if stored is not None else 'aguardando atualização do mod'), html.Span(f'{format_brazilian(stored / capacity * 100)}% da capacidade (aproximada)' if stored is not None and capacity else '—')], className='card'),
            html.Div(f'Maior stress: {highest_stress[0]} ({format_brazilian(highest_stress[1])}% real)' if highest_stress[0] else f'Maior stress (estimativa): {pressure or "—"}', className='card'),
            html.Div(f'Saldo de comida na média de 10 ciclos: {format_brazilian(food_average)} kcal' if food_average is not None else 'Saldo de comida na média de 10 ciclos: —', className='card'),
            html.Div(f'Eventos nos últimos 10 ciclos: {len(recent_events)}', className='card'),
        ]
        if stock is None:
            cards[0] = html.Div(['Reserva de comida', html.Span('aguardando atualização do mod')], className='card')
        if stored is None:
            cards[1] = html.Div(['Energia armazenada', html.Span('aguardando atualização do mod')], className='card')
        present_rows = [(name, stats) for name, stats in stress_stats.items() if stats['present_now']]
        present_rows.sort(key=lambda pair: pair[1]['positive_delta_10'], reverse=True)
        stress_table = html.Table([
            html.Thead(html.Tr([html.Th('Duplicante'), html.Th('Stress atual'), html.Th('Ciclos positivos'), html.Th('Soma positiva (10 ciclos, estimativa)')])),
            html.Tbody([html.Tr([html.Td(name), html.Td(f'{format_brazilian(stress_values[name])}%' if name in stress_values else '—'), html.Td(str(stats['consecutive_positive_cycles'])), html.Td(format_brazilian(stats['positive_delta_10']))]) for name, stats in sorted(present_rows, key=lambda pair: stress_values.get(pair[0], -1), reverse=True)]),
        ], className='stress-summary')
        sources = source_breakdown(latest) if latest else {'generators': [], 'consumers': [], 'losses': [], 'oxygen': []}
        def source_list(title, rows, unit):
            scale = 1000 if unit == 'kJ' else 1
            return html.Div([html.H3(title), html.Ul([html.Li(f'{name}: {format_brazilian(value / scale)} {unit}') for name, value in rows] or [html.Li('sem dados de fonte')])])
        material_rows = []
        _options, canonical_names, _colors = _material_data(reports)
        labels = [(label, tag) for tag, label in canonical_names.items()]
        labels.sort(key=lambda pair: (pair[0].casefold(), pair[1]))
        labels = [pair for pair in labels if selected_materials and pair[1] in selected_materials]
        if isinstance(latest_metrics.get('materials') if latest_metrics is not None else None, dict):
            material_rows = [html.Tr([html.Td(label), html.Td(format_brazilian(latest_metrics['materials'].get(tag, 0))), html.Td(format_brazilian(latest_metrics.get(f'material_tag_{tag}_change') or 0)), html.Td(format_brazilian(latest_metrics.get(f'material_tag_{tag}_average_10') or 0))]) for label, tag in labels]
        materials_table = html.Table([html.Thead(html.Tr([html.Th('Material'), html.Th('Disponível (kg)'), html.Th('Variação no ciclo'), html.Th('Média/ciclo (10 ciclos)')])), html.Tbody(material_rows)]) if material_rows else html.Div('Selecione materiais na lista' if not selected_materials else 'aguardando atualização do mod')
        event_items = [html.Li(f'Ciclo {event["cycle"]}: {event["text"]}') for event in event_list] or [html.Li('Nenhum evento nos relatórios carregados.')]
        return (
            [html.Div(message) for message in warnings], cards, event_items,
            *[figures[graph_id] for graph_id in GRAPH_IDS], sorted(manual_graphs), zoom_ranges,
            {'display': 'inline-block'} if manual_graphs else {'display': 'none'},
            reset_count, stress_table, html.Div([source_list('Geradores', sources['generators'], 'kJ'), source_list('Consumidores', sources['consumers'], 'kJ'), source_list('Perdas', sources['losses'], 'kJ')]), source_list('Produtores de oxigênio', sources['oxygen'], 'kg'), materials_table,
        )

    @app.callback(Output('status', 'children'), Input('revision-poll', 'n_intervals'))
    def refresh_status(_interval):
        reports, warnings = load_reports(export_dir)
        return _format_status(reports, warnings, _cached_game_status())

    return app
