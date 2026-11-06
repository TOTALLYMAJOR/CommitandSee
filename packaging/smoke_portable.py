"""Exercise an extracted native Windows ZIP using disposable local repositories."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener
import zipfile


def hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*') if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--git', type=Path, required=True)
    parser.add_argument('--work-root', type=Path)
    parser.add_argument('--browser-probe', action='store_true', help='Also request the real default browser and keep a temporary empty page available')
    parser.add_argument('--browser-wait-seconds', type=int, default=120)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Use native Windows Python for this executable smoke check.')
    root = args.work_root or Path(tempfile.mkdtemp(prefix='CommitandSee-smoke-'))
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.archive) as archive:
        archive.extractall(root / 'extracted')
    bundle = root / 'extracted' / 'CommitandSee'
    executable = bundle / 'CommitandSee.exe'
    before_bundle = hashes(bundle)
    settings = root / 'settings'
    settings.mkdir()
    config, observations = settings / 'config.json', settings / 'observations.json'
    repo = root / 'fixture-repository'
    env = dict(os.environ, PATH=str(args.git.parent) + os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32'),
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
    def git(*args_):
        subprocess.run([str(args.git), '-c', 'core.hooksPath=/dev/null', *map(str, args_)],
                       check=True, env=env, capture_output=True)
    git('init', '--template=', '-q', repo)
    (repo / 'sample.txt').write_text('Portable fixture\n', encoding='utf-8')
    git('-C', repo, 'add', 'sample.txt')
    git('-C', repo, '-c', 'user.name=Portable fixture', '-c', 'user.email=portable@example.invalid',
        'commit', '--no-gpg-sign', '-qm', 'Portable smoke fixture')
    before_repo = hashes(repo)
    opener = build_opener(ProxyHandler({}))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    allocated_console = kernel.GetConsoleCP() == 0
    if allocated_console and not kernel.AllocConsole():
        raise ctypes.WinError(ctypes.get_last_error())
    if allocated_console:
        ctypes.WinDLL('user32').ShowWindow(kernel.GetConsoleWindow(), 0)
    process = None
    logs = []

    def request(url, path='/api/snapshot', body=None):
        data = None if body is None else json.dumps(body).encode()
        request_ = Request(url + path, data=data, headers={'Origin': url, 'Content-Type': 'application/json'})
        with opener.open(request_, timeout=5) as response:
            payload = response.read()
            return response.status, json.loads(payload) if path != '/' else payload

    def start(number, open_browser=False):
        nonlocal process
        log = root / f'launch-{number}.log'
        errors = root / f'launch-{number}.errors.log'
        logs.append(str(log))
        with log.open('wb') as stdout, errors.open('wb') as stderr:
            process = subprocess.Popen([str(executable), *([] if open_browser else ['--no-browser']), '--config', str(config),
                                        '--state', str(observations)], cwd=root, env=env,
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            content = log.read_text(encoding='utf-8', errors='replace')
            match = re.search(r'Dashboard URL: (http://127\.0\.0\.1:\d+)', content)
            if match:
                return match[1]
            if process.poll() is not None:
                raise RuntimeError(f'Launcher exited {process.returncode}: {errors.read_text(errors="replace")}')
            time.sleep(.1)
        raise TimeoutError('Executable did not print its ready URL.')

    def stop():
        nonlocal process
        process.send_signal(signal.CTRL_BREAK_EVENT)
        code = process.wait(timeout=10)
        if code != 0:
            raise RuntimeError(f'Graceful console shutdown returned {code}')
        process = None

    def observed(url, count):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            snapshot = request(url)[1]
            rows = snapshot['repositories']
            if len(rows) == count and all(row['status'] in ('ok', 'partial') for row in rows):
                return snapshot
            time.sleep(.1)
        raise AssertionError(f'Expected {count} observed sources; got {rows}')

    try:
        first = start(1)
        empty = observed(first, 0)
        assert empty['repository_management'] is True
        html = request(first, '/')[1]
        assert b'Add repository' in html and b'SNAPSHOT_DATA' not in html
        status, added = request(first, '/api/repositories', {'path': str(repo), 'name': 'Portable fixture'})
        assert status == 201
        path = added['repository']['path']
        snapshot = observed(first, 1)
        assert snapshot['repositories'][0]['history']['commits'] == 1
        assert snapshot['repositories'][0]['history']['timezone'] == 'America/Chicago'
        stop()
        second = start(2)
        observed(second, 1)
        status, removed = request(second, '/api/repositories/remove', {'path': path})
        assert status == 200 and removed['removed']['path'] == path
        observed(second, 0)
        stop()
        third = start(3)
        observed(third, 0)
        stop()
        assert hashes(repo) == before_repo, 'Observed repository files changed'
        assert hashes(bundle) == before_bundle, 'Extracted application files changed'
        assert json.loads(config.read_text())['repositories'] == []
        assert Path(str(config) + '.registry.sqlite3').is_file()
        if args.browser_probe:
            browser_url = start(4, open_browser=True)
            observed(browser_url, 0)
            stop_file = root / 'stop-browser-probe'
            print(json.dumps({'browser_probe_url': browser_url, 'pid': process.pid,
                              'stop_file': str(stop_file), 'wait_seconds': args.browser_wait_seconds}), flush=True)
            deadline = time.monotonic() + args.browser_wait_seconds
            while not stop_file.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Browser probe exited before cleanup')
                time.sleep(.2)
            stop()
        result = {'passed': True, 'archive': str(args.archive),
                  'archive_sha256': hashlib.sha256(args.archive.read_bytes()).hexdigest(),
                  'work_root': str(root), 'logs': logs, 'repository_unchanged': True,
                  'bundle_unchanged': True, 'python_absent_from_child_path': True,
                  'checks': ['empty onboarding', 'HTTP HTML and JSON', 'bundled timezone data',
                             'add local repository', 'one observed commit', 'Ctrl+Break graceful shutdown',
                             'restart retains added repository', 'remove repository', 'restart retains removal'],
                  'not_checked': ['actual default-browser window', 'clean Windows installation', 'SmartScreen reputation']}
        if args.browser_probe:
            result['checks'].append('real default-browser launch requested after readiness')
        (root / 'smoke-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        if allocated_console:
            kernel.FreeConsole()


if __name__ == '__main__':
    main()
