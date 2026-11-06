"""Offline regressions for cancellation of Git transport descendants."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from git_metrics import GitError, _run
from public_repositories import PublicGit


@unittest.skipUnless(os.name in {"posix", "nt"} and shutil.which("git"),
                     "The offline executable Git helper requires Git")
class SubprocessCancellationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wv-cancellation-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pids = self.root / "pids.json"
        self.addCleanup(self.stop_fixture_processes)

    @staticmethod
    def running(pid):
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            api.OpenProcess.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.WaitForSingleObject.restype = wintypes.DWORD
            api.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if not handle:
                if ctypes.get_last_error() == 87:  # process no longer exists
                    return False
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                status = api.WaitForSingleObject(handle, 0)
                if status not in (0, 258):  # WAIT_OBJECT_0 / WAIT_TIMEOUT
                    raise ctypes.WinError(ctypes.get_last_error())
                return status == 258
            finally:
                api.CloseHandle(handle)
        # Linux can briefly retain a killed orphan as a zombie. It cannot run or
        # hold a pipe open, so do not confuse that with a surviving helper.
        stat = Path(f"/proc/{pid}/stat")
        try:
            if stat.exists() and stat.read_text().split(") ", 1)[1].startswith("Z "):
                return False
            os.kill(pid, 0)
        except (ProcessLookupError, FileNotFoundError):
            return False
        return True

    def stop_fixture_processes(self):
        if self.pids.exists():
            for pid in json.loads(self.pids.read_text()):
                if self.running(pid):
                    try:
                        os.kill(pid, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def assert_descendants_stopped(self):
        self.assertTrue(self.pids.exists(), "The actual Git helper must have started")
        pids = json.loads(self.pids.read_text())
        deadline = time.monotonic() + 1
        while any(self.running(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(any(self.running(pid) for pid in pids),
                         "A transport helper or its child survived cancellation")

    def test_contained_command_preserves_binary_input_arguments_environment_and_exit(self):
        value = 'space and "quotes" \\ snowman \u2603'
        environment = os.environ.copy()
        environment["WV_CANCELLATION_TEST"] = value
        script = (
            "import json, os, sys; "
            "sys.stdout.buffer.write(sys.stdin.buffer.read()); "
            "sys.stdout.buffer.write(json.dumps([sys.argv[1], os.environ['WV_CANCELLATION_TEST']], "
            "ensure_ascii=False).encode('utf-8')); "
            "sys.stderr.buffer.write(b'warning\\r\\n'); sys.exit(7)"
        )
        code, out, err = _run([sys.executable, "-c", script, value],
                              input_data=b"\x00\xff\r\n", environment=environment)
        self.assertEqual(code, 7)
        self.assertEqual(out[:4], b"\x00\xff\r\n")
        self.assertEqual(json.loads(out[4:].decode("utf-8")), [value, value])
        self.assertEqual(err, b"warning\r\n")

    def fetch_with_helper(self, *, overflow):
        helpers = self.root / "helpers"
        helpers.mkdir()
        child_ready = self.root / "child-ready"
        child_source = (
            "from pathlib import Path; import time; "
            f"Path({str(child_ready)!r}).write_text('ready'); time.sleep(60)"
        )
        helper = helpers / ("helper.py" if os.name == "nt" else "git-remote-https")
        helper.write_text(
            f"#!{sys.executable}\n"
            "import json, os, subprocess, sys, time\n"
            "from pathlib import Path\n"
            f"child = subprocess.Popen([sys.executable, '-c', {child_source!r}], "
            "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            f"while not Path({str(child_ready)!r}).exists(): time.sleep(.005)\n"
            f"Path({str(self.pids)!r}).write_text(json.dumps([os.getpid(), child.pid]))\n"
            + ("sys.stderr.buffer.write(b'x' * (512 * 1024)); sys.stderr.buffer.flush()\n" if overflow else "")
            + "time.sleep(60)\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)
        if os.name == "nt":
            (helpers / "git-remote-https").write_text(
                "#!/bin/sh\nexec " + shlex.quote(Path(sys.executable).as_posix())
                + " " + shlex.quote(helper.as_posix()) + ' "$@"\n', encoding="utf-8")
        cache = self.root / "cache"
        cache.mkdir()
        git = PublicGit(cache)
        git.run("init", "--bare", "--template=", str(cache))
        git.prefix.insert(1, "--exec-path=" + str(helpers))
        git.run("fetch", "--quiet", "--depth=2000", "--no-tags",
                "--no-recurse-submodules", "--no-auto-maintenance", "--",
                "https://127.0.0.1:1/fixture/offline.git",
                "+refs/heads/main:refs/heads/observed", timeout=5 if overflow else 2)

    def test_timeout_stops_git_transport_helper_and_child(self):
        with self.assertRaisesRegex(GitError, "exceeded 2 seconds"):
            self.fetch_with_helper(overflow=False)
        self.assert_descendants_stopped()

    def test_output_overflow_stops_git_transport_helper_and_child(self):
        with self.assertRaisesRegex(GitError, "output exceeded"):
            self.fetch_with_helper(overflow=True)
        self.assert_descendants_stopped()

    def test_exited_parent_cannot_leave_output_readers_and_child_running(self):
        child_source = (
            "from pathlib import Path; import os, time; "
            f"Path({str(self.pids)!r}).write_text('[' + str(os.getpid()) + ']'); "
            "time.sleep(60)"
        )
        source = (
            "import subprocess, sys, time; from pathlib import Path; "
            f"subprocess.Popen([sys.executable, '-c', {child_source!r}]); "
            f"ready=Path({str(self.pids)!r})\n"
            "while not ready.exists(): time.sleep(.005)\n"
        )
        with self.assertRaisesRegex(GitError, "output could not be fully collected"):
            _run([sys.executable, "-c", source], timeout=5)
        self.assert_descendants_stopped()

    @unittest.skipUnless(os.name == "nt", "Windows Job Object admission")
    def test_failed_job_admission_never_executes_target(self):
        marker = self.root / "target-executed"
        command = [sys.executable, "-c",
                   f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"]
        for stage in ("_create", "_resume"):
            with self.subTest(stage=stage):
                with mock.patch("windows_job.WindowsJob." + stage,
                                side_effect=OSError("fixture admission failure")):
                    with self.assertRaisesRegex(GitError, "fixture admission failure"):
                        _run(command)
                self.assertFalse(marker.exists(), "Uncontained target executed")

    def test_reader_start_failure_reaps_process_and_closes_pipes(self):
        thread_start = threading.Thread.start
        for failing_reader in (1, 2):
            with self.subTest(reader=failing_reader):
                processes, count = [], 0
                if os.name == "nt":
                    from windows_job import WindowsJob
                    original = WindowsJob.start
                    target = "windows_job.WindowsJob.start"
                else:
                    original = subprocess.Popen
                    target = "git_metrics.subprocess.Popen"

                def record_process(*args, **kwargs):
                    process = original(*args, **kwargs)
                    processes.append(process)
                    return process

                def fail_start(reader):
                    nonlocal count
                    count += 1
                    if count == failing_reader:
                        raise RuntimeError("fixture reader start failure")
                    return thread_start(reader)

                with mock.patch(target, new=record_process), mock.patch(
                        "git_metrics.threading.Thread.start", new=fail_start):
                    with self.assertRaisesRegex(RuntimeError, "fixture reader start failure"):
                        _run([sys.executable, "-c", "import time; time.sleep(60)"])
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll(), "Reader failure leaked its process")
                self.assertTrue(processes[0].stdout.closed)
                self.assertTrue(processes[0].stderr.closed)

    @unittest.skipUnless(os.name == "nt", "Windows creation-time job assignment")
    def test_controller_exit_before_resume_cannot_leave_suspended_orphan(self):
        executed = self.root / "unexpected-execution"
        child_source = f"from pathlib import Path; Path({str(executed)!r}).write_text('ran')"
        controller_source = (
            f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})\n"
            "import time; from pathlib import Path\n"
            "from windows_job import WindowsJob\n"
            "from git_metrics import _run\n"
            "original = WindowsJob._create\n"
            "def pause_after_creation(self, command, env, startup, info):\n"
            "    original(self, command, env, startup, info)\n"
            f"    Path({str(self.pids)!r}).write_text('[' + str(info.dwProcessId) + ']')\n"
            "    time.sleep(60)\n"
            "WindowsJob._create = pause_after_creation\n"
            f"_run([sys.executable, '-c', {child_source!r}], timeout=30)\n"
        )
        controller = subprocess.Popen([sys.executable, "-c", controller_source],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while not self.pids.exists() and controller.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.pids.exists(), "Contained suspended target must be created")
            self.assertFalse(executed.exists(), "The suspended target must not execute")
        finally:
            controller.kill()
            controller.wait(timeout=2)
        self.assert_descendants_stopped()

    @unittest.skipUnless(os.name == "nt", "Windows kill-on-close job lifetime")
    def test_controller_exit_closes_job_without_child_inheriting_handle(self):
        child_source = (
            "from pathlib import Path; import os, time; "
            f"Path({str(self.pids)!r}).write_text('[' + str(os.getpid()) + ']'); "
            "time.sleep(60)"
        )
        controller_source = (
            f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
            "from git_metrics import _run; "
            f"_run([sys.executable, '-c', {child_source!r}], timeout=30)"
        )
        controller = subprocess.Popen([sys.executable, "-c", controller_source],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while not self.pids.exists() and controller.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(self.pids.exists(), "Contained target must start before controller exits")
        finally:
            controller.kill()
            controller.wait(timeout=2)
        self.assert_descendants_stopped()


if __name__ == "__main__":
    unittest.main()
