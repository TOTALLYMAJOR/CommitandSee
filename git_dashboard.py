#!/usr/bin/env python3
"""A local Python + Git activity dashboard. No third-party Python packages."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import copy
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from git_metrics import collect_repository, GitError, _Git, _git_capabilities
from public_repositories import public_url, public_metadata, collect_public
from repository_registry import RepositoryRegistry, validate_state_destination
from github_auth import API_ROOT, GitHubAuth, GitHubAuthError, _request_json, github_app_config
from authenticated_repositories import collect_authenticated

ROOT = Path(__file__).resolve().parent
DEFAULTS = {
    "title": "Git activity dashboard", "timezone": "America/Chicago",
    "days": 180, "refresh_seconds": 30, "history_refresh_seconds": 300,
    "max_commits": 20000, "stale_days": 14, "exclude_globs": [],
}
GITHUB_SOURCE_FIELDS = {"source_kind", "url", "path", "name", "product", "ref", "exclude_globs",
                        "github_repository_id", "github_account_id", "installation_id", "private"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def history_day(zone_name, collected_at=None):
    """Match the collector's calendar window, including its UTC fallback."""
    try:
        zone = timezone.utc if zone_name == "UTC" else ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        zone = timezone.utc
    moment = datetime.fromisoformat(collected_at.replace("Z", "+00:00")) if collected_at else datetime.now(timezone.utc)
    return moment.astimezone(zone).date().isoformat()


def repository_path(item, base):
    if item.get("url"):
        return public_url(item["url"])
    path = Path(item["path"]).expanduser()
    return str((base / path if not path.is_absolute() else path).resolve())


def merge_repositories(base_entries, overrides, base):
    """Apply UI additions/removal tombstones without changing the base JSON."""
    merged, seen = [], set()
    for entry in base_entries:
        key = repository_path(entry, base)
        seen.add(key)
        value = overrides.get(key, entry)
        if value is not None:
            merged.append(copy.deepcopy(value))
    merged.extend(copy.deepcopy(entry) for key, entry in overrides.items() if key not in seen and entry is not None)
    return merged


def normalize_repositories(repos, base, config, ref=None):
    configured = []
    for entry in repos:
        if isinstance(entry, dict) and entry.get("source_kind") == "github":
            if set(entry) - GITHUB_SOURCE_FIELDS:
                raise ValueError("GitHub repository entries may contain only repository metadata, never credentials.")
            if any(type(entry.get(key)) is not int or entry[key] <= 0
                   for key in ("github_repository_id", "github_account_id", "installation_id")):
                raise ValueError("GitHub sources need positive repository, account, and installation IDs.")
            if type(entry.get("private")) is not bool:
                raise ValueError("GitHub repository visibility must be a boolean.")
            item = dict(entry)
            item["url"] = public_url(item.get("url"))
            item.update(path=item["url"], source_kind="github", ref="HEAD")
        elif isinstance(entry, dict) and "url" in entry:
            item = dict(entry)
            item["url"] = public_url(item["url"])
            item.update(path=item["url"], source_kind="public", ref="HEAD")
        else:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"].strip():
                raise ValueError("Each repository needs a nonempty path string.")
            item = dict(entry)
            item["path"] = repository_path(item, base)
        item.setdefault("name", Path(item["path"]).name)
        item.setdefault("product", "My repositories")
        item.setdefault("ref", ref or "HEAD")
        if ref:
            item["ref"] = ref
        if not all(isinstance(item.get(k), str) and item[k] for k in ("name", "product", "ref")):
            raise ValueError("Repository name, product, and ref must be nonempty strings.")
        excludes = item.get("exclude_globs", config["exclude_globs"])
        if not isinstance(excludes, list) or not all(isinstance(x, str) for x in excludes):
            raise ValueError("Repository exclude_globs must be a list of strings.")
        item["exclude_globs"] = excludes
        configured.append(item)
    return configured


def read_config(args):
    config = dict(DEFAULTS)
    repos = []
    base = Path.cwd()
    raw = {}
    if args.config:
        source = Path(args.config).expanduser().resolve()
        config["_config_digest"] = source.read_bytes()
        raw = json.loads(config["_config_digest"])
        if not isinstance(raw, dict):
            raise ValueError("Config must be a JSON object.")
        config.update({k: raw[k] for k in DEFAULTS if k in raw})
        repos = raw.get("repositories", [])
        if not isinstance(repos, list):
            raise ValueError("repositories must be an array.")
        base = source.parent
        config["_base_repositories"] = copy.deepcopy(repos)
        config["_registry_overrides"] = RepositoryRegistry(source).read()
    config["github_app"] = github_app_config(raw.get("github_app"))
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
    configured = normalize_repositories(repos, base, config, args.ref)
    if args.config:
        configured = normalize_repositories(merge_repositories(
            configured, config["_registry_overrides"], base), base, config, args.ref)
    config["_ref_override"] = args.ref
    for value in args.repo or []:
        configured.append({"path": str(Path(value).expanduser().resolve()), "product": "My repositories"})
    # These sources return whenever the same command is restarted. Do not offer
    # a persistent UI removal for them, even if the config also names that path.
    config["_cli_paths"] = [str(Path(value).expanduser().resolve()) for value in args.repo or []]
    if not configured and getattr(args, "command", None) != "serve":
        raise ValueError("Add --repo /path/to/repository (repeat for more repos), or use --config config.json.")
    config["repositories"] = normalize_repositories(configured, base, config, args.ref)
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
                if (not isinstance(data, dict) or data.get("version") != 1
                        or not isinstance(data.get("worktrees"), dict)):
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


def github_unavailable(item, status):
    """Retain configured identity, but never retain a disconnected observation."""
    result = {key: copy.deepcopy(value) for key, value in item.items() if key in GITHUB_SOURCE_FIELDS}
    result.update(id=item["path"], path=item["path"], configured_paths=[item["path"]],
        source_kind="github", status="auth_required", authentication_required=True,
        github_generation=status.get("generation"), history=None, head=None, collected_at=None,
        worktrees=[], branches=[], remote_branches=[], stashes=[], warnings=[],
        errors=["Sign in to the linked GitHub account to observe this repository."],
        source_status={key: "not_requested" for key in ("history", "worktrees", "branches", "stashes")})
    return result


def github_session(status, item=None):
    user = status.get("user") or {}
    return (status.get("status") == "connected" and type(user.get("id")) is int
            and (item is None or user["id"] == item.get("github_account_id")))


class DashboardCollector:
    def __init__(self, config, state_path=None, auth=None):
        self.config = config
        self.auth = auth if auth is not None else GitHubAuth(github_app_config(config.get("github_app")))
        self.tracker = ObservationTracker(state_path)
        self.history_cache = {}
        self.public_cache = {}
        self.public_cache_root = (Path(state_path).expanduser().resolve().parent if state_path else Path.home() / ".git-activity-dashboard") / "public-repositories"
        self.github_cache_root = self.public_cache_root.with_name("github-repositories")
        self.github_cache = {}

    def collect(self, *, live=False, on_progress=None):
        began = time.monotonic()
        result = {"schema_version": 1, "title": self.config["title"], "generated_at": utc_now(),
                  "timezone": self.config["timezone"], "refresh_seconds": self.config["refresh_seconds"],
                  "live": live, "demo": False, "repositories": [], "errors": [],
                  "collection_running": False, "source": "Local Git commands"}
        seen = {}
        # Public items added through the form must not wait behind a large local scan.
        for item in sorted(list(self.config["repositories"]), key=lambda r: not bool(r.get("url"))):
            if item.get("source_kind") == "github":
                status = self.auth.status()
                if not github_session(status, item):
                    repo = github_unavailable(item, status)
                else:
                    generation, account = status["generation"], status["user"]["id"]
                    key = (account, item["github_repository_id"], generation, history_day(self.config["timezone"]))
                    cached = self.github_cache.get(key)
                    try:
                        reused = cached and time.monotonic() - cached[0] < max(60, self.config["history_refresh_seconds"])
                        if reused:
                            # Refresh an expired in-memory access token before
                            # session_guard checks validity, even without a fetch.
                            self.auth.token()
                            repo = copy.deepcopy(cached[1])
                            if repo.get("history"):
                                repo["history"]["cached"] = True
                        else:
                            repo = collect_authenticated(item, self.github_cache_root, self.config, self.auth)
                        with self.auth.session_guard(generation, account):
                            repo["github_generation"] = generation
                            if not reused and repo.get("history") is not None:
                                self.github_cache[key] = (time.monotonic(), copy.deepcopy(repo))
                    except GitHubAuthError:
                        repo = github_unavailable(item, self.auth.status())
                repo.update(product=item["product"], products=[item["product"]], configured_paths=[item["path"]])
                result["repositories"].append(repo)
                if on_progress and on_progress(result):
                    break
                continue
            if item.get("url"):
                for local in self.config["repositories"]:
                    if not local.get("url") and self.public_cache_root.resolve().is_relative_to(Path(local["path"]).resolve()):
                        raise ValueError("Public cache must be outside monitored repositories; use --state outside those paths.")
                cached = self.public_cache.get(item["url"])
                if (cached and cached[2] == history_day(self.config["timezone"])
                        and time.monotonic() - cached[0] < max(60, self.config["history_refresh_seconds"])):
                    repo = copy.deepcopy(cached[1])
                    if repo.get("history"):
                        repo["history"]["cached"] = True
                else:
                    repo = collect_public(item, self.public_cache_root, self.config)
                    self.public_cache[item["url"]] = (
                        time.monotonic(), copy.deepcopy(repo),
                        history_day(self.config["timezone"], repo.get("collected_at")))
                repo.update(product=item["product"], products=[item["product"]], configured_paths=[item["path"]])
                result["repositories"].append(repo)
                if on_progress and on_progress(result):
                    break
                continue
            options = {"name": item["name"], "ref": item["ref"], "days": self.config["days"],
                       "timezone": self.config["timezone"], "max_commits": self.config["max_commits"],
                       "stale_days": self.config["stale_days"], "exclude_globs": item["exclude_globs"]}
            try:
                repo = collect_repository(item["path"], include_history=False, **options)
                identity = repo.get("id") or item["path"]
                if repo.get("common_dir") and identity in seen:
                    kept = seen[identity]
                    kept.setdefault("configured_paths", [kept["path"]]).append(item["path"])
                    if item["product"] not in kept["products"]:
                        kept["products"].append(item["product"])
                    result["errors"].append(f"{item['name']}: same Git common directory as {kept['name']}; counted once. First configured ref retained.")
                    continue
                key = (identity, repo.get("head"), item["ref"], self.config["days"], self.config["timezone"],
                       tuple(item["exclude_globs"]), history_day(self.config["timezone"]))
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
                                          tuple(item["exclude_globs"]), history_day(self.config["timezone"], repo.get("collected_at")))
                            self.history_cache = {k: v for k, v in self.history_cache.items() if k[0] != identity}
                            self.history_cache[actual_key] = (time.monotonic(), copy.deepcopy(history))
                repo["configured_paths"] = [item["path"]]
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
            if on_progress and on_progress(result):
                break
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


class RepositoryError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def repository_locations(path):
    """Identify the entire Git worktree family before writing monitor config."""
    _, lazy = _git_capabilities()
    git = _Git(Path(path).resolve(), lazy)
    root = Path(os.fsdecode(git.run("rev-parse", "--show-toplevel")).strip()).resolve()
    common = Path(os.fsdecode(git.run("rev-parse", "--path-format=absolute", "--git-common-dir")).strip()).resolve()
    registered = {root}
    for field in git.run("worktree", "list", "--porcelain", "-z").split(b"\0"):
        if field.startswith(b"worktree "):
            registered.add(Path(os.fsdecode(field[9:])).resolve())
    return root, common, registered


class LiveState:
    def __init__(self, collector, config_path=None):
        self.collector = collector
        self.auth = collector.auth
        self.github_session_id = uuid.uuid4().hex
        self.config_path = Path(config_path).expanduser().resolve() if config_path else None
        self.config_digest = collector.config.get("_config_digest",
            self.config_path.read_bytes() if self.config_path and self.config_path.exists() else None)
        raw = json.loads(self.config_digest) if self.config_digest else {}
        self.base_entries = raw.get("repositories", [])
        self.registry = RepositoryRegistry(self.config_path) if self.config_path else None
        self.registry_overrides = self.registry.read() if self.registry else {}
        self.persisted_paths = {item["path"] for item in self.effective_entries(self.registry_overrides, include_cli=False)}
        if "_base_repositories" in collector.config:
            collector.config["repositories"] = self.effective_entries(self.registry_overrides)
        self.registry_revision = 0
        self.lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.snapshot = {"schema_version": 1, "title": collector.config["title"],
            "timezone": collector.config["timezone"], "refresh_seconds": collector.config["refresh_seconds"],
            "generated_at": utc_now(), "live": True, "demo": False, "errors": [],
            "collection_running": True, "repositories": []}
        self.auth.set_on_change(self.github_auth_changed)
        self.publish(self.snapshot)
        self.worker = threading.Thread(target=self.loop, name="git-observer", daemon=True)

    def publish(self, data, revision=None):
        status = self.auth.status()
        guard = (self.auth.session_guard(status["generation"], status["user"]["id"])
                 if github_session(status) else nullcontext())
        try:
            with guard:
                self._publish(data, revision, status)
        except GitHubAuthError:
            self._publish(data, revision, self.auth.status(), force_private_clear=True)

    def sanitize_github(self, snapshot, status, *, force_private_clear=False):
        observation_fields = {"id", "status", "history", "head", "collected_at", "worktrees", "branches",
            "remote_branches", "stashes", "errors", "warnings", "source_status", "products", "configured_paths",
            "removable", "github_generation", "authentication_required"}
        sanitized = []
        for row in snapshot["repositories"]:
            if row.get("source_kind") != "github":
                sanitized.append(row)
                continue
            permitted = (not force_private_clear and github_session(status, row)
                and (row.get("github_generation") == status["generation"]
                     or (row.get("status") == "pending" and row.get("history") is None)))
            if permitted:
                row = {key: value for key, value in row.items() if key in GITHUB_SOURCE_FIELDS | observation_fields}
                row["authentication_required"] = False
            else:
                unavailable = github_unavailable(row, status)
                unavailable["removable"] = row.get("removable", False)
                row = unavailable
            sanitized.append(row)
        snapshot["repositories"] = sanitized
        snapshot["github_generation"] = status.get("generation")
        snapshot["github_session_id"] = self.github_session_id
        return snapshot

    def _publish(self, data, revision, auth_status, *, force_private_clear=False):
        with self.lock:
            if revision is not None and revision != self.registry_revision:
                return
            snapshot = copy.deepcopy(data)
            active = {item["path"] for item in self.collector.config["repositories"]}
            # A scan can finish after removal. Its captured rows must never
            # restore a source that is no longer configured.
            snapshot["repositories"] = [row for row in snapshot["repositories"]
                if active.intersection(row.get("configured_paths", [row["path"]]))]
            paths = {p for r in snapshot["repositories"] for p in r.get("configured_paths", [r["path"]])}
            previous = {r["path"]: r for r in self.snapshot.get("repositories", []) if r.get("status") != "pending"}
            for item in self.collector.config["repositories"]:
                if item["path"] not in paths and item["path"] in previous:
                    snapshot["repositories"].append(copy.deepcopy(previous[item["path"]]))
                    continue
                if item["path"] not in paths:
                    snapshot["repositories"].append({**item, "id": item["path"], "status": "pending",
                        "history": None, "worktrees": [], "branches": [], "stashes": [],
                        "source_status": {k: "pending" for k in ("history", "worktrees", "branches", "stashes")}})
            for row in snapshot["repositories"]:
                represented = set(row.get("configured_paths", [row["path"]]))
                row["removable"] = bool(self.config_path and represented <= self.persisted_paths
                    and not represented.intersection(self.collector.config.get("_cli_paths", [])))
            snapshot["repository_management"] = self.config_path is not None
            self.snapshot = self.sanitize_github(snapshot, auth_status, force_private_clear=force_private_clear)

    def read(self):
        status = self.auth.status()
        guard = (self.auth.session_guard(status["generation"], status["user"]["id"])
                 if github_session(status) else nullcontext())
        try:
            with guard:
                with self.lock:
                    return self.sanitize_github(copy.deepcopy(self.snapshot), status)
        except GitHubAuthError:
            status = self.auth.status()
            with self.lock:
                return self.sanitize_github(copy.deepcopy(self.snapshot), status, force_private_clear=True)

    def github_auth_changed(self, status):
        self.collector.github_cache.clear()
        self.publish(self.read())
        self.wake.set()

    def require_github_session(self):
        if not self.config_path:
            raise RepositoryError("read_only", "Start with --config to import GitHub repositories.", 403)
        status = self.auth.status()
        if not github_session(status):
            raise RepositoryError("authentication_required", "Sign in to GitHub first.", 401)
        return status["generation"], status["user"]["id"]

    def github_status(self):
        return {**self.auth.status(), "github_session_id": self.github_session_id}

    def github_response(self, result, generation=None):
        return {**result, "github_session_id": self.github_session_id,
                "github_generation": self.auth.generation if generation is None else generation}

    def commit_pulls(self, body):
        if (not isinstance(body, dict) or set(body) != {"repository", "sha"}
                or not isinstance(body["repository"], str) or not isinstance(body["sha"], str)
                or not re.fullmatch(r"[0-9a-f]{40}", body["sha"])):
            raise RepositoryError("invalid_input", "Choose an observed GitHub commit.")
        snapshot = self.read()
        repo = next((r for r in snapshot["repositories"] if r.get("id") == body["repository"]), None)
        sha = body["sha"]
        if not repo or not any(c["sha"] == sha for c in (repo.get("history") or {}).get("events", [])):
            raise RepositoryError("not_found", "This commit is outside the current observation.", 404)
        try:
            url = public_url(repo.get("github_url") or repo.get("url"))
        except ValueError:
            raise RepositoryError("unsupported", "No GitHub repository is available for this commit.") from None
        path = f"/repos/{url.removeprefix('https://github.com/')}/commits/{sha}/pulls?per_page=100"
        # Credentials are restricted to repositories explicitly selected by this account.
        imported = next((r for r in snapshot["repositories"] if r.get("source_kind") == "github"
                         and r.get("url") == url and not r.get("authentication_required")
                         and r.get("github_generation") == snapshot.get("github_generation")), None)
        if imported:
            generation, account = imported["github_generation"], imported["github_account_id"]
            rows = self.auth.request_json(path, expected_session=(generation, account))
        else:
            rows = _request_json("GET", API_ROOT + path)
        pulls = []
        for row in rows:
            number = row.get("number") if isinstance(row, dict) else None
            if type(number) != int or number < 1 or not isinstance(row.get("title"), str):
                raise GitHubAuthError("invalid_response", "GitHub returned invalid pull request details.", 502)
            pulls.append({"number": number, "title": row["title"][:300]})
        with self.auth.session_guard(generation, account) if imported else nullcontext():
            return {"pulls": pulls, "limited": len(rows) == 100}

    def github_action(self, action, body):
        if not isinstance(body, dict) or body:
            raise RepositoryError("invalid_input", "Send an empty JSON object for this action.")
        if not self.config_path:
            raise RepositoryError("read_only", "Start with --config to manage GitHub repositories.", 403)
        result = getattr(self.auth, action)()
        return self.github_response(result, result["generation"])

    def github_repositories(self, body):
        if not isinstance(body, dict) or body:
            raise RepositoryError("invalid_input", "Send an empty JSON object to discover repositories.")
        generation, account = self.require_github_session()
        result = self.auth.repositories()
        with self.auth.session_guard(generation, account):
            return self.github_response(copy.deepcopy(result), generation)

    def import_github_repositories(self, body):
        if (not isinstance(body, dict) or set(body) != {"repository_ids"}
                or not isinstance(body["repository_ids"], list) or not 1 <= len(body["repository_ids"]) <= 50
                or any(type(value) is not int or value <= 0 for value in body["repository_ids"])):
            raise RepositoryError("invalid_input", "Select between 1 and 50 GitHub repository IDs.")
        generation, account = self.require_github_session()
        result = {"imported": [], "already_configured": [], "failed": []}
        selected = []
        for repository_id in dict.fromkeys(body["repository_ids"]):
            try:
                metadata = self.auth.repository(repository_id)
                if metadata.get("id") != repository_id:
                    raise ValueError("Repository identity changed.")
                item = normalize_repositories([{
                    "source_kind": "github", "url": metadata.get("html_url"),
                    "name": metadata.get("full_name") or metadata.get("name"), "product": "GitHub repositories",
                    "github_repository_id": repository_id, "github_account_id": account,
                    "installation_id": metadata.get("installation_id"), "private": metadata.get("private"),
                    "ref": "HEAD", "exclude_globs": list(self.collector.config["exclude_globs"]),
                }], self.config_path.parent, self.collector.config)[0]
                selected.append(item)
            except GitHubAuthError as exc:
                result["failed"].append({"id": repository_id, "code": exc.code, "message": str(exc)})
            except (ValueError, TypeError):
                result["failed"].append({"id": repository_id, "code": "invalid_repository",
                                         "message": "GitHub returned invalid repository metadata."})
        with self.write_lock:
            self.writable_config()
            with self.auth.session_guard(generation, account):
                if not selected:
                    return self.github_response(result, generation)

                def add(overrides):
                    current = self.effective_entries(overrides)
                    paths = {entry["path"] for entry in current}
                    ids = {entry.get("github_repository_id") for entry in current if entry.get("source_kind") == "github"}
                    for item in selected:
                        summary = {"id": item["github_repository_id"], "name": item["name"], "url": item["url"]}
                        if item["path"] in paths or item["github_repository_id"] in ids:
                            result["already_configured"].append(summary)
                            continue
                        overrides[item["path"]] = item
                        paths.add(item["path"])
                        ids.add(item["github_repository_id"])
                        result["imported"].append(summary)

                def guarded_config():
                    self.checked_config_bytes()
                    with self.auth.session_guard(generation, account):
                        pass

                _, overrides = self.registry.update(add, guarded_config)
                self.use_registry(overrides)
                return self.github_response(result, generation)

    def entry_path(self, item):
        """Normalize persisted relative paths without discarding entry metadata."""
        return repository_path(item, self.config_path.parent)

    def effective_entries(self, overrides, *, include_cli=True):
        base = self.config_path.parent if self.config_path else Path.cwd()
        config = self.collector.config
        entries = merge_repositories(self.base_entries, overrides, base)
        if include_cli:
            entries.extend({"path": path, "product": "My repositories"} for path in config.get("_cli_paths", []))
        return normalize_repositories(entries, base, config, config.get("_ref_override"))

    def identities(self, entries=None):
        result = {}
        for item in self.collector.config["repositories"] if entries is None else entries:
            if item.get("url"):
                continue
            try:
                result[item["path"]] = repository_locations(item["path"])
            except (GitError, OSError, ValueError):
                # Unavailable sources must remain removable. Their configured
                # paths and any previously observed locations are still checked.
                pass
        return result

    def writable_config(self, identities=None, extra_locations=(), entries=None):
        """Validate a config-adjacent registry write; never write the JSON."""
        self.registry.validate_paths()
        locations = set(extra_locations)
        for item in self.collector.config["repositories"] if entries is None else entries:
            if not item.get("url"):
                locations.add(Path(item["path"]).resolve())
        if identities is None:
            identities = self.identities() if entries is None else self.identities(entries)
        for root, common, registered in identities.values():
            locations.update({root, common, *registered})
        for row in self.read()["repositories"]:
            if row.get("source_kind") == "public" or row.get("url"):
                continue
            if row.get("common_dir"):
                locations.add(Path(row["common_dir"]).resolve())
            locations.update(Path(tree["path"]).resolve() for tree in row.get("worktrees", []) if tree.get("path"))
        if any(artifact.is_relative_to(path) for path in locations
               for artifact in [self.config_path, *self.registry.artifacts]):
            raise RepositoryError("unsafe_config", "Move dashboard configuration outside monitored repositories and their linked worktrees.", 409)
        # Identity checks can take time. Read after them so an external edit
        # during inspection cannot be replaced by the older configuration.
        current = self.checked_config_bytes()
        return json.loads(current) if current else {k: v for k, v in self.collector.config.items() if not k.startswith("_")}

    def checked_config_bytes(self):
        current = self.config_path.read_bytes() if self.config_path.exists() else None
        if current != self.config_digest:
            raise RepositoryError("config_changed", "Configuration changed outside the dashboard. Restart to reload it before changing repositories.", 409)
        return current

    def use_registry(self, overrides, *, prioritize=None):
        """Publish only a committed registry snapshot, retaining CLI sources."""
        entries = self.effective_entries(overrides)
        if prioritize:
            entries.sort(key=lambda item: item["path"] != prioritize)
        with self.lock:
            self.registry_overrides = copy.deepcopy(overrides)
            self.persisted_paths = {item["path"] for item in self.effective_entries(overrides, include_cli=False)}
            self.collector.config["repositories"] = entries
            self.registry_revision += 1
        self.publish(self.read())
        self.wake.set()

    def add_repository(self, body):
        if not self.config_path:
            raise RepositoryError("read_only", "Start with --config to save repositories from the UI.", 403)
        if not isinstance(body, dict) or set(body) - {"path", "url", "name", "product"}:
            raise RepositoryError("invalid_input", "Supply either a local path or a public GitHub URL, optional name, and optional product.")
        for key in ("path", "url", "name", "product"):
            value = body.get(key, "")
            if not isinstance(value, str) or len(value) > (4096 if key in ("path", "url") else 160) or any(ord(c) < 32 for c in value):
                raise RepositoryError("invalid_input", "Invalid " + key + ".")
        if body.get("url"):
            if body.get("path"):
                raise RepositoryError("invalid_input", "Choose either a public URL or a local path.")
            try:
                url = public_url(body["url"])
                public_metadata(url)
            except ValueError as exc:
                raise RepositoryError("invalid_public_repository", str(exc)) from None
            with self.write_lock:
                item = {"url": url, "path": url, "source_kind": "public", "ref": "HEAD",
                    "name": body.get("name", "").strip() or url.rsplit("/", 1)[-1],
                    "product": body.get("product", "").strip() or "Public repositories",
                    "exclude_globs": list(self.collector.config["exclude_globs"])}
                return self.save_repository(item)
        path = Path(body.get("path", "").strip()).expanduser()
        if not path.is_absolute() or not path.is_dir():
            raise RepositoryError("invalid_path", "Enter an existing absolute local checkout path on this machine.")
        try:
            root, common, registered = repository_locations(path)
        except Exception:
            raise RepositoryError("invalid_repository", "This path is not an accessible Git worktree.") from None
        with self.write_lock:
            config = self.collector.config
            item = {"path": str(root), "name": body.get("name", "").strip() or root.name,
                "product": body.get("product", "").strip() or "My repositories", "ref": "HEAD",
                "exclude_globs": list(config["exclude_globs"])}
            return self.save_repository(item, extra_locations={common, *registered})

    def save_repository(self, item, extra_locations=()):
        # Called under write_lock by both source types.
        self.writable_config(extra_locations=extra_locations)

        def add(overrides):
            entries = self.effective_entries(overrides)
            identities = self.identities(entries)
            self.writable_config(identities=identities, extra_locations=extra_locations, entries=entries)
            if any(existing["path"] == item["path"] for existing in entries):
                raise RepositoryError("duplicate", "This repository is already configured.", 409)
            if not item.get("url"):
                _, common, _ = repository_locations(item["path"])
                if any(identity[1] == common for identity in identities.values()):
                    raise RepositoryError("duplicate", "This repository or a linked worktree is already configured.", 409)
            overrides[item["path"]] = item

        _, overrides = self.registry.update(add, self.checked_config_bytes)
        self.use_registry(overrides, prioritize=item["path"])
        return item

    def remove_repository(self, body):
        if not self.config_path:
            raise RepositoryError("read_only", "Start with --config to save repository changes from the UI.", 403)
        if (not isinstance(body, dict) or set(body) != {"path"}
                or not isinstance(body["path"], str) or not body["path"]
                or len(body["path"]) > 4096 or any(ord(c) < 32 for c in body["path"])):
            raise RepositoryError("invalid_input", "Supply the configured repository path or public URL.")
        path = body["path"]
        with self.write_lock:
            self.writable_config()

            def remove(overrides):
                entries = self.effective_entries(overrides)
                item = next((item for item in entries if item["path"] == path), None)
                if item is None:
                    raise RepositoryError("not_found", "This repository is no longer configured.", 404)
                identities = self.identities(entries)
                removed_paths = {path}
                if path in identities:
                    common = identities[path][1]
                    removed_paths.update(key for key, identity in identities.items() if identity[1] == common)
                for row in self.read()["repositories"]:
                    aliases = set(row.get("configured_paths", [row["path"]]))
                    if path in aliases:
                        removed_paths.update(aliases.intersection(entry["path"] for entry in entries))
                persisted = {entry["path"] for entry in self.effective_entries(overrides, include_cli=False)}
                if (not removed_paths <= persisted
                        or removed_paths.intersection(self.collector.config.get("_cli_paths", []))):
                    raise RepositoryError("read_only", "This source was supplied with --repo. Remove that command-line argument before restarting.", 403)
                self.writable_config(identities=identities, entries=entries)
                for removed in removed_paths:
                    overrides[removed] = None
                return {"path": path, "name": item["name"], "configured_paths": sorted(removed_paths)}

            removed, overrides = self.registry.update(remove, self.checked_config_bytes)
            self.use_registry(overrides)
            return removed

    def loop(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock:
                revision = self.registry_revision
            try:
                if self.registry:
                    with self.write_lock:
                        overrides = self.registry.read()
                        if overrides != self.registry_overrides:
                            self.checked_config_bytes()
                            self.use_registry(overrides)
                            self.wake.clear()
                            revision = self.registry_revision
                def progress(data):
                    data["collection_running"] = True
                    self.publish(data, revision)
                    return self.wake.is_set() or self.stop.is_set()
                data = self.collector.collect(live=True, on_progress=progress)
                data["collection_running"] = False
                self.publish(data, revision)
            except Exception as exc:
                with self.lock:
                    if revision == self.registry_revision:
                        self.snapshot["collection_running"] = False
                        self.snapshot["errors"] = ["Refresh failed: " + type(exc).__name__]
            self.wake.wait(self.collector.config["refresh_seconds"])


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
            elif route == "/api/github/status":
                self.json_response(state.github_status())
                return
            elif route == "/github-setup":
                try:
                    data = (ROOT / "docs" / "GITHUB-APP-SETUP.md").read_bytes()
                except OSError:
                    self.send_error(404)
                    return
                content_type = "text/plain; charset=utf-8"
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

        def do_POST(self):
            allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
            if self.headers.get("Origin") not in allowed or "http://" + self.headers.get("Host", "") not in allowed:
                self.json_response({"error": {"code": "forbidden", "message": "Local same-origin requests only."}}, 403)
                return
            github_actions = {"/api/github/" + action: action for action in ("start", "cancel", "disconnect")}
            if self.path not in {"/api/repositories", "/api/repositories/remove",
                                 "/api/github/repositories", "/api/github/import", "/api/commit-pulls", *github_actions}:
                self.json_response({"error": {"code": "not_found", "message": "Unknown endpoint."}}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192 or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise RepositoryError("invalid_request", "Send a JSON object no larger than 8 KiB.")
                self.connection.settimeout(5)
                body = json.loads(self.rfile.read(length))
                if self.path == "/api/commit-pulls":
                    result, status = state.commit_pulls(body), 200
                elif self.path in github_actions:
                    result, status = state.github_action(github_actions[self.path], body), 200
                elif self.path == "/api/github/repositories":
                    result, status = state.github_repositories(body), 200
                elif self.path == "/api/github/import":
                    result, status = state.import_github_repositories(body), 200
                elif self.path == "/api/repositories/remove":
                    result, status = {"removed": state.remove_repository(body)}, 200
                else:
                    result, status = {"repository": state.add_repository(body)}, 201
            except (RepositoryError, GitHubAuthError) as exc:
                result, status = {"error": {"code": exc.code, "message": str(exc)}}, exc.status
            except (ValueError, UnicodeError):
                result, status = {"error": {"code": "invalid_json", "message": "Invalid JSON request."}}, 400
            except OSError:
                result, status = {"error": {"code": "storage_failed", "message": "Could not save dashboard configuration."}}, 503
            self.json_response(result, status)

        def json_response(self, result, status=200):
            payload = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(payload)

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
        validate_state_destination(args.config, state_path)
        collector = DashboardCollector(config, state_path)
        if args.command == "scan":
            try:
                snapshot = collector.collect()
                export_html(args.output, snapshot)
                if args.json_output:
                    atomic_json(args.json_output, snapshot)
            finally:
                collector.auth.close()
            ok = sum(r["status"] != "error" for r in snapshot["repositories"])
            print(f"Report: {Path(args.output).resolve()} ({ok}/{len(snapshot['repositories'])} repositories observed)")
            return 0 if ok else 2
        print("Collecting local Git data…", flush=True)
        state = LiveState(collector, args.config)
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
        state.worker.start()
        print(f"Open http://127.0.0.1:{args.port} — refresh every {config['refresh_seconds']} seconds. Ctrl+C stops.", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            print("\nDashboard stopped.")
        finally:
            state.stop.set()
            state.wake.set()
            server.server_close()
            state.auth.close()
            state.worker.join(timeout=2)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
