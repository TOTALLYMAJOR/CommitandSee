"""Configuration containment, calendar caching, and repository removal regressions."""
import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import git_dashboard as app
import git_metrics
from repository_registry import validate_state_destination


class RegistryRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.git('init', '-q', self.repo)
        self.path = self.root / 'config.json'

    def git(self, *args, env=None):
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *map(str, args)],
                              env=env, check=True, capture_output=True)

    def linked(self):
        self.git('-C', self.repo, '-c', 'user.name=Fixture', '-c',
                 'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Fixture')
        linked = self.root / 'linked'
        self.git('-C', self.repo, 'worktree', 'add', '-q', '-b', 'linked', linked)
        return linked

    def state(self, entries=(), *, path=None, cli=()):
        path = path or self.path
        path.write_text(json.dumps(dict(app.DEFAULTS, repositories=list(entries),
                                       selection={'keep': True})))
        args = argparse.Namespace(command='serve', config=str(path), repo=list(cli), ref=None)
        config = app.read_config(args)
        return app.LiveState(app.DashboardCollector(config, self.root / 'state.json'), path)

    def reopen(self, *, cli=()):
        args = argparse.Namespace(command='serve', config=str(self.path), repo=list(cli), ref=None)
        return app.LiveState(app.DashboardCollector(app.read_config(args), self.root / 'state.json'), self.path)

    def test_external_writer_after_final_check_is_never_overwritten(self):
        state = self.state()
        external = b'{"repositories": [], "external_editor": "preserve byte for byte"}\n'
        update = state.registry.update
        injected = False

        def edit_at_commit_boundary(change, guard):
            mutation_complete = False

            def mutate(entries):
                nonlocal mutation_complete
                result = change(entries)
                mutation_complete = True
                return result

            def guarded():
                nonlocal injected
                result = guard()
                if mutation_complete:
                    # This is the final transaction guard: the mutation's
                    # identity checks have finished and its SQL is staged.
                    self.path.write_bytes(external)
                    injected = True
                return result

            return update(mutate, guarded)

        with patch.object(state.registry, 'update', side_effect=edit_at_commit_boundary):
            state.add_repository({'path': str(self.repo), 'name': 'Committed UI source'})
        self.assertTrue(injected)
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(state.registry.read()[str(self.repo)]['name'], 'Committed UI source')
        self.assertEqual(self.reopen().read()['repositories'][0]['name'], 'Committed UI source')

    def test_source_cli_rejects_config_and_state_alias_before_collection(self):
        self.state([{'path': 'repo'}])
        original = self.path.read_bytes()
        with patch.object(app.sys, 'stderr'):
            with self.assertRaises(SystemExit) as raised:
                app.main(['scan', '--config', str(self.path), '--state', str(self.path),
                          '--output', str(self.root / 'report.html')])
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.root / 'report.html').exists())

    def test_source_cli_rejects_state_collisions_with_every_registry_artifact(self):
        state = self.state([{'path': 'repo'}])
        original = self.path.read_bytes()
        for artifact in state.registry.artifacts:
            with self.subTest(artifact=artifact.name), patch.object(app.sys, 'stderr'):
                with patch.object(app, 'DashboardCollector', side_effect=AssertionError('collection started')):
                    with self.assertRaises(SystemExit) as raised:
                        app.main(['scan', '--config', str(self.path), '--state', str(artifact),
                                  '--output', str(self.root / 'report.html')])
                self.assertEqual(raised.exception.code, 2)
                self.assertFalse(artifact.exists())
        self.assertEqual(self.path.read_bytes(), original)

    def test_state_destination_detects_resolved_and_hardlink_aliases(self):
        self.state([{'path': 'repo'}])
        alias = self.root / 'alias.json'
        try:
            os.link(self.path, alias)
        except (OSError, NotImplementedError):
            self.skipTest('Hardlink fixtures unavailable on this platform')
        with self.assertRaises(ValueError):
            validate_state_destination(self.path, alias)
        alias.unlink()
        try:
            alias.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink fixtures unavailable on this platform')
        with self.assertRaises(ValueError):
            validate_state_destination(alias, self.path)

    def test_ui_mutations_leave_base_config_immutable_and_merge_on_restart(self):
        state = self.state([{'path': 'repo', 'name': 'Legacy repository'}])
        base = self.path.read_bytes()
        other = self.root / 'other'
        self.git('init', '-q', other)
        state.add_repository({'path': str(other), 'name': 'Added in UI'})
        state.remove_repository({'path': str(self.repo)})
        self.assertEqual(self.path.read_bytes(), base)
        rows = self.reopen().read()['repositories']
        self.assertEqual([(row['path'], row['name']) for row in rows], [(str(other), 'Added in UI')])

    def test_reading_legacy_config_does_not_create_registry(self):
        state = self.state([{'path': 'repo'}])
        self.reopen()
        self.assertFalse(state.registry.path.exists())

    def test_external_config_restart_merges_without_discarding_metadata(self):
        state = self.state()
        state.add_repository({'path': str(self.repo), 'name': 'UI source'})
        external = b'{"repositories": [], "title": "Edited externally", "custom": [1, 2]}\n'
        self.path.write_bytes(external)
        restarted = self.reopen()
        self.assertEqual(restarted.read()['title'], 'Edited externally')
        self.assertEqual(restarted.read()['repositories'][0]['name'], 'UI source')
        restarted.remove_repository({'path': str(self.repo)})
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(self.reopen().read()['repositories'], [])

    def test_independent_observer_processes_do_not_lose_additions_or_removals(self):
        self.state([{'path': 'repo', 'name': 'Legacy'}])
        original = self.path.read_bytes()
        other = self.root / 'other'
        self.git('init', '-q', other)
        script = '''
import argparse
from pathlib import Path
import sys
import time
import git_dashboard as app
config, action, target, ready, release = sys.argv[1:]
args = argparse.Namespace(command='serve', config=config, repo=[], ref=None)
state = app.LiveState(app.DashboardCollector(app.read_config(args)), config)
Path(ready).touch()
deadline = time.monotonic() + 10
while not Path(release).exists():
    if time.monotonic() > deadline:
        raise RuntimeError('fixture release timed out')
    time.sleep(.01)
getattr(state, action + '_repository')({'path': target})
'''
        for index, (added, removed) in enumerate(((other, self.repo), (self.repo, other))):
            with self.subTest(round=index):
                release = self.root / f'release-{index}'
                ready = [self.root / f'ready-{index}-{i}' for i in range(2)]
                processes = [subprocess.Popen([sys.executable, '-B', '-c', script, str(self.path),
                    action, str(target), str(mark), str(release)], cwd=Path(app.__file__).parent,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for (action, target), mark in zip((('add', added), ('remove', removed)), ready)]
                try:
                    deadline = time.monotonic() + 10
                    while not all(mark.exists() for mark in ready) and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(all(mark.exists() for mark in ready))
                    release.touch()
                    for process in processes:
                        stdout, stderr = process.communicate(timeout=15)
                        self.assertEqual(process.returncode, 0, (stdout + stderr).decode())
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                        process.communicate()
                self.assertEqual([row['path'] for row in self.reopen().read()['repositories']], [str(added)])
        self.assertEqual(self.path.read_bytes(), original)

    def test_stale_observer_detects_duplicate_linked_alias_in_latest_registry(self):
        linked = self.linked()
        first = self.state()
        second = self.reopen()
        first.add_repository({'path': str(self.repo)})
        with self.assertRaises(app.RepositoryError) as raised:
            second.add_repository({'path': str(linked)})
        self.assertEqual(raised.exception.code, 'duplicate')
        self.assertEqual([row['path'] for row in self.reopen().read()['repositories']], [str(self.repo)])

    def test_registry_and_sqlite_artifacts_reject_links(self):
        state = self.state()
        original = self.path.read_bytes()
        target = self.repo / 'protected-file'
        target.write_bytes(b'Never write this file.')
        for artifact in state.registry.artifacts:
            with self.subTest(artifact=artifact.name):
                try:
                    artifact.symlink_to(target)
                except (OSError, NotImplementedError):
                    self.skipTest('Symlink fixtures unavailable on this platform')
                try:
                    with self.assertRaises(OSError):
                        state.add_repository({'path': str(self.repo)})
                    self.assertEqual(target.read_bytes(), b'Never write this file.')
                    self.assertEqual(self.path.read_bytes(), original)
                finally:
                    artifact.unlink()

    def test_registry_refuses_unrelated_database_and_rolls_back_sql_failure(self):
        state = self.state()
        with sqlite3.connect(state.registry.path) as connection:
            connection.execute('CREATE TABLE unrelated (value TEXT)')
            connection.execute("INSERT INTO unrelated VALUES ('keep')")
        before = state.registry.path.read_bytes()
        with self.assertRaises(OSError):
            state.add_repository({'path': str(self.repo)})
        self.assertEqual(state.registry.path.read_bytes(), before)
        state.registry.path.unlink()
        state.add_repository({'path': str(self.repo)})
        other = self.root / 'other'
        self.git('init', '-q', other)
        with sqlite3.connect(state.registry.path) as connection:
            connection.execute("CREATE TRIGGER refuse_insert BEFORE INSERT ON repository_overrides "
                               "BEGIN SELECT RAISE(ABORT, 'fixture write failure'); END")
        with self.assertRaises(OSError):
            state.add_repository({'path': str(other)})
        self.assertEqual([row['path'] for row in self.reopen().read()['repositories']], [str(self.repo)])
        if os.name == 'posix':
            self.assertEqual(state.registry.path.stat().st_mode & 0o777, 0o600)

    def test_new_repository_rejects_config_in_any_linked_worktree(self):
        linked = self.linked()
        path = linked / 'dashboard.json'
        state = self.state(path=path)
        before = path.read_bytes()
        with self.assertRaises(app.RepositoryError) as raised:
            state.add_repository({'path': str(self.repo)})
        self.assertEqual(raised.exception.code, 'unsafe_config')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(state.collector.config['repositories'], [])

    def test_existing_repository_linked_config_rejects_add_and_remove(self):
        linked = self.linked()
        path = linked / 'dashboard.json'
        state = self.state([{'path': str(self.repo)}], path=path)
        other = self.root / 'other'
        self.git('init', '-q', other)
        before = path.read_bytes()
        for action, body in ((state.add_repository, {'path': str(other)}),
                             (state.remove_repository, {'path': str(self.repo)})):
            with self.subTest(action=action.__name__):
                with self.assertRaises(app.RepositoryError) as raised:
                    action(body)
                self.assertEqual(raised.exception.code, 'unsafe_config')
                self.assertEqual(path.read_bytes(), before)

    def test_remove_persists_and_preserves_files_metadata_history_and_cache(self):
        state = self.state([{'path': 'repo', 'name': 'Fixture'}])
        original = self.path.read_bytes()
        (self.repo / 'untracked.txt').write_text('Keep this work.\n')
        cache = state.collector.public_cache_root
        cache.mkdir()
        (cache / 'keep').write_text('Retained cache')
        state.collector.tracker.states = {'keep': {'last_seen': '2026-11-05T00:00:00Z'}}
        before = {str(p.relative_to(self.repo)): p.read_bytes()
                  for p in self.repo.rglob('*') if p.is_file()}
        self.assertTrue(state.read()['repositories'][0]['removable'])
        removed = state.remove_repository({'path': str(self.repo)})
        self.assertEqual(removed['name'], 'Fixture')
        self.assertEqual(removed['configured_paths'], [str(self.repo)])
        saved = json.loads(self.path.read_text())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(saved['selection'], {'keep': True})
        self.assertEqual(state.read()['repositories'], [])
        self.assertEqual(state.collector.config['repositories'], [])
        args = argparse.Namespace(command='serve', config=str(self.path), repo=[], ref=None)
        self.assertEqual(app.read_config(args)['repositories'], [])
        self.assertEqual(before, {str(p.relative_to(self.repo)): p.read_bytes()
                                 for p in self.repo.rglob('*') if p.is_file()})
        self.assertEqual((cache / 'keep').read_text(), 'Retained cache')
        self.assertIn('keep', state.collector.tracker.states)

    def test_remove_public_repository_without_network_or_cache_deletion(self):
        url = 'https://github.com/octocat/Hello-World'
        state = self.state([{'url': url, 'name': 'Public'}])
        with patch.object(app, 'public_metadata', side_effect=AssertionError('network')):
            state.remove_repository({'path': state.read()['repositories'][0]['path']})
        self.assertEqual(state.read()['repositories'], [])
        self.assertEqual(self.reopen().read()['repositories'], [])

    def test_remove_deduplicated_aliases_even_before_first_scan(self):
        linked = self.linked()
        state = self.state([{'path': 'repo'}, {'path': 'linked', 'product': 'Other'}])
        removed = state.remove_repository({'path': str(self.repo)})
        self.assertEqual(set(removed['configured_paths']), {str(self.repo), str(linked)})
        self.assertEqual(state.read()['repositories'], [])
        self.assertEqual(self.reopen().read()['repositories'], [])
        self.assertTrue(linked.is_dir())

    def test_removed_row_is_not_restored_by_inflight_collection(self):
        state = self.state([{'path': 'repo'}])
        entered, finish = threading.Event(), threading.Event()
        old = state.read()
        old['repositories'][0].update(status='ok', collected_at='2026-11-05T00:00:00Z')

        def slow_collect(**kwargs):
            entered.set()
            self.assertTrue(finish.wait(5))
            kwargs['on_progress'](copy.deepcopy(old))
            state.stop.set()
            return old

        with patch.object(state.collector, 'collect', side_effect=slow_collect):
            state.worker.start()
            try:
                self.assertTrue(entered.wait(5))
                state.remove_repository({'path': str(self.repo)})
                finish.set()
                state.worker.join(5)
                self.assertFalse(state.worker.is_alive())
            finally:
                state.stop.set()
                state.wake.set()
                finish.set()
                state.worker.join(5)
        self.assertEqual(state.read()['repositories'], [])
        state.publish(old)
        self.assertEqual(state.read()['repositories'], [])

    def test_remove_validation_and_failed_writes_preserve_state(self):
        state = self.state([{'path': 'repo'}])
        before = self.path.read_bytes()
        for body in ({}, [], {'path': ''}, {'path': str(self.repo), 'extra': 1},
                     {'path': str(self.root / 'missing')}):
            with self.subTest(body=body), self.assertRaises(app.RepositoryError):
                state.remove_repository(body)
        with patch.object(state.registry, 'update', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                state.remove_repository({'path': str(self.repo)})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(len(state.read()['repositories']), 1)
        self.path.write_text('{}')
        with self.assertRaises(app.RepositoryError) as raised:
            state.remove_repository({'path': str(self.repo)})
        self.assertEqual(raised.exception.code, 'config_changed')
        self.assertEqual(len(state.collector.config['repositories']), 1)

    def test_config_edit_during_identity_checks_is_not_overwritten(self):
        state = self.state([{'path': 'repo'}])
        other = self.root / 'other'
        self.git('init', '-q', other)
        external = json.dumps({'repositories': [{'path': 'repo'}], 'external': 'keep'}).encode()

        def edit_during_check():
            self.path.write_bytes(external)
            return {}

        with patch.object(state, 'identities', side_effect=edit_during_check):
            with self.assertRaises(app.RepositoryError) as raised:
                state.add_repository({'path': str(other)})
        self.assertEqual(raised.exception.code, 'config_changed')
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(len(state.collector.config['repositories']), 1)

    def test_cli_sources_cannot_claim_persistent_removal(self):
        for entries in ([], [{'path': 'repo'}]):
            with self.subTest(persisted=bool(entries)):
                state = self.state(entries, cli=[str(self.repo)])
                self.assertFalse(state.read()['repositories'][0]['removable'])
                with self.assertRaises(app.RepositoryError) as raised:
                    state.remove_repository({'path': str(self.repo)})
                self.assertEqual(raised.exception.code, 'read_only')

    def test_remove_route_preserves_request_boundaries(self):
        state = self.state([{'path': 'repo'}])
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.make_handler(state))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        origin = f'http://127.0.0.1:{server.server_port}'

        def post(body, *, source=origin, content_type='application/json', host=None):
            connection = HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'Origin': source, 'Content-Type': content_type}
            if host:
                headers['Host'] = host
            connection.request('POST', '/api/repositories/remove', body, headers)
            response = connection.getresponse()
            status, payload = response.status, response.read()
            connection.close()
            return status, payload

        body = json.dumps({'path': str(self.repo)})
        self.assertEqual(post(body, source='https://attacker.example')[0], 403)
        self.assertEqual(post(body, host='attacker.example')[0], 403)
        self.assertEqual(post(body, content_type='text/plain')[0], 400)
        self.assertEqual(post('x' * 8193)[0], 400)
        self.assertEqual(post('{')[0], 400)
        status, payload = post(body)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['removed']['path'], str(self.repo))
        self.assertEqual(post(body)[0], 404)

    def test_history_cache_rolls_over_at_effective_timezone_midnight(self):
        cases = [('Unavailable/Timezone', '2026-11-05T23:59:00+00:00', '2026-11-06T00:01:00+00:00')]
        try:
            ZoneInfo('America/Chicago')
        except ZoneInfoNotFoundError:
            pass  # Native Windows can legitimately use the documented UTC fallback.
        else:
            cases.append(('America/Chicago', '2026-11-06T05:59:00+00:00', '2026-11-06T06:01:00+00:00'))
        for zone, before, after in cases:
            with self.subTest(timezone=zone):
                commit_at = datetime.fromisoformat(before).timestamp() - 600
                env = dict(os.environ, GIT_AUTHOR_DATE=f'{int(commit_at)} +0000',
                           GIT_COMMITTER_DATE=f'{int(commit_at)} +0000')
                self.git('-C', self.repo, '-c', 'user.name=Fixture', '-c',
                         'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', zone, env=env)
                state = self.state([{'path': 'repo'}])
                state.collector.config.update(timezone=zone, days=1, history_refresh_seconds=86400)
                moment = datetime.fromisoformat(before)

                class Clock(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

                with patch.object(app, 'datetime', Clock), patch.object(git_metrics.dt, 'datetime', Clock):
                    first = state.collector.collect()['repositories'][0]['history']
                    self.assertGreaterEqual(first['commits'], 1)
                    moment = datetime.fromisoformat(after)
                    actual = state.collector.collect()['repositories'][0]['history']
                    expected = app.collect_repository(self.repo, days=1, timezone=zone)['history']
                self.assertFalse(actual['cached'])
                self.assertEqual(actual['daily'], expected['daily'])
                self.assertEqual(actual['daily'][0]['date'], '2026-11-06')

    def test_public_history_cache_rolls_over_without_shortening_same_day_ttl(self):
        url = 'https://github.com/octocat/hello-world'
        state = self.state([{'url': url}])
        try:
            zone = ZoneInfo('America/Chicago')
            zone_name = 'America/Chicago'
            before, after = '2026-11-06T05:59:00+00:00', '2026-11-06T06:01:00+00:00'
        except ZoneInfoNotFoundError:
            zone, zone_name = timezone.utc, 'UTC'
            before, after = '2026-11-05T23:59:00+00:00', '2026-11-06T00:01:00+00:00'
        state.collector.config.update(timezone=zone_name, days=1, history_refresh_seconds=86400)
        moment = datetime.fromisoformat(before)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

        def collect(item, cache, config):
            return {'id': url, 'path': url, 'name': item['name'], 'status': 'ok',
                    'collected_at': moment.isoformat(), 'history': {'timezone': zone_name,
                    'daily': [{'date': moment.astimezone(zone).date().isoformat()}]}}

        with patch.object(app, 'datetime', Clock), patch.object(app, 'collect_public', side_effect=collect) as observe:
            state.collector.collect()
            moment = datetime.fromisoformat(after)
            result = state.collector.collect()['repositories'][0]
            self.assertEqual(observe.call_count, 2)
            self.assertEqual(result['history']['daily'][0]['date'], '2026-11-06')
            again = state.collector.collect()['repositories'][0]
            self.assertEqual(observe.call_count, 2)
            self.assertTrue(again['history']['cached'])


if __name__ == '__main__':
    unittest.main()
