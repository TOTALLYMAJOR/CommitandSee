"""Integration checks for the collector using disposable, real Git repositories.

Run with: python3 -m unittest -v test_git_metrics.py
No network access or existing user checkout is needed.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from git_metrics import collect_repository


@unittest.skipUnless(shutil.which("git"), "Git is required")
class GitMetricsIntegrationTests(unittest.TestCase):
    """Each test owns every repository, ref, file, and hook that it changes."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="git-dashboard-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repository"
        self.repo.mkdir()
        self.env_patch = mock.patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Dashboard Test",
            "GIT_AUTHOR_EMAIL": "dashboard-test@example.invalid",
            "GIT_COMMITTER_NAME": "Dashboard Test",
            "GIT_COMMITTER_EMAIL": "dashboard-test@example.invalid",
        })
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.git("init", "-b", "main", ".")
        self.git("config", "commit.gpgSign", "false")
        self.git("config", "tag.gpgSign", "false")
        self.git("config", "core.autocrlf", "false")
        self.base_time = (datetime.now(timezone.utc) - timedelta(days=2)).replace(
            hour=0, minute=30, second=0, microsecond=0
        )
        self.commit_count = 0

    def test_chart_events_reconcile_and_keep_safe_github_origin(self):
        self.git("remote", "add", "origin", "git@github.com:octocat/example.git")
        self.write("story.txt", "one\ntwo\n")
        self.git("add", "story.txt")
        self.git("commit", "-m", "Story")
        row = collect_repository(self.repo)
        self.assertEqual(row["github_url"], "https://github.com/octocat/example")
        event, = row["history"]["events"]
        self.assertEqual(event["sha"], self.git("rev-parse", "HEAD"))
        self.assertEqual(event["added"], row["history"]["total_added"])
        self.assertEqual(event["added"], 2)
        self.git("remote", "set-url", "origin", "https://secret@github.com/octocat/example")
        self.assertIsNone(collect_repository(self.repo)["github_url"])

    def git(self, *arguments, cwd=None, env=None, check=True):
        result = subprocess.run(
            ["git", *map(str, arguments)],
            cwd=cwd or self.repo,
            env={**os.environ, **(env or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        if check and result.returncode:
            self.fail(f"Fixture Git command {arguments!r} failed: {result.stderr}")
        return result.stdout.strip()

    def write(self, name, content, *, repo=None):
        path = (repo or self.repo) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="")
        return path

    def commit(self, subject, *, repo=None):
        stamp = (self.base_time + timedelta(minutes=self.commit_count)).isoformat()
        self.commit_count += 1
        self.git("add", "--all", cwd=repo)
        self.git(
            "commit", "-m", subject, cwd=repo,
            env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
        )
        return self.git("rev-parse", "HEAD", cwd=repo)

    def metrics(self, path=None, **overrides):
        options = {"days": 30, "timezone": "UTC", **overrides}
        return collect_repository(str(path or self.repo), **options)

    def worktree(self, result, path=None):
        wanted = (path or self.repo).resolve()
        return next(w for w in result["worktrees"] if Path(w["path"]).resolve() == wanted)

    def branch(self, result, name):
        return next(b for b in result["branches"] if b["name"] == name)

    def assert_delta(self, worktree, layer, added, deleted, binary=0):
        self.assertIsNotNone(worktree["loc"], worktree.get("errors"))
        delta = worktree["loc"][layer]
        self.assertIsNotNone(delta, worktree.get("errors"))
        self.assertEqual(delta["added"], added)
        self.assertEqual(delta["deleted"], deleted)
        self.assertEqual(delta["binary_files"], binary)

    def test_root_commit_and_later_diff_have_exact_churn_and_timezone(self):
        self.write("app.py", "alpha\nbeta\n")
        self.commit("root")
        self.write("app.py", "alpha\ngamma\ndelta\n")
        self.commit("change")
        try:
            central = ZoneInfo("America/Chicago")
        except ZoneInfoNotFoundError:
            self.skipTest("Timezone database does not include America/Chicago")
        result = self.metrics(timezone="America/Chicago")
        history = result["history"]
        self.assertEqual(history["commits"], 2)
        self.assertEqual(history["total_added"], 4)
        self.assertEqual(history["total_deleted"], 1)
        self.assertEqual(history["binary_changes"], 0)
        self.assertEqual(sum(d["commits"] for d in history["daily"]), 2)
        self.assertEqual(sum(d["added"] for d in history["weekly"]), 4)
        self.assertEqual(sum(d["deleted"] for d in history["weekly"]), 1)
        active = [d["date"] for d in history["daily"] if d["commits"]]
        self.assertEqual(active, [self.base_time.astimezone(central).date().isoformat()])
        self.assertFalse(history["truncated"])
        self.assertFalse(history["shallow"])

    def test_selected_ref_excludes_unmerged_branch_and_merge_commit_churn(self):
        self.write("root.txt", "root\n")
        self.commit("root")
        self.git("checkout", "-b", "feature")
        self.write("feature.txt", "one\ntwo\n")
        feature = self.commit("feature work")
        self.git("checkout", "main")
        self.write("main.txt", "one\ntwo\nthree\n")
        self.commit("main work")
        self.git("merge", "--no-ff", "feature", "-m", "merge feature")
        self.git("checkout", "-b", "parked")
        self.write("parked.txt", "parked\n" * 8)
        parked = self.commit("not on selected ref")
        self.git("checkout", "main")
        result = self.metrics()
        history = result["history"]
        self.assertEqual(history["commits"], 3)
        self.assertEqual(history["total_added"], 6)
        self.assertEqual(history["total_deleted"], 0)
        observed = {c["sha"] for c in history["recent"]}
        self.assertIn(feature, observed)
        self.assertNotIn(parked, observed)
        self.assertFalse(self.branch(result, "parked")["merged_into_ref"])
        self.assertTrue(self.branch(result, "feature")["merged_into_ref"])

    def test_staged_change_reversed_in_worktree_has_zero_net_delta(self):
        self.write("app.py", "original\n")
        self.commit("baseline")
        self.write("app.py", "replacement\n")
        self.git("add", "app.py")
        self.write("app.py", "original\n")
        index = self.repo / ".git" / "index"
        index_before = index.read_bytes()
        index_mtime = index.stat().st_mtime_ns
        worktree = self.worktree(self.metrics())
        self.assertTrue(worktree["dirty"])
        self.assertEqual(worktree["staged"], 1)
        self.assertEqual(worktree["unstaged"], 1)
        self.assert_delta(worktree, "staged", 1, 1)
        self.assert_delta(worktree, "unstaged", 1, 1)
        self.assert_delta(worktree, "net", 0, 0)
        self.assertEqual(index.read_bytes(), index_before)
        self.assertEqual(index.stat().st_mtime_ns, index_mtime)

    def test_untracked_text_and_binary_changes_are_separate_from_line_counts(self):
        self.write("app.py", "source\n")
        self.write("image.bin", b"\x00\x01\x02")
        self.commit("text and binary baseline")
        self.write("image.bin", b"\x00\x03\x04\x05")
        self.write("new.txt", "untracked\n" * 3)
        result = self.metrics()
        worktree = self.worktree(result)
        self.assertEqual(result["history"]["total_added"], 1)
        self.assertEqual(result["history"]["binary_changes"], 1)
        self.assertEqual(worktree["untracked"], 1)
        self.assertEqual(worktree["unstaged"], 1)
        self.assert_delta(worktree, "net", 0, 0, binary=1)

    @unittest.skipIf(os.name == "nt", "Windows disallows these newline/tab filenames")
    def test_rename_and_tab_newline_paths_are_preserved(self):
        old = "old\tname\nfile.txt"
        new = "new\tname\nfile.txt"
        self.write(old, "alpha\nbeta\n")
        self.commit("original path")
        (self.repo / old).rename(self.repo / new)
        self.git("add", "--all")
        self.write(new, "alpha\nbeta\ngamma\n")
        worktree = self.worktree(self.metrics())
        paths = {f["path"] for f in worktree["files"]}
        self.assertIn(new, paths)
        self.assertEqual(worktree["staged"], 1)
        self.assertEqual(worktree["unstaged"], 1)
        self.assert_delta(worktree, "staged", 0, 0)
        self.assert_delta(worktree, "unstaged", 1, 0)
        self.commit("rename with edit")
        history = self.metrics()["history"]
        self.assertEqual(history["commits"], 2)
        self.assertEqual(history["total_added"], 3)
        self.assertEqual(history["total_deleted"], 0)

    def test_registered_worktrees_and_shared_stash_are_visible(self):
        self.write("app.py", "baseline\n")
        self.commit("baseline")
        linked = self.root / "linked-worktree"
        self.git("worktree", "add", "-b", "task", str(linked))
        self.write("app.py", "task edit\n", repo=linked)
        self.write("app.py", "parked edit\n")
        self.git("stash", "push", "-m", "parked work")
        result = self.metrics()
        self.assertEqual(len(result["worktrees"]), 2)
        self.assertFalse(self.worktree(result)["dirty"])
        self.assertTrue(self.worktree(result, linked)["dirty"])
        self.assertEqual(len(result["stashes"]), 1)
        self.assertIn("parked work", result["stashes"][0]["subject"])
        linked_result = self.metrics(linked)
        self.assertEqual(result["id"], linked_result["id"])

    def test_branch_ancestry_and_ahead_of_cached_upstream(self):
        self.write("app.py", "root\n")
        self.commit("root")
        remote = self.root / "remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "main")
        self.git("checkout", "-b", "feature")
        self.write("feature.py", "feature\n")
        self.commit("local feature")
        self.git("branch", "--set-upstream-to", "origin/main", "feature")
        self.git("branch", "isolated")
        result = self.metrics(ref="main")
        feature = self.branch(result, "feature")
        self.assertEqual(feature["upstream"], "origin/main")
        self.assertEqual(feature["ahead"], 1)
        self.assertEqual(feature["behind"], 0)
        self.assertFalse(feature["merged_into_ref"])
        self.assertTrue(self.branch(result, "main")["merged_into_ref"])
        isolated = self.branch(result, "isolated")
        self.assertFalse(isolated["upstream"])
        self.assertIsNone(isolated["ahead"])
        self.assertIsNone(isolated["behind"])

    def test_divergent_cached_upstream_reports_both_sides(self):
        self.write("app.py", "root\n")
        self.commit("root")
        remote = self.root / "remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("checkout", "-b", "remote-side")
        self.write("remote.txt", "remote\n")
        remote_head = self.commit("remote side")
        self.git("update-ref", "refs/remotes/origin/main", remote_head)
        self.git("checkout", "main")
        self.write("local.txt", "local\n")
        self.commit("local side")
        self.git("branch", "--set-upstream-to", "origin/main", "main")
        branch = self.branch(self.metrics(), "main")
        self.assertEqual(branch["ahead"], 1)
        self.assertEqual(branch["behind"], 1)

    def test_missing_upstream_stays_unknown_instead_of_zero(self):
        self.write("app.py", "root\n")
        self.commit("root")
        remote = self.root / "remote.git"
        self.git("init", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-u", "origin", "main")
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        branch = self.branch(self.metrics(), "main")
        self.assertEqual(branch["upstream"], "origin/main")
        self.assertIsNone(branch["ahead"])
        self.assertIsNone(branch["behind"])

    def test_history_limit_and_shallow_checkout_report_incomplete_coverage(self):
        for number in range(3):
            self.write("app.py", "line\n" * (number + 1))
            self.commit(f"change {number}")
        limited = self.metrics(max_commits=1)
        self.assertTrue(limited["history"]["truncated"])
        self.assertEqual(limited["history"]["commits"], 1)
        shallow = self.root / "shallow"
        self.git("clone", "--depth", "1", self.repo.as_uri(), str(shallow))
        result = self.metrics(shallow)
        self.assertTrue(result["history"]["shallow"])
        self.assertEqual(result["history"]["commits"], 1)

    def test_unborn_repository_still_reports_untracked_work(self):
        self.write("first.py", "new work\n")
        result = self.metrics()
        self.assertIsNone(result["head"])
        self.assertEqual(result["history"]["commits"], 0)
        worktree = self.worktree(result)
        self.assertTrue(worktree["dirty"])
        self.assertEqual(worktree["untracked"], 1)

    def test_missing_repository_and_invalid_ref_are_not_zero_activity(self):
        missing = self.metrics(self.root / "absent")
        self.assertEqual(missing["status"], "error")
        self.assertTrue(missing["errors"])
        history = missing.get("history")
        self.assertTrue(history is None or history.get("commits") is None)
        self.write("app.py", "baseline\n")
        self.commit("baseline")
        self.write("app.py", "current edit\n")
        invalid = self.metrics(ref="no-such-reference")
        self.assertIn(invalid["status"], {"partial", "error"})
        history = invalid.get("history")
        self.assertTrue(history is None or history.get("commits") is None)
        self.assertTrue(self.worktree(invalid)["dirty"])

    @unittest.skipIf(os.name == "nt", "Tripwire hook uses a POSIX executable script")
    def test_observation_does_not_write_index_refs_or_execute_fsmonitor(self):
        self.write("app.py", "baseline\n")
        self.commit("baseline")
        self.write("app.py", "dirty\n")
        marker = self.root / "fsmonitor-executed"
        hook = self.root / "fsmonitor.py"
        hook.write_text(
            "#!" + sys.executable + "\n"
            "from pathlib import Path\nimport sys\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
            "sys.stdout.buffer.write(b'test-token\\0')\n",
            encoding="utf-8",
        )
        hook.chmod(0o700)
        self.git("config", "core.fsmonitor", str(hook))
        self.git("status", "--porcelain")
        self.assertTrue(marker.exists(), "Fixture hook did not execute in the control run")
        marker.unlink()
        index = self.repo / ".git" / "index"
        index_before = index.read_bytes()
        index_mtime = index.stat().st_mtime_ns
        config = self.repo / ".git" / "config"
        config_before = config.read_bytes()
        refs_before = self.git("show-ref")
        result = self.metrics()
        self.assertTrue(self.worktree(result)["dirty"])
        self.assertFalse(marker.exists(), "Collector executed the repository's fsmonitor")
        self.assertEqual(index.read_bytes(), index_before)
        self.assertEqual(index.stat().st_mtime_ns, index_mtime)
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(self.git("show-ref"), refs_before)

    @unittest.skipIf(os.name == "nt", "Filter fixture uses POSIX shell quoting")
    def test_executable_content_filter_is_not_run_and_scan_is_qualified(self):
        self.write("app.txt", "baseline\n")
        self.commit("baseline")
        marker = self.root / "filter-executed"
        script = self.root / "clean-filter.py"
        script.write_text(
            "from pathlib import Path\nimport sys\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        self.write(".gitattributes", "*.txt filter=tripwire\n")
        self.git(
            "config", "filter.tripwire.clean",
            shlex.quote(sys.executable) + " " + shlex.quote(str(script)),
        )
        self.write("app.txt", "dirty\n")
        result = self.metrics()
        worktree = self.worktree(result)
        self.assertFalse(marker.exists(), "Collector executed a configured clean filter")
        self.assertIn(worktree["status"], {"partial", "error"})
        self.assertTrue(worktree["errors"])
        self.assertTrue(worktree.get("loc") is None or worktree["loc"].get("net") is None)
        self.assertIsNone(worktree["dirty"], "Unavailable status must not be called clean")

    def test_metric_exclusions_do_not_hide_dirty_files(self):
        self.write("app.py", "source\n")
        self.write("generated/output.json", "generated\n" * 3)
        self.commit("source and generated baseline")
        self.write("app.py", "source\nchange\n")
        self.write("generated/output.json", "generated\n" * 4)
        result = self.metrics(exclude_globs=["generated/**"])
        self.assertEqual(result["history"]["total_added"], 1)
        worktree = self.worktree(result)
        self.assertEqual(worktree["unstaged"], 2)
        self.assertEqual(
            {f["path"] for f in worktree["files"]},
            {"app.py", "generated/output.json"},
        )
        self.assert_delta(worktree, "net", 1, 0)

    @unittest.skipIf(os.name == "nt", "Filter fixture uses POSIX shell quoting")
    def test_submodule_filter_is_not_executed_and_nested_coverage_is_unknown(self):
        self.write("app.py", "parent\n")
        self.commit("parent baseline")
        source = self.root / "child-source"
        source.mkdir()
        self.git("init", "-b", "main", ".", cwd=source)
        self.write("child.txt", "child baseline\n", repo=source)
        self.commit("child baseline", repo=source)
        self.git(
            "-c", "protocol.file.allow=always", "submodule", "add",
            str(source), "vendor/child",
        )
        self.commit("add submodule")
        child = self.repo / "vendor" / "child"
        marker = self.root / "child-filter-executed"
        script = self.root / "child-clean-filter.py"
        script.write_text(
            "from pathlib import Path\nimport sys\n"
            f"Path({str(marker)!r}).write_text('executed')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        self.write(".gitattributes", "*.txt filter=tripwire\n", repo=child)
        self.git(
            "config", "filter.tripwire.clean",
            shlex.quote(sys.executable) + " " + shlex.quote(str(script)),
            cwd=child,
        )
        self.write("child.txt", "changed child content\n", repo=child)
        worktree = self.worktree(self.metrics())
        self.assertFalse(marker.exists(), "Collector executed a nested clean filter")
        self.assertIn(worktree["status"], {"partial", "error"})
        self.assertIsNone(worktree["dirty"], "Unobserved child contents must not be called clean")
        self.assertIn("submodule", " ".join(worktree["errors"]).lower())


if __name__ == "__main__":
    unittest.main()
