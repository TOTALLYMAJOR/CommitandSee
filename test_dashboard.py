"""Tests of configuration, persistence, export and loopback delivery."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

import git_dashboard as dashboard


class CommitPullTests(unittest.TestCase):
    def test_lookup_only_accepts_observed_commit_and_returns_safe_link_fields(self):
        sha = "a" * 40
        state = Mock()
        state.read.return_value = {"repositories": [
            {"id": "local", "github_url": "https://github.com/octocat/example",
             "history": {"events": [{"sha": sha}]}}]}
        with patch("git_dashboard._request_json", return_value=[
                {"number": 5, "title": "Example", "html_url": "https://elsewhere.invalid"}]) as api:
            with self.assertRaises(dashboard.RepositoryError):
                dashboard.LiveState.commit_pulls(state, {"repository": "local", "sha": "b" * 40})
            api.assert_not_called()
            result = dashboard.LiveState.commit_pulls(state, {"repository": "local", "sha": sha})
            self.assertEqual(result, {"pulls": [{"number": 5, "title": "Example"}], "limited": False})
            api.assert_called_once_with("GET", f"https://api.github.com/repos/octocat/example/commits/{sha}/pulls?per_page=100")

    def test_private_lookup_uses_only_selected_repository_session(self):
        from contextlib import nullcontext
        from github_auth import GitHubAuthError
        sha = "f" * 40
        state = Mock()
        url = "https://github.com/octocat/example"
        state.read.return_value = {"github_generation": 4, "repositories": [
            {"id": "repo", "url": url, "history": {"events": [{"sha": sha}]},
             "source_kind": "github", "github_generation": 4, "github_account_id": 12}]}
        state.auth.session_guard.return_value = nullcontext()
        state.auth.request_json.return_value = []
        with patch("git_dashboard._request_json") as anonymous:
            self.assertEqual(dashboard.LiveState.commit_pulls(state, {"repository": "repo", "sha": sha})["pulls"], [])
            anonymous.assert_not_called()
            state.auth.request_json.assert_called_once_with(
                f"/repos/octocat/example/commits/{sha}/pulls?per_page=100", expected_session=(4, 12))
            state.auth.session_guard.side_effect = GitHubAuthError("session_changed", "Signed out.", 409)
            with self.assertRaises(GitHubAuthError):
                dashboard.LiveState.commit_pulls(state, {"repository": "repo", "sha": sha})



class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)

    def test_config_relative_paths_and_cli_overrides(self):
        config = self.path / 'config.json'
        config.write_text(json.dumps({'days': 30, 'repositories': [{'path': 'repo', 'product': 'App'}]}))
        args = argparse.Namespace(config=str(config), repo=[], ref='main', days=14,
                                  interval=10, timezone=None, max_commits=None, stale_days=None)
        actual = dashboard.read_config(args)
        self.assertEqual(actual['repositories'][0]['path'], str(self.path / 'repo'))
        self.assertEqual(actual['repositories'][0]['ref'], 'main')
        self.assertEqual(actual['days'], 14)
        self.assertEqual(actual['refresh_seconds'], 10)
        args.interval = 0
        with self.assertRaises(ValueError): dashboard.read_config(args)

    def test_safe_html_export_and_literal_paths(self):
        data = {'title': '</script><script>window.pwned=true</script>', 'path': 'a<&\nname'}
        html = dashboard.render_html(data)
        self.assertNotIn(data['title'], html)
        self.assertIn('\\u003c/script\\u003e', html)
        self.assertNotIn('__GIT_DASHBOARD_DATA__', html)

    def test_observed_dirty_age_survives_restart_and_gap_is_explicit(self):
        state = self.path / 'observations.json'
        repo = {'id': 'one', 'collected_at': '2026-11-05T10:00:00+00:00',
                'worktrees': [{'path': '/demo', 'status': 'ok', 'dirty': True, 'fingerprint': 'a'}]}
        tracker = dashboard.ObservationTracker(state)
        tracker.annotate(repo, 30)
        tracker.save()
        tracker = dashboard.ObservationTracker(state)
        repo['collected_at'] = '2026-11-06T10:00:00+00:00'
        tracker.annotate(repo, 30)
        tree = repo['worktrees'][0]
        self.assertEqual(tree['first_seen_dirty_at'], '2026-11-05T10:00:00+00:00')
        self.assertEqual(tree['observation_gap_seconds'], 86400)
        tree.update(status='error', dirty=None)
        tracker.annotate(repo, 30)
        self.assertIsNotNone(tree['first_seen_dirty_at'])
        tree.update(status='ok', dirty=False, fingerprint='b')
        tracker.annotate(repo, 30)
        self.assertIsNone(tree['first_seen_dirty_at'])

    def test_shared_common_directory_is_counted_once_and_partial_cache_is_retained(self):
        config = dict(dashboard.DEFAULTS)
        config['repositories'] = [dict(path='/a', name='A', product='P1', ref='main', exclude_globs=[]),
                                  dict(path='/b', name='B', product='P2', ref='main', exclude_globs=[])]
        def fake(path, *, include_history, **kwargs):
            return {'id': 'same', 'name': kwargs['name'], 'path': path, 'common_dir': '/common', 'head': 'abc',
                    'ref': 'main', 'status': 'partial' if include_history else 'ok', 'errors': [], 'warnings': [],
                    'collected_at': dashboard.utc_now(), 'source_status': {'history': 'partial' if include_history else 'not_requested'},
                    'history': {'truncated': True, 'shallow': False, 'timezone': 'UTC'} if include_history else None,
                    'worktrees': [], 'branches': [], 'stashes': []}
        with patch.object(dashboard, 'collect_repository', side_effect=fake) as collect:
            collector = dashboard.DashboardCollector(config)
            first = collector.collect()
            second = collector.collect()
            self.assertEqual(len(first['repositories']), 1)
            self.assertEqual(first['repositories'][0]['products'], ['P1', 'P2'])
            self.assertEqual(second['repositories'][0]['source_status']['history'], 'partial')
            self.assertEqual(second['repositories'][0]['status'], 'partial')
            self.assertEqual(second['timezone'], 'UTC')
            self.assertEqual(sum(c.kwargs['include_history'] for c in collect.call_args_list), 1)

    def test_loopback_server_serves_snapshot_but_not_files_or_other_hosts(self):
        class State:
            def read(self):
                return {'schema_version': 1, 'title': 'test', 'live': True, 'repositories': []}
        server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.make_handler(State()))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=3)
            connection.request('GET', '/api/snapshot')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['schema_version'], 1)
            connection.request('GET', '/../../etc/passwd')
            response = connection.getresponse()
            self.assertEqual(response.status, 404)
            response.read()
            connection.request('GET', '/api/snapshot', headers={'Host': 'attacker.example'})
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
