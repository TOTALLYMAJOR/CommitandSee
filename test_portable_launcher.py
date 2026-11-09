"""Portable startup contracts, independent of a browser or installed build tools."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

import portable_launcher as launcher


class PortableLauncherTests(unittest.TestCase):
    def test_windows_data_is_outside_the_extracted_application(self):
        home = Path('/users/fixture')
        result = launcher.user_data_dir(platform='win32', environ={'LOCALAPPDATA': '/users/fixture/local'}, home=home)
        self.assertEqual(result, Path('/users/fixture/local/CommitandSee'))
        self.assertEqual(launcher.user_data_dir(platform='win32', environ={}, home=home),
                         home / 'AppData' / 'Local' / 'CommitandSee')

    def test_first_start_creates_empty_configuration_without_replacing_saved_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings' / 'config.json'
            launcher.prepare_config(path)
            self.assertEqual(json.loads(path.read_text())['repositories'], [])
            saved = '{"repositories": [], "title": "Owner settings"}\n'
            path.write_text(saved)
            launcher.prepare_config(path)
            self.assertEqual(path.read_text(), saved)

    def test_first_start_uses_bundled_publisher_defaults_without_saving_an_override(self):
        defaults = json.loads((Path(__file__).parent / 'github_app_defaults.json').read_text())
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, dict(os.environ), clear=True):
            os.environ.pop('COMMITANDSEE_GITHUB_CLIENT_ID', None)
            os.environ.pop('COMMITANDSEE_GITHUB_APP_SLUG', None)
            path = Path(folder) / 'config.json'
            launcher.prepare_config(path)
            self.assertNotIn('github_app', json.loads(path.read_text()))
            config = launcher.app.read_config(argparse.Namespace(command='serve', config=str(path), repo=[], ref=None))
            self.assertEqual(config['github_app'], defaults)

    def test_frozen_bundle_cannot_be_used_for_writable_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'CommitandSee'
            with self.assertRaisesRegex(ValueError, 'outside'):
                launcher.validate_locations(bundle / 'config.json', Path(folder) / 'state.json', bundle)
            with self.assertRaisesRegex(ValueError, 'outside'):
                launcher.validate_locations(Path(folder) / 'config.json', bundle / 'state.json', bundle)

    def test_state_cannot_replace_configuration_or_registry_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text('{"title":"Owner settings","repositories":[]}')
            before = config.read_bytes()
            for state in (config, Path(str(config) + '.registry.sqlite3'),
                          Path(str(config) + '.registry.sqlite3-wal'),
                          Path(str(config) + '.registry.sqlite3-shm'),
                          Path(str(config) + '.registry.sqlite3-journal')):
                with self.subTest(state=state):
                    with self.assertRaisesRegex(ValueError, 'separate'):
                        launcher.validate_locations(config, state, None)
            self.assertEqual(config.read_bytes(), before)

    def test_configuration_and_state_symlink_aliases_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'config.json'
            config.write_text('{}')
            state = Path(folder) / 'state.json'
            try:
                state.symlink_to(config)
            except OSError:
                self.skipTest('Creating symlinks is unavailable for this account')
            with self.assertRaisesRegex(ValueError, 'separate'):
                launcher.validate_locations(config, state, None)

    def test_missing_git_is_actionable_and_does_not_start_a_server(self):
        with patch.object(launcher, 'find_git', return_value=None), \
                patch.object(launcher, 'serve') as serve, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(launcher.main(['--no-browser']), 2)
        serve.assert_not_called()
        self.assertIn('Git for Windows', errors.getvalue())
        self.assertIn('Python', errors.getvalue())

    def test_git_installation_directory_is_added_to_path(self):
        with patch.dict(os.environ, {'PATH': '/existing'}, clear=False), \
                patch.object(launcher, 'find_git', return_value='/fixture/git/cmd/git.exe'), \
                patch.object(launcher.app, '_git_capabilities', return_value=('2.56.0', True)):
            self.assertEqual(launcher.ensure_git(), '2.56.0')
            self.assertEqual(os.environ['PATH'].split(os.pathsep)[0],
                             str(Path('/fixture/git/cmd/git.exe').resolve().parent))

    def session(self, *, no_browser=False, ready_error=None):
        order = []
        state = MagicMock()
        server = MagicMock()
        server.server_address = ('127.0.0.1', 54321)
        stopped = threading.Event()
        stopped.set()
        def ready(url):
            order.append('ready')
            if ready_error:
                raise ready_error
        with patch.object(launcher.app, 'DashboardCollector'), \
                patch.object(launcher.app, 'LiveState', return_value=state), \
                patch.object(launcher.app, 'make_handler'), \
                patch.object(launcher, 'ThreadingHTTPServer', return_value=server) as create, \
                patch.object(launcher.threading, 'Thread'), \
                patch.object(launcher, 'wait_until_ready', side_effect=ready), \
                patch.object(launcher.webbrowser, 'open', side_effect=lambda *a, **k: order.append('browser') or True) as browser, \
                contextlib.redirect_stdout(io.StringIO()):
            if ready_error:
                with self.assertRaises(type(ready_error)):
                    launcher.serve({}, Path('/settings/config.json'), Path('/settings/state.json'),
                                   open_browser=not no_browser, stop_event=stopped)
            else:
                launcher.serve({}, Path('/settings/config.json'), Path('/settings/state.json'),
                               open_browser=not no_browser, stop_event=stopped)
        create.assert_called_once()
        self.assertEqual(create.call_args.args[0], ('127.0.0.1', 0))
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        state.stop.set.assert_called_once()
        state.wake.set.assert_called_once()
        return order, state, browser

    def test_browser_opens_only_after_http_readiness_and_shutdown_closes_server(self):
        order, state, _ = self.session()
        self.assertEqual(order, ['ready', 'browser'])
        state.worker.start.assert_called_once()
        state.worker.join.assert_called_once()

    def test_no_browser_still_starts_an_usable_server(self):
        order, state, browser = self.session(no_browser=True)
        self.assertEqual(order, ['ready'])
        state.worker.start.assert_called_once()
        browser.assert_not_called()

    def test_failed_readiness_never_opens_browser_or_starts_collection(self):
        _, state, browser = self.session(ready_error=TimeoutError('Not ready'))
        state.worker.start.assert_not_called()
        state.worker.join.assert_not_called()
        browser.assert_not_called()

    def test_shutdown_cancels_auth_before_waiting_for_collection(self):
        _, state, _ = self.session()
        state.auth.close.assert_called_once_with()
        calls = [str(call) for call in state.mock_calls]
        self.assertLess(calls.index('call.auth.close()'), calls.index('call.worker.join(timeout=2)'))

    def test_failed_readiness_also_closes_auth(self):
        _, state, _ = self.session(ready_error=TimeoutError('Not ready'))
        state.auth.close.assert_called_once_with()

    def test_failed_port_binding_closes_auth_without_starting_collection(self):
        state = MagicMock()
        with patch.object(launcher.app, 'DashboardCollector'), \
                patch.object(launcher.app, 'LiveState', return_value=state), \
                patch.object(launcher, 'ThreadingHTTPServer', side_effect=OSError('Port unavailable')):
            with self.assertRaisesRegex(OSError, 'Port unavailable'):
                launcher.serve({}, Path('/settings/config.json'), Path('/settings/state.json'))
        state.auth.close.assert_called_once_with()
        state.worker.start.assert_not_called()

    def test_auth_sources_and_setup_guide_are_part_of_the_build_capture(self):
        build = runpy.run_path(str(Path(__file__).parent / 'packaging' / 'build_portable.py'))
        auth_inputs = ('github_auth.py', 'authenticated_repositories.py', 'local_insights.py',
                       'github_app_defaults.json', 'docs/GITHUB-APP-SETUP.md')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in set(build['INPUTS']) | set(auth_inputs):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('initial build source\n')
            captured = build['source_hashes'](root)
            for name in auth_inputs:
                with self.subTest(source=name):
                    path = root / name
                    path.write_text('changed auth source\n')
                    self.assertTrue(captured != build['source_hashes'](root),
                                    'A changed auth dependency must invalidate the captured build')
                    path.write_text('initial build source\n')

    def test_explicit_settings_and_state_paths_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'custom.json'
            state = Path(folder) / 'state' / 'history.json'
            with patch.object(launcher, 'ensure_git', return_value='2.56.0'), \
                    patch.object(launcher, 'serve') as serve, \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(launcher.main(['--no-browser', '--config', str(config), '--state', str(state)]), 0)
            self.assertEqual(serve.call_args.args[1:3], (config.resolve(), state.resolve()))
            self.assertFalse(serve.call_args.kwargs['open_browser'])


if __name__ == '__main__':
    unittest.main()
