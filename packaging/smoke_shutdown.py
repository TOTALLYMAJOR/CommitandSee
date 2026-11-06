"""Native executable shutdown check with a stalled disposable Git process tree."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This probe requires native Windows.')
    root = Path(tempfile.mkdtemp(prefix='CommitandSee-shutdown-'))
    shim = root / 'shim'
    shim.mkdir()
    compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319' / 'csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/out:' + str(shim / 'git.exe'),
                    str(Path(__file__).parent / 'fixtures' / 'git_shutdown_shim.cs')], check=True)
    settings, repo = root / 'settings', root / 'fixture-repository'
    settings.mkdir()
    repo.mkdir()
    config = settings / 'config.json'
    config.write_text(json.dumps({'repositories': [{'path': str(repo)}]}))
    env = dict(os.environ, PATH=str(shim) + os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32'),
               COMMITANDSEE_SHUTDOWN_FIXTURE=str(root))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    allocated = kernel.GetConsoleCP() == 0
    if allocated and not kernel.AllocConsole():
        raise ctypes.WinError(ctypes.get_last_error())
    if allocated:
        kernel.GetConsoleWindow.restype = wintypes.HWND
        user = ctypes.WinDLL('user32')
        user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user.ShowWindow(kernel.GetConsoleWindow(), 0)
    handles = []
    process = None
    try:
        log = root / 'launcher.log'
        with log.open('wb') as stream:
            process = subprocess.Popen([str(args.executable), '--no-browser', '--config', str(config),
                                        '--state', str(settings / 'observations.json')], env=env, cwd=root,
                                       stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        deadline = time.monotonic() + 15
        while not (root / 'child.pid').exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(log.read_text(errors='replace'))
            time.sleep(.1)
        pids = [int((root / name).read_text()) for name in ('git.pid', 'child.pid')]
        for pid in pids:
            handle = kernel.OpenProcess(0x00100000 | 0x0001, False, pid)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            assert kernel.WaitForSingleObject(handle, 0) == 258, 'Fixture ended before shutdown'
        began = time.monotonic()
        process.send_signal(signal.CTRL_BREAK_EVENT)
        assert process.wait(timeout=10) == 0, log.read_text(errors='replace')
        for handle in handles:
            assert kernel.WaitForSingleObject(handle, 5000) == 0, 'Git descendant survived launcher exit'
        result = {'passed': True, 'executable': str(args.executable), 'fixture_root': str(root),
                  'launcher_pid': process.pid, 'git_pid': pids[0], 'descendant_pid': pids[1],
                  'shutdown_seconds': round(time.monotonic() - began, 3),
                  'checked': 'Ctrl+Break exits launcher and closes stalled Git and its child before 30-second timeout'}
        (root / 'shutdown-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        for handle in handles:
            if kernel.WaitForSingleObject(handle, 0) == 258:
                kernel.TerminateProcess(handle, 1)
                kernel.WaitForSingleObject(handle, 5000)
            kernel.CloseHandle(handle)
        if allocated:
            kernel.FreeConsole()


if __name__ == '__main__':
    main()
