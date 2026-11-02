"""Command line entry point."""
import argparse
import ctypes
import logging
import logging.handlers
import os
from pathlib import Path
import sys
import threading
import time
import urllib.request
import webbrowser

from .app import DEFAULT_EXPORT, create_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--export-dir', type=Path, default=DEFAULT_EXPORT)
    parser.add_argument('--port', type=int, default=8050)
    parser.add_argument('--open', action='store_true')
    arguments = parser.parse_args()

    log_directory = PROJECT_ROOT / 'logs'
    log_directory.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_directory / 'dashboard.log', maxBytes=1_000_000, backupCount=2,
        encoding='utf-8',
    )
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    if sys.stdout is None:
        sys.stdout = open('NUL', 'w', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = open('NUL', 'w', encoding='utf-8')

    instance_exists = False
    if sys.platform == 'win32':
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.CreateMutexW(None, False, 'Local\\ONIDashboardMVP')
        if ctypes.get_last_error() == 183:
            logging.warning('Instância já em execução')
            instance_exists = True

    address = f'http://127.0.0.1:{arguments.port}/'
    if instance_exists:
        if arguments.open and _wait_for_server(address):
            _open_dashboard(address)
        return 0

    app = create_app(arguments.export_dir)
    if arguments.open:
        server = _create_server(app, arguments.port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        if _wait_for_server(address):
            _open_dashboard(address)
        while True:
            time.sleep(3600)
    else:
        app.run(host='127.0.0.1', port=arguments.port, debug=False)
    return 0


def _create_server(app, port):
    from werkzeug.serving import make_server
    return make_server('127.0.0.1', port, app.server, threaded=True)


def _wait_for_server(address, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(address, timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _open_dashboard(address):
    import shutil
    edge = shutil.which('msedge')
    if not edge and sys.platform == 'win32':
        for program_dir in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles')):
            if program_dir:
                candidate = Path(program_dir) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'
                if candidate.is_file():
                    edge = str(candidate)
                    break
    if edge:
        import subprocess
        subprocess.Popen([edge, f'--app={address}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(address)


if __name__ == '__main__':
    raise SystemExit(main())
