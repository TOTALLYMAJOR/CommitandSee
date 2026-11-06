"""Offline authenticated collection, credential and cache-boundary regressions."""
from contextlib import contextmanager
import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import authenticated_repositories as authenticated


URL = "https://github.com/fixture/private-repository"
TOKEN = "fixture-session-secret"
ITEM = dict(url=URL, path=URL, source_kind="github", github_repository_id=42,
            github_account_id=101, installation_id=7, private=True,
            name="Private fixture", product="Fixture", exclude_globs=[])
METADATA = dict(id=42, html_url=URL, default_branch="main", private=True)
CONFIG = dict(timezone="UTC", days=30, max_commits=20000, repositories=[])


class FakeAuth:
    def __init__(self, account=101):
        self.generation, self.account, self.connected = 1, account, True
        self.metadata, self.error, self.token_calls = copy.deepcopy(METADATA), None, 0

    @contextmanager
    def session_guard(self, generation, account):
        if not self.connected or self.generation != generation or self.account != account:
            raise RuntimeError("fixture authorization changed")
        yield

    def installation(self, installation_id):
        if installation_id != 7:
            raise RuntimeError("installation denied")
        return {"id": installation_id}

    def request_json(self, path):
        if path != "/repositories/42":
            raise RuntimeError("unexpected request")
        if self.error:
            raise self.error
        return copy.deepcopy(self.metadata)

    def token(self):
        self.token_calls += 1
        if not self.connected:
            raise RuntimeError("not connected")
        return TOKEN


class AuthenticatedRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="wv-authenticated-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = self.root / "source"
        self.git("init", "-q", "-b", "main", str(self.fixture))
        (self.fixture / "app.txt").write_text("one\ntwo\n")
        self.git("-C", str(self.fixture), "add", ".")
        self.git("-C", str(self.fixture), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgSign=false", "commit", "-qm", "Private fixture")
        self.auth = FakeAuth()
        self.calls = []
        original = authenticated._run

        def offline_run(command, **kwargs):
            self.calls.append((list(command), dict(kwargs.get("environment", {}))))
            if "fetch" in command:
                position = command.index("fetch")
                command = command[:position] + ["-c", "protocol.file.allow=always"] + command[position:]
                command = [str(self.fixture) if value == URL + ".git" else value for value in command]
            return original(command, **kwargs)

        self.addCleanup(patch.stopall)
        patch.object(authenticated, "_run", side_effect=offline_run).start()

    def git(self, *args):
        return subprocess.run(["git", "-c", "core.hooksPath=" + os.devnull, *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    def collect(self, *, item=None, root=None, config=None, auth=None):
        return authenticated.collect_authenticated(item or ITEM, root or self.root / "github-repositories",
                                                   config or CONFIG, auth or self.auth)

    def cache(self, account=101, repository=42):
        name = hashlib.sha256(f"{account}:{repository}".encode()).hexdigest()
        return self.root / "github-repositories" / name

    def test_credentials_only_reach_fetch_environment_and_never_persist(self):
        with patch.dict(os.environ, {"GH_TOKEN": "unrelated-gh-token", "GITHUB_TOKEN": "unrelated-token",
                                     "GIT_CONFIG_COUNT": "9", "GIT_CONFIG_VALUE_0": "unrelated-header"}):
            result = self.collect(item=dict(ITEM, token=TOKEN, access_token=TOKEN))
        self.assertEqual(result["status"], "ok", result["errors"])
        self.assertEqual(result["history"]["commits"], 1)
        self.assertEqual(result["history"]["total_added"], 2)
        self.assertTrue(result["private"])
        self.assertEqual(result["source_kind"], "github")
        self.assertEqual(result["source_status"]["worktrees"], "not_requested")
        self.assertEqual(result["worktrees"], [])
        encoded = base64.b64encode(("x-access-token:" + TOKEN).encode()).decode()
        credential_calls = []
        for command, environment in self.calls:
            self.assertNotIn(TOKEN, " ".join(command))
            self.assertNotIn(encoded, " ".join(command))
            self.assertNotIn("GH_TOKEN", environment)
            self.assertNotIn("GITHUB_TOKEN", environment)
            if "GIT_CONFIG_VALUE_0" in environment:
                credential_calls.append((command, environment))
                self.assertIn("fetch", command)
                self.assertEqual(environment["GIT_CONFIG_COUNT"], "1")
                self.assertEqual(environment["GIT_CONFIG_KEY_0"], f"http.{URL}.git.extraHeader")
                self.assertEqual(environment["GIT_CONFIG_VALUE_0"], "Authorization: Basic " + encoded)
        self.assertEqual(len(credential_calls), 1)
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn("access_token", result)
        for path in self.cache().rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                self.assertNotIn(TOKEN.encode(), data)
                self.assertNotIn(encoded.encode(), data)
        marker = json.loads((self.cache() / "work-visibility-cache.json").read_text())
        self.assertEqual(marker, {"version": 1, "github_account_id": 101, "github_repository_id": 42})

    def test_scoped_fetch_header_is_effective_only_for_the_repository_url(self):
        self.assertEqual(self.collect()["status"], "ok")
        environment = next(env for command, env in self.calls if "fetch" in command)
        # This fixture-only config query proves real Git's URL precedence without
        # making any request. Production supplies the environment only to fetch.
        from git_metrics import _run
        code, out, _ = _run(["git", "-c", "http.extraHeader=", "config", "--get-urlmatch",
                             "http.extraHeader", URL + ".git"], environment=environment)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip().decode(), environment["GIT_CONFIG_VALUE_0"])
        _, other, _ = _run(["git", "-c", "http.extraHeader=", "config", "--get-urlmatch",
                            "http.extraHeader", "https://github.com/other/repo.git"], environment=environment)
        self.assertEqual(other.strip(), b"")

    def test_denied_or_replaced_repository_cannot_reuse_cached_private_history(self):
        self.assertEqual(self.collect()["status"], "ok")
        for mutation in ("denied", "replaced", "different-host"):
            with self.subTest(mutation=mutation):
                self.auth.error = RuntimeError("server reflected " + TOKEN) if mutation == "denied" else None
                self.auth.metadata = dict(METADATA, id=43) if mutation == "replaced" else dict(METADATA)
                if mutation == "different-host":
                    self.auth.metadata["html_url"] = "https://evil.invalid/fixture/repo"
                result = self.collect()
                self.assertEqual(result["status"], "error")
                self.assertIsNone(result["history"])
                self.assertIsNone(result["head"])
                self.assertNotIn(TOKEN, json.dumps(result))

    def test_account_identity_partitions_cache_and_blocks_cross_account_read(self):
        self.assertEqual(self.collect()["status"], "ok")
        other = FakeAuth(account=202)
        self.assertIsNone(self.collect(auth=other)["history"])
        result = self.collect(item=dict(ITEM, github_account_id=202), auth=other)
        self.assertEqual(result["status"], "ok", result["errors"])
        self.assertTrue(self.cache(101).is_dir())
        self.assertTrue(self.cache(202).is_dir())

    def test_disconnect_during_fetch_cancels_and_discards_result(self):
        original = authenticated.AuthenticatedGit.fetch
        def revoke(git, url, branch, token, cancel_check):
            self.auth.generation += 1
            self.auth.connected = False
            self.assertTrue(cancel_check())
            return original(git, url, branch, token, cancel_check)
        with patch.object(authenticated.AuthenticatedGit, "fetch", revoke):
            result = self.collect()
        self.assertIsNone(result["history"])
        self.assertEqual(result["status"], "error")

    def test_account_change_after_history_drops_measurements(self):
        original = authenticated._history
        def change(*args, **kwargs):
            history = original(*args, **kwargs)
            self.auth.generation += 1
            self.auth.account = 202
            return history
        with patch.object(authenticated, "_history", side_effect=change):
            result = self.collect()
        self.assertIsNone(result["history"])
        self.assertIsNone(result["head"])

    def test_expired_access_token_refreshes_before_initial_session_guard(self):
        from github_auth import GitHubAuth, API_ROOT, TOKEN_ENDPOINT
        from test_github_auth import Clock, Provider, CONFIG as APP_CONFIG, token_payload
        clock, provider = Clock(), Provider()
        provider.polls = [token_payload(expires=90)]
        provider.user = {"id": ITEM["github_account_id"], "login": "fixture"}
        def request(method, url, **kwargs):
            if url == API_ROOT + "/repositories/42":
                return dict(METADATA)
            return provider(method, url, **kwargs)
        auth = GitHubAuth(APP_CONFIG, request=request, clock=clock, wait=clock.wait)
        self.addCleanup(auth.close)
        auth.start()
        auth._thread.join(2)
        self.assertEqual(auth.status()["status"], "connected")
        clock.now += 91
        result = self.collect(auth=auth)
        self.assertEqual(result["status"], "ok", result["errors"])
        refreshes = [call for call in provider.calls if call[1] == TOKEN_ENDPOINT
                     and call[2].get("grant_type") == "refresh_token"]
        self.assertEqual(len(refreshes), 1)

    def test_unauthorized_installation_never_creates_cache(self):
        result = self.collect(item=dict(ITEM, installation_id=8))
        self.assertEqual(result["status"], "error")
        self.assertFalse((self.root / "github-repositories").exists())
        self.assertEqual(self.auth.token_calls, 1)

    def test_custom_cache_git_configuration_is_rejected_before_fetch(self):
        self.assertEqual(self.collect()["status"], "ok")
        self.git("config", "--file", str(self.cache() / "config"),
                 "http.https://github.com/.extraHeader", "unrelated stored header")
        self.calls.clear()
        result = self.collect()
        self.assertEqual(result["status"], "error")
        self.assertIsNone(result["history"])
        self.assertEqual(self.auth.token_calls, 3)
        self.assertFalse(any("fetch" in command for command, _ in self.calls))

    def test_partial_cache_is_not_reinitialized_before_configuration_validation(self):
        self.assertEqual(self.collect()["status"], "ok")
        (self.cache() / "HEAD").unlink()
        self.calls.clear()
        self.assertEqual(self.collect()["status"], "error")
        self.assertFalse(any("init" in command for command, _ in self.calls))
        self.assertEqual(self.auth.token_calls, 3)

    def test_existing_fetch_file_hardlink_is_rejected_before_writes(self):
        self.assertEqual(self.collect()["status"], "ok")
        protected = self.root / "protected.txt"
        protected.write_text("protected fixture bytes")
        fetch_head = self.cache() / "FETCH_HEAD"
        fetch_head.unlink()
        os.link(protected, fetch_head)
        self.calls.clear()
        result = self.collect()
        self.assertEqual(result["status"], "error")
        self.assertEqual(protected.read_text(), "protected fixture bytes")
        self.assertFalse(any("fetch" in command for command, _ in self.calls))
        self.assertEqual(self.auth.token_calls, 3)

    @unittest.skipUnless(os.name == "nt", "native Windows junction fixture")
    def test_nested_junction_is_rejected_without_newer_pathlib_helpers(self):
        self.assertEqual(self.collect()["status"], "ok")
        junction = self.cache() / "nested-escape"
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(self.fixture)],
                       check=True, capture_output=True)
        self.calls.clear()
        with patch.object(Path, "is_junction", return_value=False, create=True):
            result = self.collect()
        self.assertEqual(result["status"], "error")
        self.assertFalse(any("fetch" in command for command, _ in self.calls))
        self.assertEqual((self.fixture / "app.txt").read_text(), "one\ntwo\n")

    def test_raw_fetch_errors_are_not_published(self):
        original = authenticated._run
        def fail(command, **kwargs):
            if "fetch" in command:
                raise RuntimeError("Git/server reflected " + TOKEN + " " + kwargs["environment"]["GIT_CONFIG_VALUE_0"])
            return original(command, **kwargs)
        with patch.object(authenticated, "_run", side_effect=fail):
            result = self.collect()
        self.assertIsNone(result["history"])
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertNotIn("Authorization", json.dumps(result))
        self.assertNotIn("Git/server reflected", json.dumps(result))

    def test_cache_root_cannot_overlap_registered_worktree_or_ancestor(self):
        linked = self.root / "linked"
        self.git("-C", str(self.fixture), "worktree", "add", "-q", "-b", "linked", str(linked))
        config = dict(CONFIG, repositories=[{"path": str(self.fixture)}])
        for target in (linked / "private-cache", self.fixture / ".git" / "private-cache", self.root):
            with self.subTest(target=str(target)):
                before = sorted(str(path) for path in self.root.rglob("*"))
                result = self.collect(root=target, config=config)
                self.assertEqual(result["status"], "error")
                self.assertIn("overlaps", result["errors"][0])
                self.assertEqual(before, sorted(str(path) for path in self.root.rglob("*")))

    def test_unresolved_local_identity_blocks_private_cache_writes(self):
        result = self.collect(config=dict(CONFIG, repositories=[{"path": str(self.root / "missing")}]))
        self.assertEqual(result["status"], "error")
        self.assertFalse((self.root / "github-repositories").exists())

    @unittest.skipIf(os.name == "nt", "POSIX link fixture")
    def test_cache_root_and_marker_links_are_rejected(self):
        linked = self.root / "linked-cache"
        linked.symlink_to(self.fixture, target_is_directory=True)
        self.assertEqual(self.collect(root=linked)["status"], "error")
        self.assertEqual(self.collect()["status"], "ok")
        marker = self.cache() / "work-visibility-cache.json"
        protected = self.root / "protected.json"
        protected.write_bytes(marker.read_bytes())
        marker.unlink()
        marker.symlink_to(protected)
        original = protected.read_bytes()
        self.assertEqual(self.collect()["status"], "error")
        self.assertEqual(protected.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
