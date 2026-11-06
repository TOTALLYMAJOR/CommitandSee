"""Offline lifecycle, disclosure, and authorization-boundary regressions."""
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import github_auth as auth_module
from github_auth import GitHubAuth, GitHubAuthError, github_app_config


CONFIG = {"client_id": "Iv1.fixturepublicid", "app_slug": "fixture-observer"}
ACCESS = "ghu_fixture_access_token_do_not_disclose"
REFRESH = "ghr_fixture_refresh_token_do_not_disclose"
ROTATED_ACCESS = "ghu_rotated_access_token_do_not_disclose"
ROTATED_REFRESH = "ghr_rotated_refresh_token_do_not_disclose"
DEVICE = "fixture_device_secret_do_not_disclose"


def token_payload(access=ACCESS, refresh=REFRESH, expires=28800):
    result = {"access_token": access, "token_type": "bearer", "expires_in": expires}
    if refresh:
        result.update(refresh_token=refresh, refresh_token_expires_in=15897600)
    return result


def repository(repo_id=11, *, private=True):
    name = "repo-" + str(repo_id)
    return {"id": repo_id, "name": name, "owner": {"login": "octocat", "id": 1},
            "full_name": "octocat/" + name, "private": private,
            "html_url": "https://github.com/octocat/" + name, "default_branch": "main",
            "archived": False, "permissions": {"pull": True}, "unexpected_secret": ACCESS}


def installation(installation_id=7, *, contents="read", slug="fixture-observer"):
    return {"id": installation_id, "app_slug": slug, "permissions": {"contents": contents, "metadata": "read"}, "suspended_at": None}


class Clock:
    def __init__(self):
        self.now = 100.0
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, event, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return event.is_set()


class Provider:
    def __init__(self):
        self.calls = []
        self.device = {"device_code": DEVICE, "user_code": "ABCD-EFGH", "expires_in": 900,
                       "interval": 5, "verification_uri": auth_module.VERIFICATION_URI}
        self.polls = [token_payload()]
        self.refresh = token_payload(ROTATED_ACCESS, ROTATED_REFRESH)
        self.user = {"id": 1, "login": "octocat", "secret": ACCESS}
        self.installations = {"total_count": 1, "installations": [installation()]}
        self.pages = {"/user/installations/7/repositories?per_page=100&page=1": {"total_count": 1, "repositories": [repository()]}}

    def __call__(self, method, url, *, data=None, token=None):
        self.calls.append((method, url, copy.deepcopy(data), token))
        if url == auth_module.DEVICE_ENDPOINT:
            return copy.deepcopy(self.device)
        if url == auth_module.TOKEN_ENDPOINT:
            value = self.refresh if data["grant_type"] == "refresh_token" else self.polls.pop(0)
        elif url == auth_module.API_ROOT + "/user":
            value = self.user
        elif url == auth_module.API_ROOT + "/user/installations?per_page=100&page=1":
            value = self.installations
        else:
            path = url.removeprefix(auth_module.API_ROOT)
            value = repository(int(path.rsplit("/", 1)[-1])) if path.startswith("/repositories/") else self.pages[path]
        if callable(value):
            value = value()
        if isinstance(value, BaseException):
            raise value
        return copy.deepcopy(value)


class GitHubAuthTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict("os.environ", {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.provider, self.clock = Provider(), Clock()
        self.events = []
        self.auth = self.new_auth()

    def new_auth(self, **kwargs):
        auth = GitHubAuth(CONFIG, request=kwargs.pop("request", self.provider),
                          clock=self.clock, wait=kwargs.pop("wait", self.clock.wait),
                          on_change=self.events.append, **kwargs)
        self.addCleanup(auth.close)
        return auth

    def connect(self, auth=None):
        auth = auth or self.auth
        auth.start()
        auth._thread.join(2)
        self.assertFalse(auth._thread.is_alive())
        self.assertEqual(auth.status()["status"], "connected", auth.status())
        return auth

    def assert_no_secrets(self, value):
        encoded = json.dumps(value)
        for secret in (ACCESS, REFRESH, ROTATED_ACCESS, ROTATED_REFRESH, DEVICE):
            self.assertNotIn(secret, encoded)

    def test_configuration_is_public_only_and_environment_can_override(self):
        self.assertEqual(github_app_config(CONFIG, environ={}), CONFIG)
        self.assertEqual(github_app_config(CONFIG, environ={"COMMITANDSEE_GITHUB_APP_SLUG": "another-app"})["app_slug"], "another-app")
        for value in ({"client_secret": "secret"}, {"client_id": "with space"}, {"app_slug": "../../wrong"}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                github_app_config(value, environ={})
        empty = GitHubAuth({}, request=lambda *a, **k: self.fail("Unconfigured auth made a request"))
        self.addCleanup(empty.close)
        self.assertEqual(empty.status()["status"], "unconfigured")
        with self.assertRaises(GitHubAuthError) as raised:
            empty.start()
        self.assertEqual(raised.exception.code, "unconfigured")

    def test_bundled_public_defaults_apply_only_when_config_is_omitted(self):
        with tempfile.TemporaryDirectory(prefix="github-public-defaults-") as directory:
            asset = Path(directory) / "github_app_defaults.json"
            asset.write_text(json.dumps(CONFIG))
            with patch.object(auth_module, "BUNDLED_CONFIG_PATH", asset):
                self.assertEqual(github_app_config(None, environ={}), CONFIG)
                default = GitHubAuth(request=lambda *args, **kwargs: self.fail("Constructor made a provider request"))
                self.addCleanup(default.close)
                self.assertEqual(default.status()["status"], "disconnected")
                self.assertTrue(default.status()["configured"])
                self.assertEqual(github_app_config({}, environ={}), {"client_id": "", "app_slug": ""})
                self.assertEqual(github_app_config({"client_id": "", "app_slug": ""}, environ={}), {"client_id": "", "app_slug": ""})
                self.assertEqual(github_app_config(None, environ={"COMMITANDSEE_GITHUB_APP_SLUG": "fork-app"}),
                                 {"client_id": CONFIG["client_id"], "app_slug": "fork-app"})
                self.assertEqual(github_app_config({}, environ={"COMMITANDSEE_GITHUB_CLIENT_ID": CONFIG["client_id"],
                    "COMMITANDSEE_GITHUB_APP_SLUG": CONFIG["app_slug"]}), CONFIG)

    def test_missing_or_invalid_bundled_defaults_never_disclose_asset_contents(self):
        with tempfile.TemporaryDirectory(prefix="github-public-defaults-") as directory:
            asset = Path(directory) / "github_app_defaults.json"
            with patch.object(auth_module, "BUNDLED_CONFIG_PATH", asset):
                self.assertEqual(github_app_config(None, environ={}), {"client_id": "", "app_slug": ""})
                for content in (ACCESS, json.dumps({"client_secret": ACCESS}), "x" * 4097):
                    with self.subTest(length=len(content)):
                        asset.write_text(content)
                        with self.assertRaises(ValueError) as raised:
                            github_app_config(None, environ={})
                        self.assertNotIn(ACCESS, str(raised.exception))
                        self.assertEqual(github_app_config({}, environ={}), {"client_id": "", "app_slug": ""})

    def test_success_exposes_only_safe_account_and_never_credentials(self):
        self.connect()
        status = self.auth.status()
        self.assertEqual(status["user"], {"id": 1, "login": "octocat"})
        self.assertTrue(status["session_only"])
        self.assertIsNone(status["user_code"])
        self.assertEqual(status["installation_url"], "https://github.com/apps/fixture-observer/installations/new")
        self.assertEqual(self.auth.token(), ACCESS)
        self.assert_no_secrets([status, self.events])
        self.assertEqual(self.provider.calls[0][2], {"client_id": CONFIG["client_id"], "scope": "offline_access"})

    def test_pending_flow_is_single_and_cancel_discards_late_token(self):
        entered, release = threading.Event(), threading.Event()
        def delayed_token():
            entered.set()
            self.assertTrue(release.wait(2))
            return token_payload()
        self.provider.polls = [delayed_token]
        self.auth.start()
        try:
            self.assertTrue(entered.wait(2))
            generation = self.auth.generation
            pending = self.auth.start()
            self.assertEqual(self.auth.generation, generation)
            self.assertEqual(pending["user_code"], "ABCD-EFGH")
            self.assertEqual(pending["verification_uri"], auth_module.VERIFICATION_URI)
            self.assert_no_secrets(pending)
            self.auth.cancel()
            self.assertGreater(self.auth.generation, generation)
        finally:
            release.set()
            self.auth._thread.join(2)
        self.assertEqual(self.auth.status()["status"], "disconnected")
        self.assertIsNone(self.auth.status()["user"])
        with self.assertRaises(GitHubAuthError):
            self.auth.token()

    def test_disconnect_during_identity_verification_cannot_revive_session(self):
        entered, release = threading.Event(), threading.Event()
        original = self.provider
        def request(method, url, **kwargs):
            if url == auth_module.API_ROOT + "/user":
                entered.set()
                self.assertTrue(release.wait(2))
            return original(method, url, **kwargs)
        auth = self.new_auth(request=request)
        auth.start()
        try:
            self.assertTrue(entered.wait(2))
            auth.disconnect()
        finally:
            release.set()
            auth._thread.join(2)
        self.assertEqual(auth.status()["status"], "disconnected")
        self.assertIsNone(auth._access_token)

    def test_polling_honors_interval_and_slow_down(self):
        self.provider.polls = [{"error": "authorization_pending"}, {"error": "slow_down", "interval": 13}, token_payload()]
        self.connect()
        self.assertEqual(self.clock.waits, [5, 5, 13])

    def test_expiry_and_denial_clear_device_information(self):
        for error in ("access_denied", "expired_token", "incorrect_device_code"):
            with self.subTest(error=error):
                self.provider.polls = [{"error": error, "error_description": ACCESS}]
                auth = self.new_auth()
                auth.start()
                auth._thread.join(2)
                self.assertEqual(auth.status()["status"], "error")
                self.assertIsNone(auth.status()["user_code"])
                self.assert_no_secrets(auth.status())
        self.provider.device["expires_in"] = 4
        self.provider.polls = [token_payload()]
        auth = self.new_auth()
        auth.start()
        auth._thread.join(2)
        self.assertEqual(auth.status()["status"], "error")
        self.assertEqual(len(self.provider.polls), 1, "Expired code must not be polled")

    def test_redirected_verification_uri_and_malformed_id_are_rejected(self):
        self.provider.device["verification_uri"] = "https://github.com.evil/login/device"
        self.auth.start()
        self.auth._thread.join(2)
        self.assertEqual(self.auth.status()["status"], "error")
        self.assertIsNone(self.auth.status()["user_code"])
        self.provider.device["verification_uri"] = auth_module.VERIFICATION_URI
        self.provider.user["id"] = True
        self.provider.polls = [token_payload()]
        self.auth.start()
        self.auth._thread.join(2)
        self.assertEqual(self.auth.status()["status"], "error")

    def test_refresh_rotates_in_memory_without_client_secret(self):
        self.provider.polls = [token_payload(expires=90)]
        self.connect()
        generation = self.auth.generation
        self.clock.now += 65
        self.assertEqual(self.auth.token(), ROTATED_ACCESS)
        self.assertEqual(self.auth.generation, generation)
        refresh_calls = [call for call in self.provider.calls if call[2] and call[2].get("grant_type") == "refresh_token"]
        self.assertEqual(len(refresh_calls), 1)
        self.assertNotIn("client_secret", refresh_calls[0][2])
        self.assertEqual(self.auth._refresh_token, ROTATED_REFRESH)
        self.assert_no_secrets(self.auth.status())

    def test_disconnect_during_refresh_discards_rotated_tokens(self):
        self.provider.polls = [token_payload(expires=90)]
        self.connect()
        self.clock.now += 65
        entered, release = threading.Event(), threading.Event()
        def delayed_refresh():
            entered.set()
            self.assertTrue(release.wait(2))
            return token_payload(ROTATED_ACCESS, ROTATED_REFRESH)
        self.provider.refresh = delayed_refresh
        errors = []
        def refresh():
            try:
                self.auth.token()
            except GitHubAuthError as error:
                errors.append(error.code)
        worker = threading.Thread(target=refresh)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.auth.disconnect()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, ["session_changed"])
        self.assertEqual(self.auth.status()["status"], "disconnected")
        self.assertIsNone(self.auth._access_token)
        self.assertIsNone(self.auth._refresh_token)

    def test_revoked_refresh_and_api_401_invalidate_but_403_does_not(self):
        for status in (403, 401):
            with self.subTest(status=status):
                self.provider.polls = [token_payload()]
                auth = self.connect(self.new_auth())
                generation = auth.generation
                self.provider.installations = auth_module._http_error(status)
                with self.assertRaises(GitHubAuthError):
                    auth.repositories()
                self.assertEqual(auth.status()["status"], "error" if status == 401 else "connected")
                self.assertEqual(auth.generation > generation, status == 401)
        self.provider.polls = [token_payload(expires=90)]
        auth = self.connect(self.new_auth())
        self.clock.now += 65
        self.provider.refresh = {"error": "bad_refresh_token", "error_description": REFRESH}
        with self.assertRaises(GitHubAuthError):
            auth.token()
        self.assertEqual(auth.status()["status"], "error")
        self.assert_no_secrets(auth.status())

    def test_no_refresh_expiry_and_close_forget_all_credentials(self):
        self.provider.polls = [token_payload(refresh=None, expires=10)]
        self.connect()
        self.clock.now += 11
        self.assertEqual(self.auth.status()["status"], "error")
        self.assertIsNone(self.auth._access_token)
        closed = self.auth.close()
        self.assert_no_secrets(closed)
        with self.assertRaises(GitHubAuthError) as raised:
            self.auth.start()
        self.assertEqual(raised.exception.code, "closed")

    def test_discovery_filters_write_permissions_and_sanitizes_private_rows(self):
        broad = installation(8)
        broad["permissions"]["issues"] = "write"
        self.provider.installations = {"total_count": 4, "installations": [installation(), broad, installation(9, contents="write"), installation(10, slug="another-app")]}
        self.connect()
        result = self.auth.repositories()
        self.assertEqual([row["id"] for row in result["repositories"]], [11])
        self.assertTrue(result["repositories"][0]["private"])
        self.assertEqual(result["repositories"][0]["installation_id"], 7)
        self.assertIn("excluded", result["message"])
        self.assert_no_secrets(result)
        self.assertFalse(any("/8/" in call[1] or "/9/" in call[1] or "/10/" in call[1] for call in self.provider.calls))

    def test_discovery_pagination_and_partial_limits_are_explicit(self):
        self.provider.pages = {
            f"/user/installations/7/repositories?per_page=100&page={page}": {
                "total_count": 1001, "repositories": [repository(index) for index in range((page-1)*100+1, page*100+1)]}
            for page in range(1, 11)}
        self.connect()
        result = self.auth.repositories()
        self.assertEqual(len(result["repositories"]), 1000)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["limits"]["repositories"], 1000)
        self.assertIn("partial", result["message"])

    def test_repository_selection_revalidates_id_installation_and_identity(self):
        self.connect()
        self.auth.repositories()
        self.assertEqual(self.auth.repository(11)["full_name"], "octocat/repo-11")
        for value in (True, "11", 12):
            with self.subTest(value=value), self.assertRaises(GitHubAuthError):
                self.auth.repository(value)
        self.provider.installations["installations"][0]["permissions"]["contents"] = "write"
        with self.assertRaises(GitHubAuthError) as raised:
            self.auth.repository(11)
        self.assertEqual(raised.exception.code, "installation_unavailable")

    def test_logout_during_discovery_discards_private_results(self):
        self.connect()
        entered, release = threading.Event(), threading.Event()
        self.provider.pages["/user/installations/7/repositories?per_page=100&page=1"] = lambda: (
            entered.set(), release.wait(2), {"total_count": 1, "repositories": [repository()]})[-1]
        results, errors = [], []
        def discover():
            try:
                results.append(self.auth.repositories())
            except GitHubAuthError as error:
                errors.append(error.code)
        worker = threading.Thread(target=discover)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.auth.disconnect()
        finally:
            release.set()
            worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [])
        self.assertEqual(errors, ["session_changed"])
        self.assertEqual(self.auth._repositories, {})

    def test_session_guard_blocks_logout_until_short_commit_finishes(self):
        self.connect()
        generation = self.auth.generation
        entered = threading.Event()
        def disconnect():
            entered.set()
            self.auth.disconnect()
        with self.auth.session_guard(generation, 1):
            worker = threading.Thread(target=disconnect)
            worker.start()
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.auth.generation, generation)
        worker.join(2)
        self.assertFalse(worker.is_alive())
        with self.assertRaises(GitHubAuthError):
            with self.auth.session_guard(generation, 1):
                self.fail("Stale commit was accepted")

    def test_api_is_not_an_arbitrary_host_or_endpoint_proxy(self):
        self.connect()
        before = len(self.provider.calls)
        for path in ("https://evil.invalid/user", "//evil.invalid/user", "/user?access_token=secret", "/repos/a/b", "/user/installations?per_page=101", "/user/installations?per_page=100&page=1&page=2"):
            with self.subTest(path=path), self.assertRaises(GitHubAuthError):
                self.auth.request_json(path)
        self.assertEqual(len(self.provider.calls), before)

    def test_account_switch_during_token_acquisition_cannot_authorize_old_result(self):
        self.connect()
        token = self.auth.token
        def switch_after_token():
            previous = token()
            self.auth.disconnect()
            self.provider.user = {"id": 2, "login": "other-user"}
            self.provider.polls = [token_payload(ROTATED_ACCESS, ROTATED_REFRESH)]
            self.connect()
            return previous
        with patch.object(self.auth, "token", side_effect=switch_after_token):
            with self.assertRaises(GitHubAuthError) as raised:
                self.auth.request_json("/user")
        self.assertEqual(raised.exception.code, "session_changed")
        self.assertEqual(self.auth.status()["user"]["id"], 2)
        old_requests = [call for call in self.provider.calls if call[0] == "GET" and call[3] == ACCESS]
        self.assertEqual(len(old_requests), 1, "Only initial identity verification may use the old token")

    def test_concurrent_token_callers_rotate_a_refresh_token_only_once(self):
        self.provider.polls = [token_payload(expires=90)]
        self.connect()
        self.clock.now += 65
        entered, release = threading.Event(), threading.Event()
        def delayed_refresh():
            entered.set()
            self.assertTrue(release.wait(2))
            return token_payload(ROTATED_ACCESS, ROTATED_REFRESH)
        self.provider.refresh = delayed_refresh
        results, errors = [], []
        def token():
            try:
                results.append(self.auth.token())
            except Exception as error:
                errors.append(type(error).__name__)
        workers = [threading.Thread(target=token) for _ in range(2)]
        try:
            workers[0].start()
            self.assertTrue(entered.wait(2))
            workers[1].start()
        finally:
            release.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(2)
        self.assertEqual(errors, [])
        self.assertEqual(results, [ROTATED_ACCESS, ROTATED_ACCESS])
        refresh_calls = [call for call in self.provider.calls if call[2] and call[2].get("grant_type") == "refresh_token"]
        self.assertEqual(len(refresh_calls), 1)

    def test_worker_start_failure_does_not_leave_a_pending_session(self):
        with patch.object(threading.Thread, "start", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(GitHubAuthError) as raised:
                self.auth.start()
        self.assertEqual(raised.exception.code, "worker_unavailable")
        self.assertEqual(self.auth.status()["status"], "error")
        self.assertIsNone(self.auth.status()["user_code"])


class HTTPBoundaryTests(unittest.TestCase):
    def test_http_errors_are_sanitized_and_redirects_are_not_followed(self):
        for status in (301, 401, 403, 404, 429, 500):
            with self.subTest(status=status):
                opener = MagicMock()
                opener.open.side_effect = HTTPError(auth_module.API_ROOT + "/user", status, ACCESS, {}, io.BytesIO(REFRESH.encode()))
                with patch.object(auth_module, "build_opener", return_value=opener):
                    with self.assertRaises(GitHubAuthError) as raised:
                        auth_module._request_json("GET", auth_module.API_ROOT + "/user", token=ACCESS)
                self.assertNotIn(ACCESS, str(raised.exception))
                self.assertNotIn(REFRESH, str(raised.exception))
        self.assertIsNone(auth_module._NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_network_errors_and_oversize_or_invalid_responses_are_bounded(self):
        opener = MagicMock()
        opener.open.side_effect = URLError(ACCESS)
        with patch.object(auth_module, "build_opener", return_value=opener):
            with self.assertRaises(GitHubAuthError) as raised:
                auth_module._request_json("GET", auth_module.API_ROOT + "/user", token=ACCESS)
        self.assertNotIn(ACCESS, str(raised.exception))
        opener.open.side_effect = None
        for payload in (b"x" * (auth_module.MAX_RESPONSE_BYTES + 1), b"not-json", b"[]"):
            with self.subTest(size=len(payload)):
                opener.open.return_value.__enter__.return_value.read.return_value = payload
                with patch.object(auth_module, "build_opener", return_value=opener):
                    with self.assertRaises(GitHubAuthError):
                        auth_module._request_json("GET", auth_module.API_ROOT + "/user", token=ACCESS)
                opener.open.return_value.__enter__.return_value.read.assert_called_with(auth_module.MAX_RESPONSE_BYTES + 1)


if __name__ == "__main__":
    unittest.main()
