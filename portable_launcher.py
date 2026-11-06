"""Open the local CommitandSee dashboard from an extracted portable bundle."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

import git_dashboard as app
from repository_registry import validate_state_destination


def user_data_dir(*, platform=None, environ=None, home=None):
    platform = sys.platform if platform is None else platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == "win32":
        base = Path(environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    elif platform == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return base / "CommitandSee"


def validate_locations(config_path, state_path, bundle_root):
    validate_state_destination(config_path, state_path)
    if bundle_root is not None:
        root = bundle_root.resolve()
        if any(path.resolve().is_relative_to(root) for path in (config_path, state_path)):
            raise ValueError("Keep configuration and observation state outside the extracted application folder.")


def prepare_config(path):
    """Create a first-run registry without replacing an existing owner's file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({**app.DEFAULTS, "title": "CommitandSee", "repositories": []}, stream, indent=2)
            stream.write("\n")
    except FileExistsError:
        pass


def find_git():
    discovered = shutil.which("git")
    if discovered:
        return discovered
    if sys.platform == "win32":
        roots = [Path(os.environ[key]) for key in ("ProgramFiles", "ProgramFiles(x86)") if os.environ.get(key)]
        if os.environ.get("LOCALAPPDATA"):
            roots.append(Path(os.environ["LOCALAPPDATA"]) / "Programs")
        for root in roots:
            candidate = root / "Git" / "cmd" / "git.exe"
            if candidate.is_file():
                return str(candidate)
    return None


def prepare_external_programs():
    # PyInstaller's Windows DLL search directory is inherited by subprocesses.
    # Git and the default browser must load their own system libraries.
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        setter = ctypes.WinDLL("kernel32", use_last_error=True).SetDllDirectoryW
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_int
        if not setter(None):
            raise ctypes.WinError(ctypes.get_last_error())


def ensure_git():
    executable = find_git()
    if not executable:
        raise ValueError("Git was not found. Install Git for Windows from https://git-scm.com/download/win "
                         "and reopen CommitandSee. Python is bundled; Git is a separate prerequisite.")
    directory = str(Path(executable).resolve().parent)
    os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")
    version, _ = app._git_capabilities()
    return version


def wait_until_ready(url, timeout=10):
    # Do not send loopback readiness checks through an inherited network proxy.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with opener.open(url + "/api/snapshot", timeout=min(1, max(0.05, deadline - time.monotonic()))) as response:
                if response.status == 200:
                    response.read(1)
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.05)
    raise TimeoutError("The local dashboard did not become ready. Close this window and try again.")


def serve(config, config_path, state_path, *, port=0, open_browser=True, stop_event=None):
    state = app.LiveState(app.DashboardCollector(config, state_path), config_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), app.make_handler(state))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                              name="portable-http", daemon=True)
    started = worker_started = False
    try:
        thread.start()
        started = True
        url = f"http://127.0.0.1:{server.server_address[1]}"
        wait_until_ready(url)
        state.worker.start()
        worker_started = True
        print(f"Dashboard URL: {url}", flush=True)
        print("Keep this window open. Press Ctrl+C to stop CommitandSee.", flush=True)
        if open_browser:
            try:
                opened = webbrowser.open(url, new=2)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print("The browser did not open automatically. Open the dashboard URL above.", flush=True)
        while stop_event is None or not stop_event.is_set():
            thread.join(timeout=0.2)
            if not thread.is_alive():
                raise RuntimeError("The local dashboard server stopped unexpectedly.")
    except KeyboardInterrupt:
        print("\nStopping CommitandSee...", flush=True)
    finally:
        state.stop.set()
        state.wake.set()
        if started:
            server.shutdown()
        server.server_close()
        if started:
            thread.join(timeout=2)
        if worker_started:
            state.worker.join(timeout=2)
        # In the Windows bundle, process exit closes the runtime's kill-on-close
        # Job Objects, including any Git command still running after this wait.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Saved repository configuration outside the app folder")
    parser.add_argument("--state", help="Observation state outside the app folder")
    parser.add_argument("--port", type=int, default=0, help="Loopback port; 0 selects an available port (default)")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    args = parser.parse_args(argv)
    try:
        if not 0 <= args.port <= 65535:
            raise ValueError("port must be between 0 and 65535")
        prepare_external_programs()
        version = ensure_git()
        data = user_data_dir()
        config_path = Path(args.config).expanduser().resolve() if args.config else (data / "config.json").resolve()
        state_path = Path(args.state).expanduser().resolve() if args.state else (data / "observations.json").resolve()
        bundle_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else None
        validate_locations(config_path, state_path, bundle_root)
        prepare_config(config_path)
        config = app.read_config(argparse.Namespace(command="serve", config=str(config_path), repo=[], ref=None))
        print(f"CommitandSee | Git {version}", flush=True)
        print(f"Repositories: {config_path}\nObservation state: {state_path}", flush=True)
        serve(config, config_path, state_path, port=args.port, open_browser=not args.no_browser)
        return 0
    except (OSError, ValueError, TypeError, RuntimeError, app.GitError) as exc:
        print(f"CommitandSee could not start: {exc}", file=sys.stderr, flush=True)
        return 2


def entrypoint():
    if sys.platform == "win32":
        def interrupt(_signum, _frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK, interrupt)
    result = main()
    if result and getattr(sys, "frozen", False) and sys.stdin is not None and sys.stdin.isatty():
        try:
            input("Press Enter to close this window.")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


if __name__ == "__main__":
    raise SystemExit(entrypoint())
