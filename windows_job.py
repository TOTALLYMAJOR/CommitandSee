"""Admit Windows subprocesses to a kill-on-close Job Object before execution.

Only imported on Windows; uses documented kernel32 APIs through ctypes.
Creation-time job assignment requires Windows 10 / Server 2016 or newer. No
breakaway limits or inheritable job handles are enabled. stdin and output pipes
are the only handles explicitly inherited by the new process.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import msvcrt
import os
import shutil
import subprocess


CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimitInformation),
                ("IoInfo", _IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", ctypes.c_void_p)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


def _kernel32():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                     wintypes.DWORD], wintypes.BOOL),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "InitializeProcThreadAttributeList": ([ctypes.c_void_p, wintypes.DWORD,
            wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)], wintypes.BOOL),
        "UpdateProcThreadAttribute": ([ctypes.c_void_p, wintypes.DWORD, ctypes.c_size_t,
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p], wintypes.BOOL),
        "DeleteProcThreadAttributeList": ([ctypes.c_void_p], None),
        "CreateProcessW": ([wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
            wintypes.LPCWSTR, ctypes.POINTER(_StartupInfo), ctypes.POINTER(_ProcessInformation)],
            wintypes.BOOL),
        "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "GetExitCodeProcess": ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class WindowsJob:
    def __init__(self):
        self.api = _kernel32()
        # NULL security attributes make the unnamed job handle non-inheritable.
        self.handle = _check(self.api.CreateJobObjectW(None, None))
        limits = _ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            _check(self.api.SetInformationJobObject(
                self.handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits), ctypes.sizeof(limits)))
        except BaseException:
            self.close()
            raise

    def _resume(self, thread):
        previous = self.api.ResumeThread(thread)
        if previous == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        if previous != 1:
            raise OSError("Unexpected primary-thread suspension state; refusing to run Git")

    def _create(self, command, environment, startup, info):
        for key, value in environment.items():
            if not key or "=" in key[1:] or "\0" in key or "\0" in value:
                raise ValueError("Invalid subprocess environment")
        block = ctypes.create_unicode_buffer("\0".join(
            key + "=" + value for key, value in sorted(environment.items(), key=lambda row: row[0].upper())
        ) + "\0\0")
        executable = shutil.which(command[0], path=environment.get("PATH")) or command[0]
        line = ctypes.create_unicode_buffer(subprocess.list2cmdline(command))
        _check(self.api.CreateProcessW(
            executable, line, None, None, True,
            CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            block, None, ctypes.cast(ctypes.byref(startup), ctypes.POINTER(_StartupInfo)),
            ctypes.byref(info)))

    def start(self, command, *, stdin, stdout, stderr, env):
        if stdout != subprocess.PIPE or stderr != subprocess.PIPE:
            raise ValueError("Contained Git commands require captured output pipes")
        fds, attributes, process = [], None, None
        info = _ProcessInformation()
        try:
            out_read, out_write = os.pipe()
            fds.extend((out_read, out_write))
            err_read, err_write = os.pipe()
            fds.extend((err_read, err_write))
            input_fd = os.open(os.devnull, os.O_RDONLY) if stdin == subprocess.DEVNULL else os.dup(stdin.fileno())
            fds.append(input_fd)
            child_fds = (input_fd, out_write, err_write)
            for fd in child_fds:
                os.set_inheritable(fd, True)
            handles = (wintypes.HANDLE * 3)(*(msvcrt.get_osfhandle(fd) for fd in child_fds))
            jobs = (wintypes.HANDLE * 1)(self.handle)
            size = ctypes.c_size_t()
            self.api.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            if ctypes.get_last_error() != 122:  # ERROR_INSUFFICIENT_BUFFER
                raise ctypes.WinError(ctypes.get_last_error())
            buffer = ctypes.create_string_buffer(size.value)
            _check(self.api.InitializeProcThreadAttributeList(buffer, 2, 0, ctypes.byref(size)))
            attributes = buffer
            for attribute, value in ((PROC_THREAD_ATTRIBUTE_HANDLE_LIST, handles),
                                     (PROC_THREAD_ATTRIBUTE_JOB_LIST, jobs)):
                _check(self.api.UpdateProcThreadAttribute(
                    attributes, 0, attribute, value, ctypes.sizeof(value), None, None))
            startup = _StartupInfoEx()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput, startup.StartupInfo.hStdOutput, startup.StartupInfo.hStdError = handles
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            # Job assignment is part of CreateProcess, before the API returns.
            # There is no suspended-but-unassigned admission window.
            self._create(command, env, startup, info)
            process = _WindowsProcess(self.api, info.hProcess, info.dwProcessId, command)
            info.hProcess = None  # transferred to process
            process.stdout = os.fdopen(out_read, "rb")
            fds.remove(out_read)
            process.stderr = os.fdopen(err_read, "rb")
            fds.remove(err_read)
            self._resume(info.hThread)
            return process
        except BaseException:
            try:
                self.terminate()
                if process is not None:
                    process.wait(timeout=2)
            finally:
                self.close()
                if process is not None:
                    process.close()
                    for pipe in (process.stdout, process.stderr):
                        if pipe is not None:
                            pipe.close()
            raise
        finally:
            if info.hThread:
                _check(self.api.CloseHandle(info.hThread))
            if info.hProcess:
                _check(self.api.CloseHandle(info.hProcess))
            if attributes is not None:
                self.api.DeleteProcThreadAttributeList(attributes)
            for fd in fds:
                os.close(fd)

    def terminate(self):
        if self.handle is not None:
            _check(self.api.TerminateJobObject(self.handle, 1))

    def close(self):
        if self.handle is not None:
            _check(self.api.CloseHandle(self.handle))
            self.handle = None


class _WindowsProcess:
    """The narrow Popen interface needed by the shared bounded pipe collector."""
    def __init__(self, api, handle, pid, command):
        self.api, self.handle, self.pid, self.args = api, handle, pid, command
        self.returncode = None
        self.stdout = self.stderr = None

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        milliseconds = 0xFFFFFFFF if timeout is None else max(0, math.ceil(timeout * 1000))
        status = self.api.WaitForSingleObject(self.handle, milliseconds)
        if status == 258:  # WAIT_TIMEOUT
            raise subprocess.TimeoutExpired(self.args, timeout)
        if status != 0:
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        _check(self.api.GetExitCodeProcess(self.handle, ctypes.byref(code)))
        self.returncode = code.value
        return self.returncode

    def poll(self):
        try:
            return self.wait(timeout=0)
        except subprocess.TimeoutExpired:
            return None

    def close(self):
        if self.handle is not None:
            _check(self.api.CloseHandle(self.handle))
            self.handle = None
