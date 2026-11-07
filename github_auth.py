"""GitHub App device sign-in with credentials held only in this process.

No token is written to a file, returned in a status response, or logged. Closing
the app forgets the session. Provider revocation is separate from local logout.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
import math
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEVICE_ENDPOINT = "https://github.com/login/device/code"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"
VERIFICATION_URI = "https://github.com/login/device"
API_ROOT = "https://api.github.com"
REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
BUNDLED_CONFIG_PATH = Path(__file__).with_name("github_app_defaults.json")
DISCOVERY_LIMITS = {"installations": 100, "repositories": 1000, "requests": 12,
                    "request_start_window_seconds": 30, "request_timeout_seconds": REQUEST_TIMEOUT}


class GitHubAuthError(ValueError):
    """An intentionally sanitized error suitable for a local API response."""

    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def github_app_config(raw=None, *, environ=None):
    """Return public identity; omission uses the bundle, explicit blanks disable.

    Environment settings override either source. The fixed, module-adjacent
    asset contains public registration identifiers, never credentials.
    """
    if raw is None:
        try:
            with BUNDLED_CONFIG_PATH.open("rb") as stream:
                payload = stream.read(4097)
        except FileNotFoundError:
            raw = {}
        except OSError:
            raise ValueError("Bundled GitHub App configuration could not be read.") from None
        else:
            try:
                if len(payload) > 4096:
                    raise ValueError()
                raw = json.loads(payload)
            except (ValueError, UnicodeError):
                raise ValueError("Bundled GitHub App configuration is invalid.") from None
    if not isinstance(raw, dict) or set(raw) - {"client_id", "app_slug"}:
        raise ValueError("github_app accepts only the public client_id and app_slug.")
    environment = os.environ if environ is None else environ
    values = {}
    patterns = {"client_id": r"[A-Za-z0-9_.-]{1,128}", "app_slug": r"[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?"}
    for key, pattern in patterns.items():
        value = environment.get("COMMITANDSEE_GITHUB_" + key.upper(), raw.get(key, ""))
        if not isinstance(value, str) or (value and not re.fullmatch(pattern, value)):
            raise ValueError("github_app " + key + " must be a valid public application identifier.")
        values[key] = value
    return values


def _positive_id(value):
    return type(value) is int and 0 < value < 2**63


def _seconds(value, *, maximum=31536000):
    return type(value) is int and 0 < value <= maximum


_PULL_PATH = re.compile(r"/repos/[A-Za-z0-9][A-Za-z0-9-]{0,38}/(?!\.{1,2}/)[A-Za-z0-9_.-]{1,100}"
                        r"/commits/[a-f0-9]{40}/pulls\?per_page=100")


def _api_path(path):
    if not isinstance(path, str):
        raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
    if _PULL_PATH.fullmatch(path):
        return path
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
    paged = re.fullmatch(r"/user/installations(?:/[1-9][0-9]*/repositories)?", parsed.path)
    if not paged and parsed.path != "/user" and not re.fullmatch(r"/repositories/[1-9][0-9]*", parsed.path):
        raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
    if parsed.query:
        try:
            query = parse_qs(parsed.query, strict_parsing=True)
        except ValueError:
            raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.") from None
        if not paged or set(query) - {"per_page", "page"}:
            raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
        for key, values in query.items():
            if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]{0,3}", values[0]):
                raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
            if int(values[0]) > (100 if key == "per_page" else 1000):
                raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub API request.")
    return path


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _http_error(status):
    if status == 401:
        return GitHubAuthError("authorization_lost", "GitHub authorization expired or was revoked. Sign in again.", 401)
    if status in (403, 429):
        return GitHubAuthError("github_access_limited", "GitHub denied this request or reached a rate limit. Check app access and try again later.", 503)
    if status == 404:
        return GitHubAuthError("repository_unavailable", "This GitHub resource is no longer available to this session.", 404)
    return GitHubAuthError("github_unavailable", "GitHub could not complete this request. Try again later.", 502)


def _request_json(method, url, *, data=None, token=None):
    """The sole network boundary: pinned HTTPS endpoints, no redirects, bounds."""
    if method == "POST":
        if url not in {DEVICE_ENDPOINT, TOKEN_ENDPOINT} or token is not None:
            raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub authentication request.")
    elif method == "GET" and url.startswith(API_ROOT + "/"):
        _api_path(url[len(API_ROOT):])
    else:
        raise GitHubAuthError("invalid_endpoint", "Unsupported GitHub authentication request.")
    headers = {"Accept": "application/json" if method == "POST" else "application/vnd.github+json",
               "User-Agent": "Commit-and-See", "X-GitHub-Api-Version": "2026-03-10"}
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    encoded = urlencode(data).encode("ascii") if data is not None else None
    if encoded is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=encoded, headers=headers, method=method)
    try:
        with build_opener(_NoRedirect).open(request, timeout=REQUEST_TIMEOUT) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise GitHubAuthError("response_too_large", "GitHub's response exceeded the local response limit.", 502)
        result = json.loads(payload)
    except HTTPError as error:
        raise _http_error(error.code) from None
    except (URLError, OSError, TimeoutError):
        raise GitHubAuthError("github_unavailable", "Cannot reach GitHub. Check your connection and try again.", 503) from None
    except GitHubAuthError:
        raise
    except (ValueError, UnicodeError):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid response.", 502) from None
    expected = list if _PULL_PATH.fullmatch(url.removeprefix(API_ROOT)) else dict
    if not isinstance(result, expected):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid response.", 502)
    return result


def _user(payload):
    if (not isinstance(payload, dict) or not _positive_id(payload.get("id"))
            or not isinstance(payload.get("login"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", payload["login"])):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid account identity.", 502)
    return {"id": payload["id"], "login": payload["login"]}


def _tokens(payload, now):
    if (not isinstance(payload, dict) or not isinstance(payload.get("token_type"), str)
            or payload["token_type"].lower() != "bearer"):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid authorization response.", 502)
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if not isinstance(access, str) or not re.fullmatch(r"ghu_[A-Za-z0-9_]{8,508}", access):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid authorization response.", 502)
    if refresh is not None and (not isinstance(refresh, str) or not re.fullmatch(r"ghr_[A-Za-z0-9_]{8,508}", refresh)):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid authorization response.", 502)
    expires = payload.get("expires_in")
    refresh_expires = payload.get("refresh_token_expires_in")
    if ((expires is not None and not _seconds(expires))
            or (refresh is not None and not _seconds(refresh_expires))):
        raise GitHubAuthError("invalid_response", "GitHub returned an invalid authorization lifetime.", 502)
    return access, now + expires if expires is not None else None, refresh, now + refresh_expires if refresh else None


def _repository(payload, installation_id):
    """Select metadata deliberately; never return a provider response wholesale."""
    owner = payload.get("owner") if isinstance(payload, dict) else None
    name = payload.get("name") if isinstance(payload, dict) else None
    login = owner.get("login") if isinstance(owner, dict) else None
    if (not isinstance(payload, dict) or not _positive_id(payload.get("id"))
            or not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", login)
            or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)
            or name in {".", ".."} or payload.get("full_name") != login + "/" + name
            or payload.get("html_url") != "https://github.com/" + login + "/" + name
            or type(payload.get("private")) is not bool or type(payload.get("archived")) is not bool
            or not isinstance(payload.get("default_branch"), str)
            or not 0 < len(payload["default_branch"]) <= 255
            or any(ord(c) < 32 or ord(c) == 127 for c in payload["default_branch"])):
        raise GitHubAuthError("invalid_response", "GitHub returned invalid repository metadata.", 502)
    return {"id": payload["id"], "full_name": payload["full_name"], "name": name,
            "owner": login, "private": payload["private"], "html_url": payload["html_url"],
            "default_branch": payload["default_branch"], "archived": payload["archived"],
            "installation_id": installation_id}


class GitHubAuth:
    """One session and one device flow, isolated from late network completions.

    Test seams: request(method, url, *, data=None, token=None) returns a JSON
    dictionary; clock() is monotonic; wait(cancel_event, seconds) is interruptible.
    Lifecycle callbacks receive a safe status dictionary outside the auth lock.
    """

    def __init__(self, config=None, *, request=None, clock=None, wait=None, on_change=None):
        self.config = github_app_config(config)
        self._request = request or _request_json
        self._clock = clock or time.monotonic
        self._wait = wait or (lambda event, seconds: event.wait(seconds))
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._generation = 0
        self._closed = False
        self._cancel = threading.Event()
        self._thread = None
        self._on_change = on_change
        self._configured = bool(self.config["client_id"] and self.config["app_slug"])
        self._state = "disconnected" if self._configured else "unconfigured"
        self._message = ("Sign in to choose repositories available to you and this GitHub App."
                         if self._configured else "GitHub sign-in is not configured. Set the public GitHub App client ID and app slug, then restart.")
        self._access_token = self._access_deadline = self._refresh_token = self._refresh_deadline = None
        self._user = None
        self._user_code = self._device_deadline = None
        self._repositories = {}

    @property
    def generation(self):
        with self._lock:
            return self._generation

    def set_on_change(self, callback):
        with self._lock:
            self._on_change = callback

    def _snapshot(self):
        return {"status": self._state, "configured": self._configured, "session_only": True,
                "generation": self._generation, "user": copy.deepcopy(self._user),
                "user_code": self._user_code,
                "verification_uri": VERIFICATION_URI if self._user_code else None,
                "expires_in": max(0, math.ceil(self._device_deadline - self._clock())) if self._device_deadline is not None else None,
                "installation_url": "https://github.com/apps/" + self.config["app_slug"] + "/installations/new" if self.config["app_slug"] else None,
                "message": self._message}

    def _notify(self):
        with self._lock:
            callback, status = self._on_change, self._snapshot()
        if callback:
            try:
                callback(status)
            except Exception:
                # A UI observer must not break credential clearing or expose an
                # exception containing provider responses or session credentials.
                pass

    def _clear(self, state, message):
        self._cancel.set()
        self._generation += 1
        self._access_token = self._access_deadline = self._refresh_token = self._refresh_deadline = None
        self._user = None
        self._user_code = self._device_deadline = None
        self._repositories = {}
        self._state, self._message = state, message

    def status(self):
        changed = False
        with self._lock:
            if (self._state == "connected" and self._access_deadline is not None
                    and self._clock() >= self._access_deadline
                    and (not self._refresh_token or self._clock() >= self._refresh_deadline)):
                self._clear("error", "GitHub sign-in expired. Sign in again.")
                changed = True
            result = self._snapshot()
        if changed:
            self._notify()
        return result

    def start(self):
        failure = None
        with self._lock:
            if self._closed:
                raise GitHubAuthError("closed", "GitHub sign-in is unavailable after shutdown.", 503)
            if not self._configured:
                raise GitHubAuthError("unconfigured", self._message, 409)
            if self._state in {"pending", "connected"}:
                return self._snapshot()
            self._clear("pending", "Requesting a GitHub sign-in code.")
            self._cancel = threading.Event()
            generation, cancel = self._generation, self._cancel
            self._thread = threading.Thread(target=self._flow, args=(generation, cancel), name="github-device-sign-in", daemon=True)
            try:
                self._thread.start()
            except RuntimeError:
                self._clear("error", "The GitHub sign-in worker could not start. Try again.")
                failure = GitHubAuthError("worker_unavailable", self._message, 503)
            result = self._snapshot()
        self._notify()
        if failure:
            raise failure
        return result

    def cancel(self):
        with self._lock:
            changed = self._state == "pending"
            if changed:
                self._clear("disconnected", "GitHub sign-in cancelled.")
            result = self._snapshot()
        if changed:
            self._notify()
        return result

    def disconnect(self):
        with self._lock:
            self._clear("disconnected" if self._configured else "unconfigured", "Disconnected. Session credentials were forgotten locally.")
            result = self._snapshot()
        self._notify()
        return result

    def close(self):
        with self._lock:
            if self._closed:
                return self._snapshot()
            self._closed = True
        return self.disconnect()

    def _fail(self, generation, message):
        with self._lock:
            if generation != self._generation or self._closed:
                return
            self._clear("error", message)
        self._notify()

    def _call(self, method, url, *, data=None, token=None):
        try:
            payload = self._request(method, url, data=data, token=token)
        except GitHubAuthError:
            raise
        except Exception:
            raise GitHubAuthError("github_unavailable", "GitHub could not complete this request. Try again later.", 503) from None
        expected = list if _PULL_PATH.fullmatch(url.removeprefix(API_ROOT)) else dict
        if not isinstance(payload, expected):
            raise GitHubAuthError("invalid_response", "GitHub returned an invalid response.", 502)
        return payload

    def _flow(self, generation, cancel):
        try:
            device = self._call("POST", DEVICE_ENDPOINT, data={"client_id": self.config["client_id"], "scope": "offline_access"})
            code = device.get("device_code")
            user_code = device.get("user_code")
            interval = device.get("interval", 5)
            if (not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,2048}", code)
                    or not isinstance(user_code, str) or not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", user_code)
                    or device.get("verification_uri") != VERIFICATION_URI
                    or not _seconds(device.get("expires_in"), maximum=1800)
                    or not _seconds(interval, maximum=1800)):
                error = device.get("error")
                message = "Enable device flow in the GitHub App settings, then try again." if error == "device_flow_disabled" else "GitHub could not issue a valid sign-in code. Check the app configuration."
                raise GitHubAuthError("device_start_failed", message, 502)
            deadline = self._clock() + device["expires_in"]
            with self._lock:
                if generation != self._generation or cancel.is_set():
                    return
                self._user_code, self._device_deadline = user_code, deadline
                self._message = "Enter this code on GitHub. Sign-in expires automatically; cancelling keeps this app disconnected."
            self._notify()
            while not cancel.is_set():
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break
                if self._wait(cancel, min(interval, remaining)) or cancel.is_set():
                    return
                if self._clock() >= deadline:
                    break
                payload = self._call("POST", TOKEN_ENDPOINT, data={"client_id": self.config["client_id"],
                    "device_code": code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                if cancel.is_set():
                    return
                if self._clock() >= deadline:
                    break
                error = payload.get("error")
                if error == "authorization_pending":
                    continue
                if error == "slow_down":
                    supplied = payload.get("interval")
                    interval = max(interval + 5, supplied if _seconds(supplied, maximum=1800) else 0)
                    continue
                if error:
                    message = {"access_denied": "GitHub sign-in was denied. Start again when ready.",
                               "expired_token": "GitHub sign-in code expired. Start again for a new code.",
                               "token_expired": "GitHub sign-in code expired. Start again for a new code.",
                               "device_flow_disabled": "Enable device flow in the GitHub App settings, then try again."}.get(error,
                               "GitHub could not authorize this sign-in. Check the app configuration and try again.")
                    raise GitHubAuthError("authorization_failed", message, 401)
                tokens = _tokens(payload, self._clock())
                user = _user(self._call("GET", API_ROOT + "/user", token=tokens[0]))
                with self._lock:
                    if generation != self._generation or cancel.is_set() or self._closed:
                        return
                    self._access_token, self._access_deadline, self._refresh_token, self._refresh_deadline = tokens
                    self._user, self._state = user, "connected"
                    self._user_code = self._device_deadline = None
                    self._message = "Connected for this app session. Credentials are forgotten when you disconnect or exit."
                self._notify()
                return
            self._fail(generation, "GitHub sign-in code expired. Start again for a new code.")
        except GitHubAuthError as error:
            self._fail(generation, error.message)
        except Exception:
            self._fail(generation, "GitHub sign-in could not be completed. Try again.")

    def token(self):
        """Return a current backend-only credential, refreshing once in memory."""
        with self._refresh_lock:
            with self._lock:
                if self._state != "connected" or not self._access_token or self._closed:
                    raise GitHubAuthError("not_connected", "Sign in to GitHub first.", 401)
                generation, account = self._generation, self._user["id"]
                access, expires = self._access_token, self._access_deadline
                refresh, refresh_expires = self._refresh_token, self._refresh_deadline
                now = self._clock()
                if expires is None or now + 30 < expires or (now < expires and not refresh):
                    return access
            if not refresh or now >= refresh_expires:
                self._fail(generation, "GitHub sign-in expired. Sign in again.")
                raise GitHubAuthError("authorization_lost", "GitHub sign-in expired. Sign in again.", 401)
            try:
                payload = self._call("POST", TOKEN_ENDPOINT, data={"client_id": self.config["client_id"],
                    "grant_type": "refresh_token", "refresh_token": refresh})
            except GitHubAuthError as error:
                if error.status == 401:
                    self._fail(generation, "GitHub sign-in expired or was revoked. Sign in again.")
                raise
            if payload.get("error"):
                self._fail(generation, "GitHub sign-in expired or was revoked. Sign in again.")
                raise GitHubAuthError("authorization_lost", "GitHub sign-in expired or was revoked. Sign in again.", 401)
            try:
                tokens = _tokens(payload, self._clock())
                user = _user(self._call("GET", API_ROOT + "/user", token=tokens[0]))
                if user["id"] != account:
                    raise GitHubAuthError("account_changed", "The GitHub account changed. Sign in again.", 409)
            except GitHubAuthError:
                self._fail(generation, "GitHub's refreshed session could not be verified. Sign in again.")
                raise GitHubAuthError("authorization_lost", "GitHub's refreshed session could not be verified. Sign in again.", 401) from None
            with self._lock:
                if generation != self._generation or self._state != "connected" or self._closed:
                    raise GitHubAuthError("session_changed", "The GitHub session changed. Try again after signing in.", 409)
                self._access_token, self._access_deadline, self._refresh_token, self._refresh_deadline = tokens
                self._user = user
                return self._access_token

    @contextmanager
    def session_guard(self, generation, user_id):
        """Hold a short publication/commit barrier; perform network work first."""
        with self._lock:
            if (type(generation) is not int or not _positive_id(user_id)
                    or generation != self._generation or self._state != "connected"
                    or self._closed or not self._user or self._user["id"] != user_id
                    or (self._access_deadline is not None and self._clock() >= self._access_deadline)):
                raise GitHubAuthError("session_changed", "The GitHub session changed. Sign in again or retry.", 409)
            yield

    def request_json(self, path, *, expected_session=None):
        """Authenticated, allowlisted GET for backend collectors; never a proxy."""
        _api_path(path)
        with self._lock:
            generation, account = self._generation, self._user["id"] if self._user else None
            if expected_session is not None and (generation, account) != expected_session:
                raise GitHubAuthError("session_changed", "The GitHub session changed. Try again.", 409)
        token = self.token()
        with self.session_guard(generation, account):
            if token != self._access_token:
                raise GitHubAuthError("session_changed", "The GitHub session changed. Try again.", 409)
        try:
            result = self._call("GET", API_ROOT + path, token=token)
        except GitHubAuthError as error:
            if error.status == 401:
                with self._lock:
                    current = generation == self._generation and token == self._access_token
                if current:
                    self._fail(generation, "GitHub authorization expired or was revoked. Sign in again.")
            raise
        with self.session_guard(generation, account):
            return result

    def _installations(self):
        payload = self.request_json("/user/installations?per_page=100&page=1")
        rows, total = payload.get("installations"), payload.get("total_count")
        if not isinstance(rows, list) or len(rows) > 100 or type(total) is not int or total < 0:
            raise GitHubAuthError("invalid_response", "GitHub returned invalid installation metadata.", 502)
        allowed, excluded = [], False
        for row in rows:
            permissions = row.get("permissions") if isinstance(row, dict) else None
            if (not isinstance(row, dict) or not _positive_id(row.get("id"))
                    or row.get("app_slug") != self.config["app_slug"]
                    or row.get("suspended_at") is not None or not isinstance(permissions, dict)
                    or permissions.get("contents") != "read"
                    or permissions.get("metadata", "read") != "read"
                    or any(not isinstance(value, str) or value not in {"read", "none"} for value in permissions.values())):
                excluded = True
                continue
            allowed.append(row["id"])
        return allowed, total > len(rows), excluded

    def installation(self, installation_id):
        if not _positive_id(installation_id):
            raise GitHubAuthError("invalid_installation", "Choose a valid GitHub App installation.")
        installations, truncated, _ = self._installations()
        if installation_id not in installations:
            message = "This installation is unavailable or is not read-only. Grant Contents: read-only and no write permissions to the configured GitHub App."
            if truncated:
                message += " Only the first 100 installations were checked."
            raise GitHubAuthError("installation_unavailable", message, 403)
        return {"id": installation_id}

    def repositories(self):
        """Discover the user/app intersection within explicit request/time caps."""
        with self._lock:
            generation, account = self._generation, self._user["id"] if self._user else None
        self.token()
        with self.session_guard(generation, account):
            pass
        deadline = self._clock() + DISCOVERY_LIMITS["request_start_window_seconds"]
        installations, truncated, excluded = self._installations()
        result, requests = {}, 1
        for installation_index, installation_id in enumerate(installations):
            page = 1
            visited = 0
            while True:
                if (len(result) >= DISCOVERY_LIMITS["repositories"] or requests >= DISCOVERY_LIMITS["requests"]
                        or self._clock() >= deadline):
                    truncated = True
                    break
                payload = self.request_json(f"/user/installations/{installation_id}/repositories?per_page=100&page={page}")
                requests += 1
                rows, total = payload.get("repositories"), payload.get("total_count")
                if not isinstance(rows, list) or len(rows) > 100 or type(total) is not int or total < 0:
                    raise GitHubAuthError("invalid_response", "GitHub returned invalid repository metadata.", 502)
                for row in rows:
                    entry = _repository(row, installation_id)
                    if len(result) >= DISCOVERY_LIMITS["repositories"] and entry["id"] not in result:
                        truncated = True
                        break
                    result[entry["id"]] = entry
                visited += len(rows)
                if visited >= total:
                    break
                if not rows:
                    truncated = True
                    break
                page += 1
            if requests >= DISCOVERY_LIMITS["requests"] or self._clock() >= deadline or len(result) >= DISCOVERY_LIMITS["repositories"]:
                if installation_index + 1 < len(installations):
                    truncated = True
                break
        with self.session_guard(generation, account):
            self._repositories = copy.deepcopy(result)
        messages = []
        if excluded:
            messages.append("Some installations were excluded. Use the configured GitHub App with Contents: read-only and no write permissions; suspended installations are unavailable.")
        if truncated:
            messages.append("Repository discovery reached a local limit; this list is partial.")
        if not result:
            messages.append("No permitted repositories were found. Install the GitHub App for selected repositories, then refresh this list.")
        return {"repositories": sorted(result.values(), key=lambda row: row["full_name"].lower()),
                "truncated": truncated, "limits": dict(DISCOVERY_LIMITS), "message": " ".join(messages)}

    def repository(self, repo_id):
        if not _positive_id(repo_id):
            raise GitHubAuthError("invalid_repository", "Choose a repository from the GitHub list.")
        with self._lock:
            chosen = copy.deepcopy(self._repositories.get(repo_id))
            generation, account = self._generation, self._user["id"] if self._user else None
        if chosen is None:
            raise GitHubAuthError("repository_not_selected", "Refresh the GitHub list and choose a permitted repository.", 409)
        self.installation(chosen["installation_id"])
        entry = _repository(self.request_json(f"/repositories/{repo_id}"), chosen["installation_id"])
        if entry["id"] != repo_id or entry["full_name"] != chosen["full_name"]:
            raise GitHubAuthError("repository_changed", "This repository changed. Refresh the GitHub list before adding it.", 409)
        with self.session_guard(generation, account):
            return entry
