#!/usr/bin/env python3
"""A local Python + Git activity dashboard. No third-party Python packages."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from git_metrics import collect_repository

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "title": "Git activity dashboard", "timezone": "America/Chicago",
    "days": 180, "refresh_seconds": 30, "history_refresh_seconds": 300,
    "max_commits": 20000, "stale_days": 14, "exclude_globs": [],
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_config(args):
    config = dict(DEFAULTS)
    repos = []
    base = Path.cwd()
    if args.config:
        source = Path(args.config).expanduser().resolve()
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Config must be a JSON object.")
        config.update({k: raw[k] for k in DEFAULTS if k in raw})
        repos = raw.get("repositories", [])
        if not isinstance(repos, list):
            raise ValueError("repositories must be an array.")
        base = source.parent
    for arg, field in (("days", "days"), ("interval", "refresh_seconds"),
                       ("timezone", "timezone"), ("max_commits", "max_commits"),
                       ("stale_days", "stale_days")):
        value = getattr(args, arg, None)
        if value is not None:
            config[field] = value
    for field, minimum, maximum in (("days", 1, 3660), ("refresh_seconds", 5, 86400),
                                    ("history_refresh_seconds", 5, 86400),
                                    ("max_commits", 1, 100000), ("stale_days", 1, 36525)):
        value = config[field]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{field} must be an integer from {minimum} to {maximum}.")
    if not isinstance(config["exclude_globs"], list) or not all(isinstance(v, str) for v in config["exclude_globs"]):
        raise ValueError("exclude_globs must be a list of strings.")
    if not isinstance(config["title"], str) or not isinstance(config["timezone"], str):
        raise ValueError("title and timezone must be strings.")
    configured = []
    for entry in repos:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"].strip():
            raise ValueError("Each repository needs a nonempty path string.")
        item = dict(entry)
        path = Path(item["path"]).expanduser()
        item["path"] = str((base / path if not path.is_absolute() else path).resolve())
        configured.append(item)
    for value in args.repo or []:
        configured.append({"path": str(Path(value).expanduser().resolve()), "product": "My repositories"})
    if not configured:
        raise ValueError("Add --repo /path/to/repository (repeat for more repos), or use --config config.json.")
    for item in configured:
        item.setdefault("name", Path(item["path"]).name)
        item.setdefault("product", "My repositories")
        item.setdefault("ref", args.ref or "HEAD")
        if args.ref:
            item["ref"] = args.ref
        if not all(isinstance(item.get(k), str) and item[k] for k in ("name", "product", "ref")):
            raise ValueError("Repository name, product, and ref must be nonempty strings.")
        excludes = item.get("exclude_globs", config["exclude_globs"])
        if not isinstance(excludes, list) or not all(isinstance(x, str) for x in excludes):
            raise ValueError("Repository exclude_globs must be a list of strings.")
        item["exclude_globs"] = excludes
    config["repositories"] = configured
    return config


def atomic_json(path, data):
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".git-dashboard-", suffix=".tmp",
                                         encoding="utf-8", delete=False) as stream:
            temporary = stream.name
            json.dump(data, stream, ensure_ascii=True, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class ObservationTracker:
    """Remember observed dirty age without claiming unobserved historical activity."""
    def __init__(self, path=None):
        self.path = Path(path).expanduser() if path else None
        self.states = {}
        self.error = None
        if self.path and self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if data.get("version") != 1 or not isinstance(data.get("worktrees"), dict):
                    raise ValueError("Unsupported state file")
                self.states = data["worktrees"]
            except (OSError, ValueError, TypeError) as exc:
                self.error = f"Observation history unavailable: {exc}"

    def annotate(self, repository, interval):
        now = repository.get("collected_at") or utc_now()
        for tree in repository.get("worktrees", []):
            key = hashlib.sha256((str(repository.get("id")) + "\0" + tree.get("path", "")).encode()).hexdigest()
            prior = self.states.get(key, {})
            if not isinstance(prior, dict):
                prior = {}
            gap = None
            try:
                elapsed = (datetime.fromisoformat(now.replace("Z", "+00:00")) -
                           datetime.fromisoformat(prior["last_seen"].replace("Z", "+00:00"))).total_seconds()
                if elapsed > max(interval * 3, 120):
                    gap = round(elapsed)
            except (KeyError, TypeError, ValueError):
                pass
            tree["observation_gap_seconds"] = gap
            if tree.get("dirty") is None or tree.get("status") == "error":
                tree["first_seen_dirty_at"] = prior.get("first_seen_dirty_at")
                tree["last_changed_at"] = prior.get("last_changed_at")
                continue
            is_dirty = tree.get("dirty") is True
            fingerprint = tree.get("fingerprint")
            changed = fingerprint is not None and fingerprint != prior.get("fingerprint")
            first = (prior.get("first_seen_dirty_at") or now) if is_dirty else None
            last_changed = now if changed or not prior else prior.get("last_changed_at", now)
            tree["first_seen_dirty_at"] = first
            tree["last_changed_at"] = last_changed
            self.states[key] = {"fingerprint": fingerprint, "last_seen": now,
                                "first_seen_dirty_at": first, "last_changed_at": last_changed}

    def save(self):
        if not self.path:
            return
        try:
            atomic_json(self.path, {"version": 1, "worktrees": self.states})
        except OSError as exc:
            self.error = f"Could not save observation history: {exc}"


class DashboardCollector:
    def __init__(self, config, state_path=None):
        self.config = config
        self.tracker = ObservationTracker(state_path)
        self.history_cache = {}

    def collect(self, *, live=False):
        began = time.monotonic()
        result = {"schema_version": 1, "title": self.config["title"], "generated_at": utc_now(),
                  "timezone": self.config["timezone"], "refresh_seconds": self.config["refresh_seconds"],
                  "live": live, "demo": False, "repositories": [], "errors": [],
                  "collection_running": False, "source": "Local Git commands"}
        seen = {}
        for item in self.config["repositories"]:
            options = {"name": item["name"], "ref": item["ref"], "days": self.config["days"],
                       "timezone": self.config["timezone"], "max_commits": self.config["max_commits"],
                       "stale_days": self.config["stale_days"], "exclude_globs": item["exclude_globs"]}
            try:
                repo = collect_repository(item["path"], include_history=False, **options)
                identity = repo.get("id") or item["path"]
                if repo.get("common_dir") and identity in seen:
                    kept = seen[identity]
                    if item["product"] not in kept["products"]:
                        kept["products"].append(item["product"])
                    result["errors"].append(f"{item['name']}: same Git common directory as {kept['name']}; counted once. First configured ref retained.")
                    continue
                key = (identity, repo.get("head"), item["ref"], self.config["days"], self.config["timezone"],
                       tuple(item["exclude_globs"]), datetime.now(timezone.utc).date().isoformat())
                cached = self.history_cache.get(key)
                if repo.get("common_dir"):
                    if cached and time.monotonic() - cached[0] < self.config["history_refresh_seconds"]:
                        repo["history"] = copy.deepcopy(cached[1])
                        repo["history"]["cached"] = True
                        limited = repo["history"].get("truncated") or repo["history"].get("shallow")
                        repo.setdefault("source_status", {})["history"] = "partial" if limited else "ok"
                        if limited and repo.get("status") == "ok":
                            repo["status"] = "partial"
                    else:
                        measured = collect_repository(item["path"], include_history=True, **options)
                        repo = measured
                        history = repo.get("history")
                        if history is not None:
                            history["collected_at"] = repo.get("collected_at", utc_now())
                            history["cached"] = False
                            actual_key = (identity, repo.get("head"), item["ref"], self.config["days"], self.config["timezone"],
                                          tuple(item["exclude_globs"]), datetime.now(timezone.utc).date().isoformat())
                            self.history_cache = {k: v for k, v in self.history_cache.items() if k[0] != identity}
                            self.history_cache[actual_key] = (time.monotonic(), copy.deepcopy(history))
                repo["product"] = item["product"]
                repo["products"] = [item["product"]]
                repo["stale_days"] = self.config["stale_days"]
                repo["exclude_globs"] = item["exclude_globs"]
                self.tracker.annotate(repo, self.config["refresh_seconds"])
                seen[identity] = repo
                result["repositories"].append(repo)
            except Exception as exc:
                result["repositories"].append({"id": item["path"], "name": item["name"], "path": item["path"],
                    "product": item["product"], "products": [item["product"]], "ref": item["ref"], "head": None,
                    "status": "error", "errors": [f"Collection failed: {type(exc).__name__}: {exc}"],
                    "warnings": [], "history": None, "worktrees": [], "branches": [], "remote_branches": [], "stashes": []})
        self.tracker.save()
        if self.tracker.error:
            result["errors"].append(self.tracker.error)
        zones = {r["history"].get("timezone", self.config["timezone"]) for r in result["repositories"] if r.get("history")}
        result["requested_timezone"] = self.config["timezone"]
        if len(zones) == 1:
            result["timezone"] = zones.pop()
        elif len(zones) > 1:
            result["timezone"] = "Mixed; see repository details"
        result["generated_at"] = utc_now()
        result["duration_seconds"] = round(time.monotonic() - began, 3)
        return result


def render_html(snapshot):
    template = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    marker = "__GIT_DASHBOARD_DATA__"
    if template.count(marker) != 1:
        raise ValueError("Dashboard template must contain exactly one data marker.")
    data = json.dumps(snapshot, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return template.replace(marker, data)


def export_html(path, snapshot):
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(snapshot), encoding="utf-8")


class LiveState:
    def __init__(self, collector):
        self.collector = collector
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.snapshot = collector.collect(live=True)
        self.worker = threading.Thread(target=self.loop, name="git-observer", daemon=True)

    def read(self):
        with self.lock:
            return copy.deepcopy(self.snapshot)

    def loop(self):
        while not self.stop.wait(self.collector.config["refresh_seconds"]):
            with self.lock:
                self.snapshot["collection_running"] = True
            try:
                data = self.collector.collect(live=True)
                with self.lock:
                    self.snapshot = data
            except Exception as exc:
                with self.lock:
                    self.snapshot["collection_running"] = False
                    self.snapshot["errors"] = [f"Refresh failed; retaining previous snapshot: {type(exc).__name__}: {exc}"]


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GitDashboard/1"

        def do_GET(self):
            host = self.headers.get("Host", "").split(":", 1)[0].lower()
            if host not in {"127.0.0.1", "localhost"}:
                self.send_error(403, "Local dashboard only")
                return
            route = urlsplit(self.path).path
            if route in {"/", "/index.html"}:
                data, content_type = render_html(state.read()).encode("utf-8"), "text/html; charset=utf-8"
            elif route == "/api/snapshot":
                data, content_type = json.dumps(state.read(), ensure_ascii=True, allow_nan=False).encode("utf-8"), "application/json"
            elif route == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", action="append", help="Local repository path; repeat for multiple repositories")
    common.add_argument("--config", help="JSON configuration file")
    common.add_argument("--ref", help="History/integration comparison ref (default HEAD, or per-repo config)")
    common.add_argument("--days", type=int, help="History window (default 180)")
    common.add_argument("--timezone", help="IANA chart timezone (default America/Chicago)")
    common.add_argument("--max-commits", type=int, help="Maximum history commits (default 20000; truncation is visible)")
    common.add_argument("--stale-days", type=int, help="Old unmerged branch-tip threshold (default 14)")
    common.add_argument("--state", help="Optional observation-history JSON path (never a repository path)")
    scan = sub.add_parser("scan", parents=[common], help="Collect Git data and export a self-contained HTML report")
    scan.add_argument("--output", default="git-activity.html")
    scan.add_argument("--json", dest="json_output", help="Also write the machine-readable snapshot")
    serve = sub.add_parser("serve", parents=[common], help="Run the auto-refreshing dashboard on localhost")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--interval", type=int, help="Local refresh interval in seconds (minimum 5, default 30)")
    demo = sub.add_parser("demo", help="Export a clearly labeled example using synthetic data")
    demo.add_argument("--output", default="demo.html")
    args = parser.parse_args(argv)
    if args.command == "demo":
        snapshot = json.loads((ROOT / "demo.json").read_text(encoding="utf-8"))
        snapshot["live"] = False
        snapshot["demo"] = True
        export_html(args.output, snapshot)
        print(f"Synthetic demo written to {Path(args.output).resolve()}")
        return 0
    try:
        config = read_config(args)
        if args.command == "serve" and not 1 <= args.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        state_path = args.state
        if args.command == "serve" and not state_path:
            state_path = Path.home() / ".git-activity-dashboard" / "observations.json"
        collector = DashboardCollector(config, state_path)
        if args.command == "scan":
            snapshot = collector.collect()
            export_html(args.output, snapshot)
            if args.json_output:
                atomic_json(args.json_output, snapshot)
            ok = sum(r["status"] != "error" for r in snapshot["repositories"])
            print(f"Report: {Path(args.output).resolve()} ({ok}/{len(snapshot['repositories'])} repositories observed)")
            return 0 if ok else 2
        print("Collecting local Git data…", flush=True)
        state = LiveState(collector)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
        state.worker.start()
        print(f"Open http://127.0.0.1:{args.port} — refresh every {config['refresh_seconds']} seconds. Ctrl+C stops.", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")
        finally:
            state.stop.set()
            server.server_close()
            state.worker.join(timeout=2)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
