"""Offline GitHub account/import routing and private-result isolation tests."""
import argparse
from contextlib import contextmanager
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


SECRET = 'ghu_fixture_must_never_reach_registry_or_browser'


class FakeAuth:
    def __init__(self):
        self.generation = 1
        self.user = {'id': 7, 'login': 'fixture-user'}
        self.connected = True
        self.callback = None
        self.lock = threading.RLock()
        self.catalog = {11: {'id': 11, 'name': 'private-project', 'full_name': 'fixture/private-project',
            'owner': 'fixture', 'private': True, 'html_url': 'https://github.com/fixture/private-project',
            'default_branch': 'main', 'archived': False, 'installation_id': 91}}

    def status(self):
        with self.lock:
            return {'status': 'connected' if self.connected else 'disconnected', 'configured': True,
                'generation': self.generation, 'user': self.user if self.connected else None,
                'session_only': True, 'message': '', 'user_code': None, 'verification_uri': None,
                'expires_in': None, 'installation_url': None}

    def set_on_change(self, callback):
        self.callback = callback

    def start(self):
        return self.status()

    def cancel(self):
        return self.disconnect()

    def disconnect(self):
        with self.lock:
            self.generation += 1
            self.connected = False
        if self.callback:
            self.callback(self.status())
        return self.status()

    def close(self):
        self.disconnect()

    def token(self):
        return SECRET

    def repositories(self):
        return {'repositories': list(self.catalog.values()), 'truncated': False, 'limits': {}, 'message': ''}

    def repository(self, repo_id):
        from github_auth import GitHubAuthError
        if repo_id not in self.catalog:
            raise GitHubAuthError('not_found', 'Repository is not accessible.', 404)
        return copy.deepcopy(self.catalog[repo_id])

    @contextmanager
    def session_guard(self, generation, user_id):
        from github_auth import GitHubAuthError
        with self.lock:
            if not self.connected or generation != self.generation or user_id != self.user['id']:
                raise GitHubAuthError('session_changed', 'Sign in again.', 409)
            yield


class GitHubIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / 'config.json'
        self.config_path.write_text(json.dumps({'repositories': [], 'custom': 'keep'}))
        args = argparse.Namespace(command='serve', config=str(self.config_path), repo=[], ref=None)
        self.config = app.read_config(args)
        self.auth = FakeAuth()
        self.collector = app.DashboardCollector(self.config, self.root / 'state.json', auth=self.auth)
        self.state = app.LiveState(self.collector, self.config_path)

    def import_one(self):
        return self.state.import_github_repositories({'repository_ids': [11]})

    def test_import_persists_only_selected_safe_metadata_and_survives_restart(self):
        before = self.config_path.read_bytes()
        result = self.import_one()
        self.assertEqual([row['id'] for row in result['imported']], [11])
        item = self.collector.config['repositories'][0]
        self.assertEqual(item['source_kind'], 'github')
        self.assertEqual(item['github_account_id'], 7)
        self.assertEqual(item['github_repository_id'], 11)
        self.assertEqual(item['installation_id'], 91)
        self.assertTrue(item['private'])
        self.assertEqual(self.config_path.read_bytes(), before)
        args = argparse.Namespace(command='serve', config=str(self.config_path), repo=[], ref=None)
        restarted = app.read_config(args)
        self.assertEqual(restarted['repositories'][0]['source_kind'], 'github')
        for data in (self.state.read(), self.state.registry.read(), result):
            self.assertNotIn(SECRET, json.dumps(data))
        self.assertNotIn(SECRET, app.render_html(self.state.read()))

    def test_import_results_distinguish_duplicates_and_failed_selection(self):
        self.import_one()
        result = self.state.import_github_repositories({'repository_ids': [11, 12]})
        self.assertEqual(result['imported'], [])
        self.assertEqual([row['id'] for row in result['already_configured']], [11])
        self.assertEqual([row['id'] for row in result['failed']], [12])
        self.assertEqual(len(self.collector.config['repositories']), 1)

    def test_import_rejects_credential_payload_and_invalid_ids(self):
        for body in ({'repository_ids': [11], 'token': SECRET}, {'repository_ids': [True]},
                     {'repository_ids': [-1]}, {'repository_ids': ['11']}, {'repository_ids': []},
                     {'repository_ids': list(range(1, 52))}):
            with self.subTest(body=body), self.assertRaises(app.RepositoryError):
                self.state.import_github_repositories(body)
        self.assertEqual(self.collector.config['repositories'], [])

    def test_github_normalization_rejects_credentials_and_keeps_source_identity(self):
        item = dict(url='https://github.com/fixture/private-project', source_kind='github',
                    github_repository_id=11, github_account_id=7, installation_id=91, private=True)
        normalized = app.normalize_repositories([item], self.root, app.DEFAULTS)
        self.assertEqual(normalized[0]['source_kind'], 'github')
        for poisoned in (dict(item, token=SECRET), dict(item, access_token=SECRET),
                         dict(item, github_account_id=True), dict(item, installation_id=None)):
            with self.subTest(poisoned=poisoned), self.assertRaises(ValueError):
                app.normalize_repositories([poisoned], self.root, app.DEFAULTS)

    def test_disconnect_during_metadata_lookup_prevents_import_commit(self):
        original = self.auth.repository

        def disconnect(repo_id):
            result = original(repo_id)
            self.auth.disconnect()
            return result

        with patch.object(self.auth, 'repository', side_effect=disconnect):
            with self.assertRaises(Exception) as raised:
                self.import_one()
        self.assertIn(getattr(raised.exception, 'code', ''), ('session_changed', 'authentication_required'))
        self.assertEqual(self.state.registry.read(), {})

    def test_disconnect_at_registry_commit_guard_rolls_back_import(self):
        original = self.state.registry.update

        def update(change, guard):
            def disconnect_after_change(entries):
                change(entries)
                self.auth.disconnect()
            return original(disconnect_after_change, guard)

        with patch.object(self.state.registry, 'update', side_effect=update):
            with self.assertRaises(app.GitHubAuthError):
                self.import_one()
        self.assertEqual(self.state.registry.read(), {})
        self.assertEqual(self.collector.config['repositories'], [])

    def observed(self):
        self.import_one()
        row = copy.deepcopy(self.collector.config['repositories'][0])
        row.update(id=row['url'], status='ok', github_generation=self.auth.generation,
                   history={'commits': 99, 'daily': [], 'private_commit_subject': 'sensitive history'},
                   head='private-head', collected_at='2026-11-05T00:00:00Z',
                   source_status={'history': 'ok'}, worktrees=[], branches=[], stashes=[], errors=[], warnings=[])
        snapshot = self.state.read()
        snapshot['repositories'] = [row]
        self.state.publish(snapshot)
        return snapshot

    def test_disconnect_scrubs_current_previous_and_late_authenticated_results(self):
        late = self.observed()
        self.auth.disconnect()
        self.state.publish(late)
        self.state.publish(dict(late, repositories=[]))
        snapshot = self.state.read()
        row = snapshot['repositories'][0]
        self.assertIsNone(row['history'])
        self.assertIsNone(row['head'])
        self.assertTrue(row['authentication_required'])
        self.assertNotIn('sensitive history', json.dumps(snapshot))
        self.assertNotIn('private-head', app.render_html(snapshot))

    def test_account_switch_cannot_reuse_previous_private_history(self):
        late = self.observed()
        self.auth.generation += 1
        self.auth.user = {'id': 8, 'login': 'another-account'}
        self.state.publish(late)
        self.assertIsNone(self.state.read()['repositories'][0]['history'])

    def test_signed_out_collector_does_not_fetch_authenticated_source(self):
        self.import_one()
        self.auth.disconnect()
        with patch.object(app, 'collect_authenticated', side_effect=AssertionError('fetch after logout')):
            result = self.collector.collect()
        self.assertIsNone(result['repositories'][0]['history'])
        self.assertTrue(result['repositories'][0]['authentication_required'])

    def test_late_collector_result_is_not_cached_after_disconnect(self):
        observed = self.observed()['repositories'][0]

        def collect(*args):
            self.auth.disconnect()
            return observed

        with patch.object(app, 'collect_authenticated', side_effect=collect):
            result = self.collector.collect()
        self.assertEqual(self.collector.github_cache, {})
        self.assertIsNone(result['repositories'][0]['history'])
        self.assertIsNone(result['repositories'][0]['head'])

    def test_cached_collection_refreshes_auth_before_publication(self):
        observed = self.observed()['repositories'][0]
        with patch.object(app, 'collect_authenticated', return_value=observed) as collect:
            self.collector.collect()
            with patch.object(self.auth, 'token', wraps=self.auth.token) as token:
                result = self.collector.collect()
            self.assertEqual(collect.call_count, 1)
            token.assert_called_once_with()
        self.assertTrue(result['repositories'][0]['history']['cached'])

    def test_real_auth_refreshes_expired_access_token_for_cached_collection(self):
        from github_auth import GitHubAuth
        from test_github_auth import Provider, Clock, CONFIG, token_payload

        provider, clock, requests = Provider(), Clock(), []
        provider.polls = [token_payload(expires=90)]

        def request(method, url, *, data=None, token=None):
            requests.append(data or {})
            return provider(method, url, data=data, token=token)

        auth = GitHubAuth(CONFIG, request=request, clock=clock, wait=clock.wait)
        self.addCleanup(auth.close)
        auth.start()
        auth._thread.join(2)
        self.assertEqual(auth.status()['status'], 'connected')
        auth.repositories()
        self.auth = auth
        self.collector = app.DashboardCollector(self.config, self.root / 'state.json', auth=auth)
        self.state = app.LiveState(self.collector, self.config_path)
        observed = self.observed()['repositories'][0]
        generation = auth.generation
        with patch.object(app, 'collect_authenticated', return_value=observed) as collect:
            self.collector.collect()
            clock.now += 91
            result = self.collector.collect()
            self.assertEqual(collect.call_count, 1)
        self.assertEqual(auth.generation, generation)
        self.assertIsNotNone(result['repositories'][0]['history'])
        self.assertTrue(result['repositories'][0]['history']['cached'])
        self.assertEqual(sum(item.get('grant_type') == 'refresh_token' for item in requests), 1)

    def test_cached_refresh_cannot_publish_after_session_changes(self):
        observed = self.observed()['repositories'][0]
        with patch.object(app, 'collect_authenticated', return_value=observed):
            self.collector.collect()
        with patch.object(self.auth, 'token', side_effect=lambda: self.auth.disconnect()):
            result = self.collector.collect()
        self.assertIsNone(result['repositories'][0]['history'])
        self.assertEqual(self.collector.github_cache, {})

    def test_epoch_distinguishes_restart_even_when_generation_matches(self):
        status = self.state.github_status()
        self.assertEqual(status['github_session_id'], self.state.read()['github_session_id'])
        self.assertEqual(status['github_session_id'], self.state.github_action('start', {})['github_session_id'])
        restarted = app.LiveState(app.DashboardCollector(copy.deepcopy(self.config), auth=FakeAuth()), self.config_path)
        self.assertEqual(restarted.github_status()['generation'], status['generation'])
        self.assertNotEqual(restarted.github_status()['github_session_id'], status['github_session_id'])

    def test_late_repository_discovery_is_rejected_after_disconnect(self):
        original = self.auth.repositories

        def discovery():
            result = original()
            self.auth.disconnect()
            return result

        with patch.object(self.auth, 'repositories', side_effect=discovery):
            with self.assertRaises(Exception):
                self.state.github_repositories({})

    def test_github_routes_keep_origin_host_body_and_secret_boundaries(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(self.state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'

        def request(method, route, body=None, headers=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            connection.request(method, route, body, headers or {})
            response = connection.getresponse()
            status, payload, cache = response.status, response.read(), response.getheader('Cache-Control')
            connection.close()
            self.assertNotIn(SECRET.encode(), payload)
            self.assertEqual(cache, 'no-store')
            return status, payload, cache

        status, payload, cache = request('GET', '/api/github/status')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['status'], 'connected')
        self.assertEqual(cache, 'no-store')
        for route in ('start', 'cancel', 'disconnect', 'repositories', 'import'):
            path = '/api/github/' + route
            self.assertEqual(request('POST', path, '{}', {'Origin': 'https://attacker.invalid', 'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(request('POST', path, '{}', {'Origin': origin, 'Host': 'attacker.invalid', 'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(request('POST', path, 'x' * 8193, {'Origin': origin, 'Content-Type': 'application/json'})[0], 400)
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        status, payload, cache = request('POST', '/api/github/import', '{"repository_ids":[11]}', headers)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(payload)['imported']), 1)
        self.assertEqual(cache, 'no-store')
        self.assertEqual(request('POST', '/api/github/disconnect', '{}', headers)[0], 200)


if __name__ == '__main__':
    unittest.main()
