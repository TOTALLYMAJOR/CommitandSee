"""Local registry boundary and progressive startup regression tests."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import git_dashboard as app

class RepositoryUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        self.config = dict(app.DEFAULTS, repositories=[])
        self.path = self.root / 'config.json'
        self.path.write_text(json.dumps(dict(self.config, selection={'preserve': True})))
        self.state = app.LiveState(app.DashboardCollector(self.config), self.path)

    def test_startup_is_nonblocking_and_pending_is_unknown(self):
        self.config['repositories'] = [dict(path=str(self.repo), name='Repo', product='App', ref='HEAD', exclude_globs=[])]
        with patch.object(app.DashboardCollector, 'collect', side_effect=AssertionError('synchronous scan')):
            state = app.LiveState(app.DashboardCollector(self.config), self.path)
        row = state.read()['repositories'][0]
        self.assertIsNone(row['history'])
        self.assertEqual(row['source_status']['worktrees'], 'pending')

    def test_later_scan_keeps_prior_observation_timestamp(self):
        item = self.state.add_repository({'path': str(self.repo)})
        snapshot = self.state.read()
        snapshot['repositories'][0].update(status='ok', collected_at='2026-11-05T00:00:00Z')
        self.state.publish(snapshot)
        snapshot['repositories'] = []
        self.state.publish(snapshot)
        row = self.state.read()['repositories'][0]
        self.assertEqual(row['status'], 'ok')
        self.assertEqual(row['collected_at'], '2026-11-05T00:00:00Z')

    def test_linked_worktree_is_rejected_as_duplicate(self):
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'Fixture'], check=True)
        linked = self.root / 'linked'
        subprocess.run(['git', '-C', str(self.repo), '-c', 'core.hooksPath=/dev/null', 'worktree', 'add', '-q', '-b', 'fixture-linked', str(linked)], check=True)
        self.state.add_repository({'path': str(self.repo)})
        with self.assertRaises(app.RepositoryError) as raised:
            self.state.add_repository({'path': str(linked)})
        self.assertEqual(raised.exception.code, 'duplicate')

    def test_add_persists_metadata_and_does_not_touch_git(self):
        before = {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        original = self.path.read_bytes()
        item = self.state.add_repository({'path': str(self.repo), 'name': '<My repo>', 'product': 'App'})
        saved = json.loads(self.path.read_text())
        self.assertEqual(saved['selection'], {'preserve': True})
        self.assertEqual(self.path.read_bytes(), original)
        args = argparse.Namespace(command='serve', config=str(self.path), repo=[], ref=None)
        self.assertEqual(app.read_config(args)['repositories'][0], item)
        self.assertEqual(self.state.read()['repositories'][0]['status'], 'pending')
        self.assertTrue(self.state.wake.is_set())
        after = {str(p.relative_to(self.repo)): p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(app.RepositoryError) as raised:
            self.state.add_repository({'path': str(self.repo / '.git' / '..')})
        self.assertEqual(raised.exception.status, 409)

    def test_external_config_change_and_failed_write_preserve_memory(self):
        self.path.write_text('{}')
        with self.assertRaises(app.RepositoryError) as raised:
            self.state.add_repository({'path': str(self.repo)})
        self.assertEqual(raised.exception.code, 'config_changed')
        self.state.config_digest = self.path.read_bytes()
        with patch.object(self.state.registry, 'update', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.state.add_repository({'path': str(self.repo)})
        self.assertEqual(self.config['repositories'], [])

    def test_reject_bad_paths_and_config_inside_checkout(self):
        for body in ({'path': 'relative'}, {'path': str(self.root)}, {'path': str(self.repo), 'url': 'bad'}):
            with self.assertRaises(app.RepositoryError): self.state.add_repository(body)
        inside = self.repo / 'monitor.json'
        inside.write_text('{}')
        state = app.LiveState(app.DashboardCollector(self.config), inside)
        with self.assertRaises(app.RepositoryError) as raised: state.add_repository({'path': str(self.repo)})
        self.assertEqual(raised.exception.code, 'unsafe_config')

    def test_http_origin_validation_and_creation(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(self.state))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def post(body, origin):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            connection.request('POST', '/api/repositories', body, {'Content-Type': 'application/json', 'Origin': origin})
            response = connection.getresponse()
            status, data = response.status, response.read()
            connection.close()
            return status, data
        origin = f'http://127.0.0.1:{server.server_port}'
        body = json.dumps({'path': str(self.repo)})
        self.assertEqual(post(body, 'https://attacker.example')[0], 403)
        self.assertEqual(post('{', origin)[0], 400)
        self.assertEqual(post('x' * 8193, origin)[0], 400)
        self.assertEqual(post(body, origin)[0], 201)
        self.assertEqual(post(body, origin)[0], 409)

if __name__ == '__main__': unittest.main()
