"""Bounded local Git observations. Never fetch, refresh the index, or run hooks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


class ObservationError(Exception):
    """Fixed, credential-free diagnostic suitable for storing in observations."""


class Git:
    def __init__(self, timeout=10, output_limit=8 * 1024 * 1024):
        self.timeout, self.output_limit = timeout, output_limit
        self.executable = shutil.which('git')
        if not self.executable:
            raise ObservationError('git_unavailable')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
                        GIT_NO_LAZY_FETCH='1', GIT_ALLOW_PROTOCOL='', LC_ALL='C')
        version = self.run(None, '--version')
        match = re.search(rb'git version (\d+)\.(\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (2, 36, 0):
            raise ObservationError('git_2_36_or_newer_required')

    def run(self, root, *args, allowed=(0,)):
        command = [self.executable, '--no-optional-locks', '-c', 'core.fsmonitor=false',
                   '-c', 'core.hooksPath=' + os.devnull, '-c', 'core.untrackedCache=false',
                   '-c', 'diff.external=', '-c', 'submodule.recurse=false',
                   '-c', 'maintenance.auto=false', '-c', 'gc.auto=0']
        if root is not None:
            command += ['-C', os.fspath(root)]
        # Only internal callers supply arguments; never shell text or repository commands.
        command += list(args)
        try:
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                with subprocess.Popen(command, env=self.env, stdout=out, stderr=err) as process:
                    started = time.monotonic()
                    while process.poll() is None:
                        if time.monotonic() - started > self.timeout:
                            process.kill()
                            raise ObservationError('command_timeout')
                        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > self.output_limit:
                            process.kill()
                            raise ObservationError('command_output_budget')
                        time.sleep(0.01)
                    if process.returncode not in allowed:
                        raise ObservationError('git_command_failed')
                    if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > self.output_limit:
                        raise ObservationError('command_output_budget')
                    if process.returncode == 0 and os.fstat(err.fileno()).st_size:
                        raise ObservationError('git_reported_diagnostic')
                    out.seek(0)
                    return out.read()
        except OSError:
            raise ObservationError('git_process_unavailable') from None


def decode(value):
    return os.fsdecode(value)


def parse_worktrees(raw):
    records, current = [], {}
    for field in raw.split(b'\0'):
        if not field:
            if current:
                records.append(current)
                current = {}
            continue
        key, sep, value = field.partition(b' ')
        current[decode(key)] = decode(value) if sep else True
    if current:
        records.append(current)
    return records


def parse_status(raw):
    fields, records, index = raw.split(b'\0'), [], 0
    while index < len(fields) and fields[index]:
        field = fields[index]
        index += 1
        if len(field) < 4 or field[2:3] != b' ':
            raise ObservationError('malformed_status')
        code = field[:2].decode('ascii')
        record = {'path': decode(field[3:]), 'index': code[0], 'worktree': code[1],
                  'untracked': code == '??',
                  'conflict': code in {'DD', 'AU', 'UD', 'UA', 'DU', 'AA', 'UU'}}
        if 'R' in code or 'C' in code:
            if index >= len(fields) or not fields[index]:
                raise ObservationError('malformed_rename')
            record['original_path'] = decode(fields[index])
            index += 1
        records.append(record)
    return records


def file_stamp(path):
    try:
        stat = path.lstat()
        return [stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    except FileNotFoundError:
        return ['absent']
    except OSError:
        raise ObservationError('fingerprint_unavailable') from None


def _identity(git, root):
    head = decode(git.run(root, 'rev-parse', '--verify', '--quiet', 'HEAD', allowed=(0, 1))).strip() or None
    branch = decode(git.run(root, 'symbolic-ref', '-q', 'HEAD', allowed=(0, 1))).strip() or None
    return {'head': head, 'branch': branch, 'detached': branch is None and head is not None,
            'unborn': head is None and branch is not None}


def _read_worktree(git, entry, expected_common):
    root = Path(entry['worktree'])
    result = {'path': str(root), 'registration': {k: v for k, v in entry.items() if k not in {'HEAD', 'branch', 'detached'}}, 'coverage': 'unavailable',
              'publication': {'state': 'unknown', 'reason': 'remote_not_observed'},
              'loc': {'state': 'unavailable', 'reason': 'not_implemented'},
              'task': {'state': 'unlinked', 'active_run': 'unknown'}}
    if 'bare' in entry:
        result.update(coverage='partial', reason='bare_repository_no_worktree')
        return result
    try:
        common = Path(decode(git.run(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).removesuffix('\n')).resolve()
        if str(common) != expected_common:
            raise ObservationError('worktree_repository_identity_changed')
        # No file-content operations when filters or lazy object acquisition are possible.
        filters = git.run(root, 'config', '--null', '--name-only', '--get-regexp',
                          r'^filter\..*\.(clean|process)$', allowed=(0, 1))
        partial = git.run(root, 'config', '--null', '--name-only', '--get-regexp',
                          r'^(extensions\.partialclone|remote\..*\.promisor)$', allowed=(0, 1))
        result.update(_identity(git, root))
        if filters or partial:
            result['reason'] = 'content_filters_configured' if filters else 'partial_clone_not_supported'
            return result
        index_path = Path(decode(git.run(root, 'rev-parse', '--path-format=absolute', '--git-path', 'index')).removesuffix('\n'))
        submodules = []
        for field in git.run(root, 'ls-files', '--stage', '-z').split(b'\0'):
            if field.startswith(b'160000 '):
                submodules.append(decode(field.split(b'\t', 1)[1]))
        for attempt in range(2):
            before = _identity(git, root), file_stamp(index_path)
            raw = git.run(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=all')
            files = parse_status(raw)
            stamps = [(item['path'], file_stamp(root / item['path'])) for item in files]
            again = git.run(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all', '--ignore-submodules=all')
            after = _identity(git, root), file_stamp(index_path)
            if before == after and raw == again and stamps == [(item['path'], file_stamp(root / item['path'])) for item in files]:
                result.update(after[0])
                result.update(files=files, file_fingerprints=stamps, coverage='complete',
                              working_state='dirty' if files else 'clean', attempts=attempt + 1,
                              submodules={'state': 'not_collected' if submodules else 'none', 'paths': submodules})
                if submodules:
                    result.update(coverage='partial', reason='submodule_content_not_collected')
                return result
        result.update(coverage='partial', reason='inconsistent_observation')
    except (ObservationError, OSError) as error:
        result['reason'] = str(error) if isinstance(error, ObservationError) else 'worktree_inaccessible'
    return result


def _worktree(git, entry, expected_common):
    at = timestamp()
    result = _read_worktree(git, entry, expected_common)
    return {**result, 'started_at': at, 'finished_at': timestamp()}


def _shared_refs(git, root):
    result = {'branches': [], 'stashes': [], 'shared_refs_coverage': 'complete'}
    try:
        raw = git.run(root, 'for-each-ref', '--format=%(refname)%00%(objectname)%00%(upstream)%00%(push)%00', 'refs/heads/')
        for line in raw.splitlines():
            values = line.split(b'\0')
            if len(values) != 5:
                raise ObservationError('malformed_branches')
            name, sha, upstream, push, _ = map(decode, values)
            result['branches'].append({'ref': name, 'head': sha, 'upstream': upstream or None,
                                      'cached_push_tracking_ref': push or None,
                                      'publication': {'state': 'unknown', 'reason': 'remote_not_observed'}})
    except ObservationError as error:
        result.update(shared_refs_coverage='partial', branches_error=str(error))
    try:
        tip = git.run(root, 'for-each-ref', '--format=%(objectname)', 'refs/stash').strip()
        if tip:
            raw = git.run(root, 'reflog', 'show', '--format=%H%x00%gD%x00', 'refs/stash')
            for line in raw.splitlines():
                values = line.split(b'\0')
                if len(values) != 3:
                    raise ObservationError('malformed_stashes')
                result['stashes'].append({'sha': decode(values[0]), 'selector': decode(values[1])})
            if not result['stashes'] or result['stashes'][0]['sha'] != decode(tip):
                raise ObservationError('stash_reflog_incomplete_or_changed')
    except ObservationError as error:
        result.update(shared_refs_coverage='partial', stashes_error=str(error))
    result['refs_observed_at'] = timestamp()
    return result


def observe(roots, git=None):
    started, began = timestamp(), time.monotonic()
    git = git or Git()
    clones, gaps = {}, []
    for requested in roots:
        root = Path(requested).expanduser().resolve()
        try:
            common = decode(git.run(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).removesuffix('\n')
            common = str(Path(common).resolve())
            if common in clones:
                clones[common]['configured_roots'].append(str(root))
                continue
            entries = parse_worktrees(git.run(root, 'worktree', 'list', '--porcelain', '-z'))
            clone = {'common_directory': common, 'configured_roots': [str(root)], **_shared_refs(git, root),
                     'worktrees': [_worktree(git, entry, common) for entry in entries]}
            clones[common] = clone
        except ObservationError as error:
            gaps.append({'path': str(root), 'coverage': 'unavailable', 'reason': str(error)})
    result = {'schema_version': 1, 'source': 'local_git', 'started_at': started, 'finished_at': timestamp(),
              'duration_seconds': round(time.monotonic() - began, 4), 'clones': list(clones.values()),
              'coverage_gaps': gaps,
              'limits': ['No remote queries or ancestry comparisons', 'LOC and native tasks not collected',
                         'Submodule content not scanned', 'No inactivity or abandonment conclusions',
                         'Bounded consistency check, not an atomic filesystem snapshot']}
    result['coverage_scope'] = 'Configured clone metadata and top-level worktree inventory only'
    result['coverage'] = 'partial' if gaps or any(c['shared_refs_coverage'] != 'complete' or any(w['coverage'] != 'complete' for w in c['worktrees']) for c in clones.values()) else 'complete'
    return result
