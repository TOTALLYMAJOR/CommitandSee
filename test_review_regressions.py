"""Regression tests from the review of git-activity-dashboard(1).zip.

Copy this file alongside git_dashboard.py, git_metrics.py, and test_git_metrics.py.
Run: python3 -m unittest -v test_review_regressions.py

These tests assert the desired behavior. All five fail on the reviewed version.
All repositories and harmless marker scripts are created in temporary directories.
No network, credentials, or pre-existing user repositories are used.
"""
from __future__ import annotations

from datetime import timedelta
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import git_dashboard as dashboard
import test_git_metrics as fixtures


@unittest.skipUnless(shutil.which("git"), "Git is required")
class GitSafetyAndMetricsRegressions(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.GitMetricsIntegrationTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    @unittest.skipIf(os.name == "nt", "The harmless verifier fixture uses a POSIX shell")
    def test_signature_display_must_not_execute_a_configured_program(self) -> None:
        f = self.fixture
        f.write("app.txt", "baseline\n")
        parent = f.commit("baseline")
        tree = f.git("rev-parse", "HEAD^{tree}")
        marker = f.root / "signature-program-executed"
        program = f.root / "signature-program.sh"
        program.write_text(
            "#!/bin/sh\nprintf executed > " + shlex.quote(str(marker)) + "\nexit 1\n",
            encoding="utf-8",
        )
        program.chmod(0o755)

        # Signature verification is triggered by this test-only signature header.
        # The configured verifier merely writes a marker inside this fixture.
        epoch = int(f.base_time.timestamp()) + 60
        commit = (
            f"tree {tree}\nparent {parent}\n"
            f"author Review <review@example.invalid> {epoch} +0000\n"
            f"committer Review <review@example.invalid> {epoch} +0000\n"
            "gpgsig -----BEGIN PGP SIGNATURE-----\n"
            " \n"
            " ZHVtbXk=\n"
            " -----END PGP SIGNATURE-----\n\n"
            "test-only signed commit\n"
        )
        completed = subprocess.run(
            ["git", "hash-object", "-t", "commit", "-w", "--stdin"],
            cwd=f.repo, input=commit, text=True, capture_output=True,
            check=True, timeout=20,
        )
        f.git("update-ref", "refs/heads/main", completed.stdout.strip())
        f.git("config", "gpg.program", str(program))
        f.git("config", "log.showSignature", "true")

        result = f.metrics()
        self.assertFalse(
            marker.exists(),
            f"Observation executed the configured signature verifier; status={result['status']}",
        )

    @unittest.skipIf(os.name == "nt", "The harmless clean-filter fixture uses a POSIX shell")
    def test_git_config_environment_must_not_bypass_the_filter_guard(self) -> None:
        f = self.fixture
        f.write("app.txt", "baseline\n")
        f.commit("baseline")
        marker = f.root / "clean-filter-executed"
        program = f.root / "clean-filter.sh"
        program.write_text(
            "#!/bin/sh\nprintf executed > " + shlex.quote(str(marker)) + "\ncat\n",
            encoding="utf-8",
        )
        program.chmod(0o755)
        f.write(".gitattributes", "*.txt filter=review\n")
        f.git("config", "filter.review.clean", str(program))
        f.write("app.txt", "changed\n")

        # Control: the ordinary guard correctly refuses this working-tree scan.
        f.metrics()
        self.assertFalse(marker.exists(), "The control scan unexpectedly ran a filter")

        with mock.patch.dict(os.environ, {"GIT_CONFIG": os.devnull}):
            result = f.metrics()
        self.assertFalse(
            marker.exists(),
            f"GIT_CONFIG bypassed filter detection; worktree status={result['worktrees'][0]['status']}",
        )

    def test_root_commit_churn_is_independent_of_log_showroot(self) -> None:
        f = self.fixture
        f.write("app.txt", "one\ntwo\nthree\n")
        f.commit("root")
        baseline = f.metrics()
        self.assertEqual(baseline["history"]["total_added"], 3)
        f.git("config", "log.showRoot", "false")

        result = f.metrics()
        self.assertEqual(
            result["history"]["total_added"], 3,
            "A display preference silently suppressed the root commit's additions",
        )

    def test_shallow_boundary_does_not_invent_recent_line_additions(self) -> None:
        f = self.fixture
        recent_time = f.base_time
        f.base_time = recent_time - timedelta(days=70)
        f.write("app.txt", "old baseline\n" * 100)
        f.commit("baseline outside the history window")
        f.base_time = recent_time
        f.write("app.txt", "old baseline\n" * 100 + "recent addition\n")
        f.commit("one recent added line")
        full = f.metrics(days=30)
        self.assertEqual(full["history"]["total_added"], 1)

        shallow_path = f.root / "shallow"
        f.git("clone", "--depth", "1", f.repo.as_uri(), str(shallow_path))
        result = f.metrics(shallow_path, days=30)
        history = result.get("history")
        # Explicitly unavailable churn is preferable to an invented lower bound.
        actual = None if history is None else history.get("total_added")
        self.assertTrue(
            actual is None or actual <= full["history"]["total_added"],
            f"Shallow clone reported {actual} additions; full history proves only 1",
        )


class SavedStateRegressions(unittest.TestCase):
    def test_wrong_top_level_state_type_is_reported_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "observations.json"
            state.write_text(json.dumps([]), encoding="utf-8")
            try:
                tracker = dashboard.ObservationTracker(state)
            except Exception as exc:
                self.fail(
                    "Invalid state should produce a recoverable history warning, "
                    f"not {type(exc).__name__}: {exc}"
                )
            self.assertEqual(tracker.states, {})
            self.assertIsNotNone(tracker.error)


if __name__ == "__main__":
    unittest.main()
