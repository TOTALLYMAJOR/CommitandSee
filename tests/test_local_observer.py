from __future__ import annotations

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from local_observer import Git, ObservationError, observe, parse_status
from observation_store import Store
from work_visibility import main


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        self.git('init', '-q', '--initial-branch=main')
        (self.repo / 'tracked.txt').write_text('first\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')

    def git(self, *args, root=None, allowed=(0,)):
        result = subprocess.run(['git', '-c', 'core.hooksPath=' + os.devnull, '-C', str(root or self.repo), *args],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertIn(result.returncode, allowed, result.stderr.decode(errors='replace'))
        return result.stdout

    def scan(self, *roots, git=None):
        # Isolate fixtures from global includes/filters while still testing local configuration.
        with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}):
            observer = git or Git()
        observer.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        return observe(roots or [self.repo], observer)

    def tree(self, snapshot):
        return snapshot['clones'][0]['worktrees'][0]

    def test_edit_stage_commit_independent_states(self):
        (self.repo / 'tracked.txt').write_text('second\n')
        row = self.tree(self.scan())
        self.assertEqual(row['files'][0]['worktree'], 'M')
        self.assertEqual(row['files'][0]['index'], ' ')
        self.git('add', '.')
        row = self.tree(self.scan())
        self.assertEqual(row['files'][0]['index'], 'M')
        self.git('commit', '-qm', 'second')
        row = self.tree(self.scan())
        self.assertEqual(row['working_state'], 'clean')
        self.assertEqual(row['publication']['state'], 'unknown')

    def test_linked_worktrees_shared_branches_stashes_and_detached_head(self):
        self.git('branch', 'non-current')
        (self.repo / 'tracked.txt').write_text('parked\n')
        self.git('stash', 'push', '-qm', 'parked')
        linked = self.base / 'linked'
        detached = self.base / 'detached'
        self.git('worktree', 'add', '-q', '-b', 'other', str(linked))
        self.git('worktree', 'add', '-q', '--detach', str(detached))
        (linked / 'pending.txt').write_text('pending')
        snapshot = self.scan(self.repo, linked)
        self.assertEqual(len(snapshot['clones']), 1)
        clone = snapshot['clones'][0]
        self.assertEqual(len(clone['stashes']), 1)
        self.assertEqual(len(clone['worktrees']), 3)
        self.assertIn('refs/heads/non-current', [b['ref'] for b in clone['branches']])
        self.assertTrue(next(w for w in clone['worktrees'] if w['path'] == str(detached))['detached'])
        self.assertEqual(next(w for w in clone['worktrees'] if w['path'] == str(linked))['working_state'], 'dirty')

    def test_independent_clones_not_collapsed(self):
        clone = self.base / 'clone'
        self.git('clone', '-q', str(self.repo), str(clone))
        snapshot = self.scan(self.repo, clone)
        self.assertEqual(len(snapshot['clones']), 2)
        self.assertNotEqual(snapshot['clones'][0]['common_directory'], snapshot['clones'][1]['common_directory'])

    def test_unborn_and_inaccessible(self):
        unborn = self.base / 'unborn'
        unborn.mkdir()
        self.git('init', '-q', str(unborn))
        self.assertTrue(self.tree(self.scan(unborn))['unborn'])
        snapshot = self.scan(self.base / 'absent')
        self.assertEqual(snapshot['coverage'], 'partial')
        self.assertEqual(snapshot['coverage_gaps'][0]['coverage'], 'unavailable')

    def test_nul_paths_rename_binary_and_conflict(self):
        unusual = 'spaces and\nnewlines.txt'
        (self.repo / unusual).write_bytes(b'\x00\xff\x01')
        self.git('mv', 'tracked.txt', 'renamed\nfile.txt')
        files = self.tree(self.scan())['files']
        self.assertIn(unusual, [f['path'] for f in files])
        rename = next(f for f in files if f['index'] == 'R')
        self.assertEqual(rename['original_path'], 'tracked.txt')
        self.assertEqual(rename['path'], 'renamed\nfile.txt')
        self.assertTrue(parse_status(b'UU conflict.txt\0')[0]['conflict'])

    def test_real_merge_conflict(self):
        self.git('checkout', '-qb', 'side')
        (self.repo / 'tracked.txt').write_text('side\n')
        self.git('commit', '-qam', 'side')
        self.git('checkout', '-q', 'main')
        (self.repo / 'tracked.txt').write_text('main\n')
        self.git('commit', '-qam', 'main')
        self.git('merge', 'side', allowed=(1,))
        row = self.tree(self.scan())
        self.assertTrue(row['files'][0]['conflict'])

    def test_fsmonitor_never_executes_and_scan_preserves_repo_bytes(self):
        marker = self.base / 'executed'
        hook = self.base / 'fsmonitor-hook'
        hook.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\n')
        hook.chmod(0o700)
        self.git('config', 'core.fsmonitor', str(hook))
        self.git('config', 'diff.external', str(hook))
        self.git('config', 'diff.fixture.textconv', str(hook))
        (self.repo / '.gitattributes').write_text('*.txt diff=fixture\n')
        (self.repo / 'tracked.txt').write_text('changed\n')
        def inventory():
            return {str(p.relative_to(self.repo)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns, p.stat().st_mode)
                    for p in self.repo.rglob('*') if p.is_file()}
        before = inventory()
        snapshot = self.scan()
        self.assertEqual(snapshot['coverage'], 'complete')
        self.assertFalse(marker.exists())
        self.assertEqual(before, inventory())

    def test_content_filter_marks_coverage_unavailable_without_running(self):
        marker = self.base / 'filter-ran'
        self.git('config', 'filter.danger.clean', 'touch "' + str(marker) + '"')
        (self.repo / '.gitattributes').write_text('*.txt filter=danger\n')
        (self.repo / 'tracked.txt').write_text('changed')
        row = self.tree(self.scan())
        self.assertEqual(row['reason'], 'content_filters_configured')
        self.assertNotIn('working_state', row)
        self.assertFalse(marker.exists())

    def test_partial_clone_and_missing_worktree(self):
        self.git('config', 'remote.origin.promisor', 'true')
        self.assertEqual(self.tree(self.scan())['reason'], 'partial_clone_not_supported')
        self.git('config', '--unset', 'remote.origin.promisor')
        linked = self.base / 'lost'
        self.git('worktree', 'add', '-q', '-b', 'lost', str(linked))
        shutil.rmtree(linked)
        snapshot = self.scan()
        row = next(w for w in snapshot['clones'][0]['worktrees'] if w['path'] == str(linked))
        self.assertEqual(row['coverage'], 'unavailable')
        self.assertIn('prunable', row['registration'])

    def test_submodule_is_explicit_partial_coverage(self):
        head = self.git('rev-parse', 'HEAD').decode().strip()
        self.git('update-index', '--add', '--cacheinfo', '160000,' + head + ',component')
        row = self.tree(self.scan())
        self.assertEqual(row['coverage'], 'partial')
        self.assertEqual(row['submodules']['paths'], ['component'])

    def test_mid_scan_change_retries_and_continuous_change_is_partial(self):
        real = Git()
        real.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        original = real.run
        count = 0
        def change(root, *args, **kwargs):
            nonlocal count
            output = original(root, *args, **kwargs)
            if args and args[0] == 'status':
                count += 1
                if count == 1:
                    (self.repo / 'tracked.txt').write_text('after first status\n')
            return output
        with patch.object(real, 'run', side_effect=change):
            row = self.tree(self.scan(git=real))
        self.assertEqual(row['attempts'], 2)
        self.assertEqual(row['working_state'], 'dirty')
        def keep_changing(root, *args, **kwargs):
            nonlocal count
            output = original(root, *args, **kwargs)
            if args and args[0] == 'status':
                count += 1
                (self.repo / 'tracked.txt').write_text(str(count))
            return output
        with patch.object(real, 'run', side_effect=keep_changing):
            row = self.tree(self.scan(git=real))
        self.assertEqual(row['reason'], 'inconsistent_observation')

    def test_output_budget_is_a_gap(self):
        (self.repo / ('long' * 50)).write_text('x')
        git = Git(output_limit=100)
        snapshot = self.scan(git=git)
        self.assertEqual(snapshot['coverage'], 'partial')

    def test_old_git_is_rejected(self):
        with patch.object(Git, 'run', return_value=b'git version 2.35.1\n'):
            with self.assertRaisesRegex(ObservationError, '2_36'):
                Git()

    def test_persistence_restart_and_repeated_scan_deduplication(self):
        path = self.base / 'state' / 'observations.sqlite3'
        first = self.scan()
        store = Store(path)
        store.record(first)
        events = len(store.history())
        machine = store.machine_id
        store.close()
        second = self.scan()
        store = Store(path)
        self.addCleanup(store.close)
        store.record(second)
        self.assertEqual(machine, store.machine_id)
        self.assertEqual(events, len(store.history()))
        self.assertEqual(first['persistence']['entities'][1]['first_seen'], second['persistence']['entities'][1]['first_seen'])
        self.assertTrue(all(not e['changed'] for e in second['persistence']['entities']))
        (self.repo / 'tracked.txt').write_text('changed')
        third = store.record(self.scan())
        self.assertEqual(len(store.history()), events + 1)
        self.assertEqual(first['clones'][0]['clone_id'], third['clones'][0]['clone_id'])
        self.assertEqual(first['clones'][0]['worktrees'][0]['worktree_id'], third['clones'][0]['worktrees'][0]['worktree_id'])

    def test_failure_preserves_last_success_and_last_known_state(self):
        path = self.base / 'state.sqlite3'
        store = Store(path)
        self.addCleanup(store.close)
        good = store.record(self.scan())
        failed = copy.deepcopy(good)
        failed.pop('persistence')
        failed['finished_at'] = '2099-01-01T00:00:00+00:00'
        failed['clones'][0]['worktrees'][0].update(coverage='unavailable', reason='test_gap')
        store.record(failed)
        row = store.db.execute("SELECT last_success, last_known_json FROM entities WHERE kind='worktree'").fetchone()
        self.assertEqual(row[0], good['finished_at'])
        self.assertEqual(json.loads(row[1])['coverage'], 'complete')

    def test_cli_refuses_storage_in_monitored_worktrees_and_common_dir(self):
        for database in [self.repo / 'state.sqlite3', self.repo / '.git' / 'state.sqlite3']:
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(['snapshot', '--root', str(self.repo), '--database', str(database)]), 1)
            self.assertFalse(database.exists())
        linked = self.base / 'linked'
        self.git('worktree', 'add', '-q', '-b', 'linked', str(linked))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(['snapshot', '--root', str(self.repo), '--database', str(linked / 'state.sqlite3')]), 1)
        self.assertFalse((linked / 'state.sqlite3').exists())

    def test_cli_snapshot_and_read_only_history(self):
        path = self.base / 'monitor' / 'observations.sqlite3'
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['snapshot', '--root', str(self.repo), '--database', str(path)]), 0)
        self.assertEqual(json.loads(output.getvalue())['coverage'], 'complete')
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['history', '--database', str(path)]), 0)
        self.assertEqual(len(json.loads(output.getvalue())), 3)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_stash_failure_keeps_worktree_inventory(self):
        (self.repo / 'tracked.txt').write_text('parked')
        self.git('stash', 'push', '-qm', 'parked')
        git = Git()
        original = git.run
        def fail_stash(root, *args, **kwargs):
            if args and args[0] == 'reflog':
                raise ObservationError('stash_objects_missing')
            return original(root, *args, **kwargs)
        with patch.object(git, 'run', side_effect=fail_stash):
            snapshot = self.scan(git=git)
        self.assertEqual(snapshot['coverage'], 'partial')
        self.assertEqual(self.tree(snapshot)['working_state'], 'clean')
        self.assertEqual(snapshot['clones'][0]['stashes_error'], 'stash_objects_missing')

    def test_root_gap_resolves_in_same_persistent_entity(self):
        store = Store(self.base / 'state.sqlite3')
        self.addCleanup(store.close)
        snapshot = self.scan()
        failed = {'finished_at': '2000-01-01T00:00:00+00:00', 'clones': [],
                  'coverage_gaps': [{'path': str(self.repo), 'coverage': 'unavailable', 'reason': 'offline'}]}
        store.record(failed)
        store.record(snapshot)
        rows = store.db.execute("SELECT state_json, first_seen FROM entities WHERE kind='configured_root'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])['coverage'], 'complete')
        self.assertEqual(rows[0][1], failed['finished_at'])

    def test_snapshot_json_handles_non_utf8_paths(self):
        if os.name == 'nt':
            self.skipTest('POSIX byte filename fixture')
        name = os.fsencode(self.repo) + b'/invalid-\xff.txt'
        with open(name, 'wb') as handle:
            handle.write(b'fixture')
        encoded = json.dumps(self.scan(), ensure_ascii=True)
        self.assertIn('invalid-', encoded)
        self.assertIn('\\udcff', encoded)

    def test_timeout_is_bounded(self):
        git = Git()
        with patch('local_observer.subprocess.Popen') as popen:
            process = popen.return_value.__enter__.return_value
            process.poll.return_value = None
            with patch('local_observer.time.monotonic', side_effect=[0, 11]):
                with self.assertRaisesRegex(ObservationError, 'timeout'):
                    git.run(self.repo, 'status', '--porcelain')
            process.kill.assert_called_once()

    def test_bare_repository_explicitly_has_no_worktree(self):
        bare = self.base / 'bare'
        self.git('clone', '-q', '--bare', str(self.repo), str(bare))
        snapshot = self.scan(bare)
        self.assertEqual(self.tree(snapshot)['reason'], 'bare_repository_no_worktree')
        self.assertEqual(len(snapshot['clones'][0]['branches']), 1)

    def test_environment_cannot_redirect_git_to_another_repository(self):
        with patch.dict(os.environ, {'GIT_DIR': '/not/the/repository', 'GIT_WORK_TREE': '/unrelated',
                                    'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.fsmonitor',
                                    'GIT_CONFIG_VALUE_0': '/untrusted-hook'}):
            git = Git()
        self.assertNotIn('GIT_DIR', git.env)
        self.assertNotIn('GIT_CONFIG_COUNT', git.env)
        self.assertEqual(self.tree(self.scan(git=git))['working_state'], 'clean')


if __name__ == '__main__':
    unittest.main()
