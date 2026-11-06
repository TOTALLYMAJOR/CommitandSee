"""Offline provider fixture through the real HTTP/auth/registry boundary.

This verifies local integration, not a GitHub authorization or private download.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import git_dashboard as app
from github_auth import API_ROOT, DEVICE_ENDPOINT, TOKEN_ENDPOINT, GitHubAuth


class GitHubFlowTests(unittest.TestCase):
    def test_authorize_select_import_disconnect_and_restart_without_credentials(self):
        access = 'ghu_' + 'SyntheticAccess' * 3
        refresh = 'ghr_' + 'SyntheticRefresh' * 3
        device = 'synthetic_device_code_1234567890'
        approved = threading.Event()
        calls = []
        private = dict(id=1001, name='private-fixture', full_name='fixture/private-fixture',
                       owner={'login': 'fixture'}, private=True, archived=False,
                       html_url='https://github.com/fixture/private-fixture', default_branch='main')
        public = dict(private, id=1002, name='public-fixture', full_name='fixture/public-fixture',
                      html_url='https://github.com/fixture/public-fixture', private=False)

        def provider(method, url, *, data=None, token=None):
            calls.append((method, url))
            if method == 'POST' and url == DEVICE_ENDPOINT:
                return dict(device_code=device, user_code='ABCD-EFGH',
                            verification_uri='https://github.com/login/device', expires_in=900, interval=5)
            if method == 'POST' and url == TOKEN_ENDPOINT:
                self.assertEqual(data['grant_type'], 'urn:ietf:params:oauth:grant-type:device_code')
                self.assertNotIn('client_secret', data)
                if not approved.is_set():
                    return {'error': 'authorization_pending'}
                return dict(access_token=access, refresh_token=refresh, token_type='bearer',
                            expires_in=28800, refresh_token_expires_in=15897600)
            self.assertEqual(token, access)
            if url == API_ROOT + '/user':
                return {'id': 42, 'login': 'fixture'}
            if url == API_ROOT + '/user/installations?per_page=100&page=1':
                return {'total_count': 1, 'installations': [dict(id=7, app_slug='fixture-app',
                        suspended_at=None, permissions={'contents': 'read', 'metadata': 'read'})]}
            if url == API_ROOT + '/user/installations/7/repositories?per_page=100&page=1':
                return {'total_count': 2, 'repositories': [copy.deepcopy(private), copy.deepcopy(public)]}
            if url == API_ROOT + '/repositories/1001':
                return copy.deepcopy(private)
            raise AssertionError('Unexpected fixture request: ' + method + ' ' + url)

        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                'COMMITANDSEE_GITHUB_CLIENT_ID': 'Iv1.fixture',
                'COMMITANDSEE_GITHUB_APP_SLUG': 'fixture-app'}):
            root = Path(temporary)
            config_path = root / 'config.json'
            original = json.dumps({'repositories': [], 'timezone': 'UTC',
                                   'github_app': {'client_id': 'Iv1.fixture', 'app_slug': 'fixture-app'}})
            config_path.write_text(original, encoding='utf-8')
            args = argparse.Namespace(command='serve', config=str(config_path), repo=[], ref=None)
            config = app.read_config(args)
            # The injected wait compresses provider time; no real provider is called.
            auth = GitHubAuth(config['github_app'], request=provider,
                              wait=lambda cancelled, seconds: cancelled.wait(0.01))
            self.addCleanup(auth.close)
            state = app.LiveState(app.DashboardCollector(config, root / 'state.json', auth=auth), config_path)
            server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(state))
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            captured = []

            def request(method, path, body=None):
                connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                headers = {'Origin': f'http://127.0.0.1:{server.server_port}'}
                if body is not None:
                    headers['Content-Type'] = 'application/json'
                connection.request(method, path, json.dumps(body) if body is not None else None, headers)
                response = connection.getresponse()
                content = response.read()
                captured.append(content)
                status = response.status
                self.assertEqual(response.getheader('Cache-Control'), 'no-store')
                connection.close()
                return status, json.loads(content)

            def wait_for_status(expected):
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    status, body = request('GET', '/api/github/status')
                    self.assertEqual(status, 200)
                    if body['status'] == expected and (expected != 'pending' or body.get('user_code')):
                        return body
                    time.sleep(0.01)
                self.fail('Fixture authorization did not reach ' + expected)

            try:
                self.assertEqual(request('POST', '/api/github/start', {})[0], 200)
                pending = wait_for_status('pending')
                self.assertEqual(pending['user_code'], 'ABCD-EFGH')
                approved.set()
                connected = wait_for_status('connected')
                self.assertEqual(connected['user'], {'id': 42, 'login': 'fixture'})
                status, listing = request('POST', '/api/github/repositories', {})
                self.assertEqual(status, 200)
                self.assertEqual({r['id'] for r in listing['repositories']}, {1001, 1002})
                status, imported = request('POST', '/api/github/import', {'repository_ids': [1001]})
                self.assertEqual(status, 200)
                self.assertEqual([r['id'] for r in imported['imported']], [1001])
                self.assertEqual(imported['failed'], [])
                snapshot = request('GET', '/api/snapshot')[1]
                self.assertEqual(len(snapshot['repositories']), 1)
                self.assertEqual(snapshot['repositories'][0]['source_kind'], 'github')
                self.assertEqual(snapshot['repositories'][0]['url'], private['html_url'])
                duplicate = request('POST', '/api/github/import', {'repository_ids': [1001]})[1]
                self.assertEqual([r['id'] for r in duplicate['already_configured']], [1001])
                self.assertEqual(request('POST', '/api/github/disconnect', {})[1]['status'], 'disconnected')
                disconnected = request('GET', '/api/snapshot')[1]['repositories'][0]
                self.assertIsNone(disconnected['history'])
                self.assertFalse(request('GET', '/api/github/status')[1]['user'])
                self.assertEqual(request('POST', '/api/github/repositories', {})[0], 401)
                self.assertEqual(config_path.read_text(encoding='utf-8'), original)
            finally:
                auth.close()
                server.shutdown()
                server.server_close()
                server_thread.join(timeout=2)

            # Persisted choices return after restart, without any authenticated session.
            restarted = app.LiveState(app.DashboardCollector(app.read_config(args), root / 'state.json'), config_path)
            try:
                self.assertEqual(restarted.auth.status()['status'], 'disconnected')
                self.assertEqual(len(restarted.read()['repositories']), 1)
                self.assertIsNone(restarted.read()['repositories'][0]['history'])
                for secret in (access, refresh, device):
                    self.assertNotIn(secret.encode(), b'\n'.join(captured))
                    for path in root.rglob('*'):
                        if path.is_file():
                            self.assertNotIn(secret.encode(), path.read_bytes(), str(path))
                # Discovery and import do not invoke a remote-history Git download.
                self.assertFalse((root / 'github-repositories').exists())
                self.assertTrue(any(url == TOKEN_ENDPOINT for _, url in calls))
            finally:
                restarted.auth.close()


if __name__ == '__main__':
    unittest.main()
