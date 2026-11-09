"""Local inspection authorization, lifetime, and loopback boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import git_dashboard as app


class LocalInsightsAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repository'
        self.repo.mkdir()
        self.config = dict(app.DEFAULTS, repositories=[{'path': str(self.repo), 'exclude_globs': ['private/**']}])
        self.collector = app.DashboardCollector(self.config)
        self.state = app.LiveState(self.collector)
        self.addCleanup(self.state.auth.close)
        self.row = {'id': 'fixture-id', 'path': str(self.repo), 'common_dir': str(self.repo / '.git'),
                    'status': 'ok', 'history': None, 'exclude_globs': ['private/**']}
        with self.state.lock:
            self.state.snapshot['repositories'] = [copy.deepcopy(self.row)]
        self.body = {'repository': 'fixture-id', 'source': 'source-id', 'target': 'target-id'}

    def test_registered_path_only_and_exclusions_are_propagated(self):
        result = {'files': [{'path': 'example.txt', 'explanation': 'INSIGHTS_ONLY_SENTINEL'}]}
        with patch.object(app.local_insights, 'analyze', return_value=result) as scan:
            self.assertEqual(self.state.inspect_local_changes(self.body), result)
            args, kwargs = scan.call_args
            self.assertEqual(args, (str(self.repo), 'source-id', 'target-id'))
            self.assertEqual(kwargs['exclude_globs'], ['private/**'])
            self.assertFalse(kwargs['cancel_check']())
        self.assertNotIn('INSIGHTS_ONLY_SENTINEL', json.dumps(self.state.read()))
        self.assertFalse(list(self.repo.iterdir()))

    def test_inventory_uses_same_registration_gate(self):
        with patch.object(app.local_insights, 'options', return_value={'sources': []}) as scan:
            self.assertEqual(self.state.inspect_local_changes({'repository': 'fixture-id'}, inventory=True), {'sources': []})
            self.assertEqual(scan.call_args.args, (str(self.repo),))

    def test_invalid_input_and_arbitrary_paths_never_reach_scanner(self):
        invalid = [None, [], {}, dict(self.body, path=str(self.root)),
                   dict(self.body, source=''), dict(self.body, target=['main']),
                   dict(self.body, source='x\0y'), dict(self.body, source='x' * 4097),
                   dict(self.body, repository=str(self.root))]
        with patch.object(app.local_insights, 'analyze') as scan:
            for body in invalid:
                with self.subTest(body=str(body)[:70]), self.assertRaises(app.RepositoryError):
                    self.state.inspect_local_changes(body)
            scan.assert_not_called()

    def test_remote_pending_and_removed_sources_are_rejected(self):
        variants = [dict(self.row, source_kind='github'), dict(self.row, source_kind='public'),
                    dict(self.row, url='https://github.com/example/repo'),
                    dict(self.row, common_dir=None), dict(self.row, status='pending')]
        with patch.object(app.local_insights, 'analyze') as scan:
            for row in variants:
                self.state.snapshot['repositories'] = [row]
                with self.subTest(row=row), self.assertRaises(app.RepositoryError):
                    self.state.inspect_local_changes(self.body)
            self.state.snapshot['repositories'] = [self.row]
            self.config['repositories'] = []
            with self.assertRaises(app.RepositoryError):
                self.state.inspect_local_changes(self.body)
            scan.assert_not_called()

    def test_revision_change_cancels_and_discards_results(self):
        def inspect(*args, cancel_check, **kwargs):
            self.assertFalse(cancel_check())
            with self.state.lock:
                self.state.registry_revision += 1
            self.assertTrue(cancel_check())
            return {'files': [{'path': 'PRIVATE_LATE_RESULT'}]}
        with patch.object(app.local_insights, 'analyze', side_effect=inspect):
            with self.assertRaises(app.RepositoryError) as error:
                self.state.inspect_local_changes(self.body)
            self.assertEqual(error.exception.code, 'stale_scan')
        self.assertNotIn('PRIVATE_LATE_RESULT', json.dumps(self.state.read()))
        self.assertTrue(self.state.insights_lock.acquire(False))
        self.state.insights_lock.release()

    def test_identity_disappearance_without_revision_is_rejected(self):
        def inspect(*args, **kwargs):
            with self.state.lock:
                self.state.snapshot['repositories'] = []
            return {'files': []}
        with patch.object(app.local_insights, 'analyze', side_effect=inspect):
            with self.assertRaises(app.RepositoryError) as error:
                self.state.inspect_local_changes(self.body)
            self.assertEqual(error.exception.status, 409)

    def test_busy_gate_and_exception_release(self):
        self.state.insights_lock.acquire()
        try:
            with patch.object(app.local_insights, 'analyze') as scan:
                with self.assertRaises(app.RepositoryError) as error:
                    self.state.inspect_local_changes(self.body)
                self.assertEqual(error.exception.status, 429)
                scan.assert_not_called()
        finally:
            self.state.insights_lock.release()
        with patch.object(app.local_insights, 'analyze', side_effect=ValueError('fixture')):
            with self.assertRaises(ValueError):
                self.state.inspect_local_changes(self.body)
        self.assertTrue(self.state.insights_lock.acquire(False))
        self.state.insights_lock.release()

    def test_shutdown_cancels_and_discards_results(self):
        def inspect(*args, cancel_check, **kwargs):
            self.state.stop.set()
            self.assertTrue(cancel_check())
            return {'sources': []}
        with patch.object(app.local_insights, 'options', side_effect=inspect):
            with self.assertRaises(app.RepositoryError) as error:
                self.state.inspect_local_changes({'repository': 'fixture-id'}, inventory=True)
            self.assertEqual(error.exception.status, 409)

    def test_http_same_origin_size_and_both_routes(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(self.state))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'

        def post(route, body, origin_header=origin, host=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'Content-Type': 'application/json', 'Origin': origin_header}
            if host:
                headers['Host'] = host
            connection.request('POST', route, body, headers)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result

        for route, body, name in [('/api/local-insights/options', {'repository': 'fixture-id'}, 'options'),
                                  ('/api/local-insights', self.body, 'analyze')]:
            with self.subTest(route=route), patch.object(app.local_insights, name, return_value={'ok': True}) as scan:
                raw = json.dumps(body)
                self.assertEqual(post(route, raw, 'https://attacker.invalid')[0], 403)
                self.assertEqual(post(route, raw, host='attacker.invalid')[0], 403)
                self.assertEqual(post(route, 'x' * 8193)[0], 400)
                self.assertEqual(post(route, '{')[0], 400)
                scan.assert_not_called()
                self.assertEqual(post(route, raw), (200, {'ok': True}))


if __name__ == '__main__':
    unittest.main()
