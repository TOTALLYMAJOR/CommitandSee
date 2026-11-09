"""Public URL trust boundary and Git history contract."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import git_dashboard as app
import public_repositories as public

URL = 'https://github.com/octocat/hello-world'
METADATA = {'private': False, 'visibility': 'public', 'html_url': URL, 'default_branch': 'main'}

class PublicRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_normalization_and_url_restrictions(self):
        self.assertEqual(public.public_url('https://github.com/Octocat/Hello-World.git/'), URL)
        for value in ['http://github.com/a/b', 'https://github.com.evil/a/b', 'https://user:token@github.com/a/b', 'https://127.0.0.1/a/b', 'file:///tmp/repo', 'git@github.com:a/b', URL+'?token=bad', URL+'#fragment', 'https://github.com/a/..', 'https://github.com/a/b/extra']:
            with self.subTest(value=value), self.assertRaises(ValueError): public.public_url(value)

    def test_public_registration_keeps_local_and_preserves_config(self):
        config = dict(app.DEFAULTS, repositories=[])
        path = self.root/'config.json'
        path.write_text(json.dumps(dict(config, selection={'keep': True})))
        state = app.LiveState(app.DashboardCollector(config, self.root/'state.json'), path)
        with patch.object(app, 'public_metadata', return_value=METADATA):
            item = state.add_repository({'url': URL, 'product': 'Examples'})
            with self.assertRaises(app.RepositoryError) as raised: state.add_repository({'url': URL})
            self.assertEqual(raised.exception.code, 'duplicate')
        saved = json.loads(path.read_text())
        self.assertEqual(saved['selection'], {'keep': True})
        self.assertEqual(item['source_kind'], 'public')
        args = argparse.Namespace(config=str(path), repo=[], ref=None)
        self.assertEqual(app.read_config(args)['repositories'][0]['url'], URL)
        self.assertEqual(state.read()['repositories'][0]['history'], None)

    def test_remote_history_uses_bare_fixture_and_has_no_local_evidence(self):
        fixture = self.root/'fixture'
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(fixture)], check=True)
        (fixture/'app.txt').write_text('one\ntwo\n')
        subprocess.run(['git', '-C', str(fixture), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(fixture), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'A public fixture'], check=True)
        original = public.PublicGit.run
        def fixture_fetch(git, *args, **kwargs):
            if args[0] == 'fetch':
                args = ('-c', 'protocol.file.allow=always', *[str(fixture) if arg == URL+'.git' else arg for arg in args])
            return original(git, *args, **kwargs)
        item = dict(url=URL, path=URL, name='Public example', product='Examples', exclude_globs=[])
        with patch.object(public, 'public_metadata', return_value=METADATA), patch.object(public.PublicGit, 'run', fixture_fetch):
            result = public.collect_public(item, self.root/'cache', app.DEFAULTS)
        self.assertEqual(result['status'], 'ok', result['errors'])
        self.assertEqual(result['history']['total_added'], 2)
        self.assertEqual(result['history']['commits'], 1)
        self.assertEqual(result['source_status']['worktrees'], 'not_requested')
        self.assertEqual(result['worktrees'], [])
        self.assertEqual(result['path'], URL)
        self.assertFalse(any(p.name == 'app.txt' for p in (self.root/'cache').rglob('*')))

    def test_public_git_ignores_user_config_and_credentials(self):
        with patch.dict('os.environ', {'GIT_CONFIG_GLOBAL': '/bad/config', 'GIT_SSL_NO_VERIFY': '1', 'GIT_CONFIG_COUNT': '2'}):
            git = public.PublicGit(self.root)
        self.assertEqual(git.environment['GIT_CONFIG_GLOBAL'], os.devnull)
        self.assertNotIn('GIT_SSL_NO_VERIFY', git.environment)
        self.assertNotIn('GIT_CONFIG_COUNT', git.environment)
        self.assertIn('http.followRedirects=false', git.prefix)
        self.assertIn('protocol.allow=never', git.prefix)

    def test_metadata_rejects_private_and_rate_limited_responses(self):
        from urllib.error import HTTPError
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(dict(METADATA, private=True)).encode()
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(public, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'public'): public.public_metadata(URL)
        opener.open.side_effect = HTTPError(URL, 429, 'Too many requests', {}, None)
        with patch.object(public, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(ValueError, 'rate limit'): public.public_metadata(URL)

    def test_progress_can_yield_to_newly_added_repository(self):
        config = dict(app.DEFAULTS, repositories=[dict(path='/one', name='One', product='App', ref='HEAD', exclude_globs=[]), dict(path='/two', name='Two', product='App', ref='HEAD', exclude_globs=[])])
        with patch.object(app, 'collect_repository', side_effect=ValueError('unavailable')) as collect:
            result = app.DashboardCollector(config).collect(on_progress=lambda snapshot: True)
        self.assertEqual(collect.call_count, 1)
        self.assertEqual(len(result['repositories']), 1)

    def test_public_failure_does_not_become_clean_or_zero(self):
        with patch.object(public, 'public_metadata', side_effect=ValueError('Rate limited')):
            result = public.collect_public(dict(url=URL, name='Example'), self.root/'cache', app.DEFAULTS)
        self.assertEqual(result['status'], 'error')
        self.assertIsNone(result['history'])
        self.assertEqual(result['source_status']['worktrees'], 'not_requested')
        self.assertIn('Rate limited', result['errors'])

if __name__ == '__main__': unittest.main()
