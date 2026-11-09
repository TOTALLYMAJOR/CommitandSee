"""Bounded, read-only comparisons of local changes and saved file versions.

Results describe bytes and file modes, never semantic equivalence, backup safety,
or author intent. No patch bodies are returned or persisted.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import difflib
import fnmatch
import hashlib
import os
from pathlib import Path
import re
import stat
import time

from git_metrics import GitError, _Git, _environment, _run

MAX_REFS = 48
MAX_STASHES = 16
MAX_REFLOG = 24
MAX_FILES = 120
MAX_TREE_ENTRIES = 12000
MAX_BLOB = 512 * 1024
MAX_BYTES = 24 * 1024 * 1024
MAX_COMMANDS = 320
MAX_SECONDS = 18
MAX_LINES = 1600
HEX = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class InsightError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _sha(value):
    text = value.decode('ascii').strip() if isinstance(value, bytes) else value
    if not HEX.fullmatch(text):
        raise InsightError('unavailable', 'Git returned an unsupported object identity.', 503)
    return text


def _id(kind, value):
    return kind + ':' + hashlib.sha256(os.fsencode(value)).hexdigest()[:24]


class Scan:
    def __init__(self, path, cancel_check=None, exclude_globs=()):
        self.path = Path(path).resolve()
        self.started = time.monotonic()
        self.commands = self.bytes = 0
        self.cancel_check = cancel_check
        self.exclusions = tuple(exclude_globs or ())
        self.warnings = []
        self.blobs = {}
        self.trees = {}
        self.git = _Git(self.path, False)
        # These commands only inspect refs/index/objects; no working-tree diff,
        # status, attribute conversion, checkout, merge, or hash-object -w.
        self.git.prefix[1:1] = ['--no-replace-objects']
        self.git.prefix[1:1] = ['-c', 'protocol.allow=never', '-c', 'protocol.file.allow=never',
                              '-c', 'protocol.https.allow=never', '-c', 'protocol.http.allow=never',
                              '-c', 'protocol.ssh.allow=never', '-c', 'protocol.ext.allow=never',
                              '-c', 'core.hooksPath=' + os.devnull]
        self.environment = _environment()
        self.environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                                GIT_CONFIG_SYSTEM=os.devnull, GIT_NO_REPLACE_OBJECTS='1',
                                GIT_ALLOW_PROTOCOL='', GIT_LITERAL_PATHSPECS='1')
        self.environment.pop('GIT_REPLACE_REF_BASE', None)
        version = self.run('--version', limit=1024)
        match = re.search(rb'git version (\d+)\.(\d+)', version)
        if not match or tuple(map(int, match.groups())) < (2, 37):
            raise InsightError('unsupported', 'Git 2.37 or newer is required.')
        lazy = self.run('--no-lazy-fetch', '--version', allow=(0, 128, 129), limit=1024).startswith(b'git version ')
        if lazy:
            self.git.prefix.insert(1, '--no-lazy-fetch')
        # Git versions before --no-lazy-fetch cannot reliably promise no helper
        # execution in a promisor clone merely through a newer env variable.
        if not lazy and self.run('config', '--get-regexp', r'^(extensions\.partialclone|remote\..*\.promisor)$', allow=(0, 1)):
            raise InsightError('unsupported', 'This partial clone needs Git with --no-lazy-fetch support.')
        self.identity = self.run('rev-parse', '--path-format=absolute', '--git-common-dir').strip()
        if self.run('rev-parse', '--is-bare-repository').strip() != b'true':
            top = Path(os.fsdecode(self.run('rev-parse', '--path-format=absolute', '--show-toplevel').strip())).resolve()
            if top != self.path:
                raise InsightError('unsafe_path', 'The selected repository path is not its current Git worktree root.', 409)
        self.object_format = self.run('rev-parse', '--show-object-format').strip().decode('ascii')
        if self.object_format not in ('sha1', 'sha256'):
            raise InsightError('unsupported', 'Unsupported Git object format.')

    def check(self):
        if self.cancel_check and self.cancel_check():
            raise InsightError('cancelled', 'The repository selection changed or the server is stopping.', 409)
        if time.monotonic() - self.started >= MAX_SECONDS or self.commands >= MAX_COMMANDS or self.bytes >= MAX_BYTES:
            raise InsightError('budget_exceeded', 'This inspection exceeded its bounded scan budget; no conclusion was returned.', 503)

    def consume(self, count):
        self.bytes += count
        self.check()

    def run(self, *args, allow=(0,), limit=2 * 1024 * 1024, path=None):
        self.check()
        self.commands += 1
        prefix = self.git.prefix
        if path is not None:
            prefix = prefix[:-1] + [str(path)]
        try:
            code, out, _ = _run(prefix + list(args), limit=min(limit, MAX_BYTES-self.bytes),
                               timeout=max(.05, MAX_SECONDS-(time.monotonic()-self.started)),
                               environment=self.environment, cancel_check=self.cancel_check)
        except GitError:
            raise InsightError('unavailable', 'Git inspection failed or exceeded its time/output limit; no conclusion was returned.', 503) from None
        self.consume(len(out))
        if code not in allow:
            raise InsightError('unavailable', 'Required local Git objects or metadata could not be read.', 503)
        return out

    def excluded(self, name):
        return any(fnmatch.fnmatchcase(name, pattern) for pattern in self.exclusions)

    def inventory(self):
        raw = self.run('for-each-ref', '--count=' + str(MAX_REFS+1),
                       '--format=%(refname)%00%(objectname)%00%(symref)', 'refs/heads', 'refs/remotes')
        refs, sources, targets = [], [], []
        rows = raw.splitlines()
        limited = len(rows) > MAX_REFS
        for row in rows[:MAX_REFS]:
            name, oid, symbolic = row.split(b'\0')
            if symbolic:
                continue
            name = os.fsdecode(name)
            item = dict(id=_id('ref', name), label=name.removeprefix('refs/'), kind='branch', oid=_sha(oid), ref=name)
            refs.append(item)
            targets.append(item)
            if name.startswith('refs/heads/'):
                sources.append(item)
        stash_raw = self.run('stash', 'list', '-n', str(MAX_STASHES+1), '--format=%H%x00%gd')
        stashes = []
        stash_rows = stash_raw.splitlines()
        limited |= len(stash_rows) > MAX_STASHES
        for row in stash_rows[:MAX_STASHES]:
            oid, label = row.split(b'\0')
            stashes.append(dict(id='stash:' + _sha(oid), label=os.fsdecode(label), kind='stash', oid=_sha(oid)))
        sources += stashes
        sources += [dict(item, id='stash-index:'+item['oid'], label=item['label']+' (staged files)', kind='stash_index') for item in stashes]
        worktrees = []
        work_raw = self.run('worktree', 'list', '--porcelain', '-z')
        for block in work_raw.split(b'\0\0'):
            fields = {}
            for line in block.split(b'\0'):
                key, _, value = line.partition(b' ')
                fields[key] = value
            if b'worktree' not in fields or b'bare' in fields or b'HEAD' not in fields:
                continue
            path = os.fsdecode(fields[b'worktree'])
            branch = os.fsdecode(fields.get(b'branch', b'detached')).removeprefix('refs/heads/')
            for kind, label in [('worktree', 'Working files'), ('index', 'Staged files')]:
                item = dict(id=_id(kind, path), label=f'{label} — {branch} ({Path(path).name})',
                            kind=kind, path=path, oid=_sha(fields[b'HEAD']))
                sources.append(item)
                worktrees.append(item)
        if len(worktrees) > 32:
            limited = True
            sources = [item for item in sources if item not in worktrees[32:]]
            worktrees = worktrees[:32]
        return dict(sources=sources, targets=targets, refs=refs, stashes=stashes,
                    limited=limited, fingerprint=hashlib.sha256(raw+stash_raw+work_raw).hexdigest())

    def tree(self, oid):
        if oid in self.trees:
            return self.trees[oid]
        raw = self.run('ls-tree', '-r', '-z', '--full-tree', oid)
        rows = raw.split(b'\0')
        if len(rows) > MAX_TREE_ENTRIES+1:
            raise InsightError('budget_exceeded', 'The tree exceeds the inspected file limit; no conclusion was returned.', 503)
        result = {}
        for row in rows:
            if not row:
                continue
            info, path = row.split(b'\t', 1)
            mode, kind, blob = info.split(b' ')
            name = os.fsdecode(path)
            if not self.excluded(name):
                result[name] = (mode.decode('ascii'), _sha(blob))
        self.trees[oid] = result
        return result

    def blob(self, entry):
        if entry is None:
            return b''
        mode, oid = entry
        if mode not in ('100644', '100755'):
            return None
        if oid not in self.blobs:
            size = int(self.run('cat-file', '-s', oid, limit=64))
            if size > MAX_BLOB:
                self.blobs[oid] = None
            else:
                self.blobs[oid] = self.run('cat-file', 'blob', oid, limit=MAX_BLOB+1)
        return self.blobs[oid]

    def working(self, source):
        root = Path(source['path']).resolve()
        top = Path(os.fsdecode(self.run('rev-parse', '--path-format=absolute', '--show-toplevel', path=root).strip())).resolve()
        if top != root or self.run('rev-parse', '--path-format=absolute', '--git-common-dir', path=root).strip() != self.identity:
            raise InsightError('unsafe_path', 'The registered worktree no longer resolves to the selected repository.', 409)
        head = _sha(self.run('rev-parse', '--verify', 'HEAD^{commit}', path=root))
        if head != source['oid']:
            raise InsightError('changed', 'The worktree HEAD changed; refresh and inspect again.', 409)
        raw = self.run('ls-files', '--stage', '-z', path=root)
        entries = {}
        for row in raw.split(b'\0'):
            if not row:
                continue
            info, path = row.split(b'\t', 1)
            mode, oid, stage = info.split(b' ')
            if stage != b'0':
                raise InsightError('conflicts', 'Resolve the index conflicts before inspecting remaining changes.', 409)
            name = os.fsdecode(path)
            if not self.excluded(name):
                entries[name] = (mode.decode('ascii'), _sha(oid))
        if source['kind'] == 'index':
            return entries, hashlib.sha256(raw).hexdigest()
        # Listing untracked paths and reading regular file bytes cannot execute
        # clean/smudge filters, fsmonitor hooks, or external diff programs.
        other = self.run('ls-files', '--others', '--exclude-standard', '-z', path=root)
        flags = self.run('ls-files', '-v', '-z', path=root)
        sparse = {os.fsdecode(row[2:]) for row in flags.split(b'\0') if row[:1] in (b'S', b's')}
        names = set(entries) | {os.fsdecode(p) for p in other.split(b'\0') if p and not self.excluded(os.fsdecode(p))}
        if len(names) > MAX_FILES:
            raise InsightError('budget_exceeded', f'Working-file inspection is limited to {MAX_FILES} non-excluded files; use a committed branch or narrow exclusions.', 503)
        result = {}
        filemode = self.run('config', '--bool', '--get', 'core.filemode', path=root, allow=(0, 1), limit=64) if os.name == 'nt' else b'true'
        for name in sorted(names):
            self.check()
            prior = entries.get(name)
            if prior and prior[0] == '160000':
                result[name] = prior  # Never descend into submodules.
                continue
            payload, mode = _read_regular(root, name, MAX_BLOB)
            if mode == 'missing':
                if name in sparse:
                    result[name] = ('unsupported', 'unreadable')
                continue
            if payload is None:
                # Sentinel is intentionally distinct from any real object id.
                result[name] = (mode, 'unreadable')
                continue
            self.consume(len(payload))
            oid = hashlib.new(self.object_format, b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
            self.blobs[oid] = payload
            # Git does not track executability on normal Windows filesystems.
            if filemode.strip() == b'false':
                mode = prior[0] if prior and prior[0] in ('100644', '100755') else '100644'
            result[name] = (mode, oid)
        stamp = hashlib.sha256(raw+other+flags+repr(sorted(result.items())).encode('utf-8', 'surrogateescape')).hexdigest()
        return result, stamp


def _read_regular(root, name, limit):
    """Open regular files without reading through links or outside the root."""
    parts = name.split('/')
    if any(part in ('', '.', '..') for part in parts) or name.startswith('/') or (os.name == 'nt' and any('\\' in p or ':' in p for p in parts)):
        return None, 'unsupported'
    if os.name == 'nt' and any(part.endswith((' ', '.')) or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.I) for part in parts):
        return None, 'unsupported'
    handles = []
    try:
        if os.name == 'posix':
            # Traverse the root itself from / without following links in any
            # ancestor. O_NOFOLLOW on only the last root component is not enough.
            parent = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            for part in root.parts[1:]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                handles.append(parent)
            for part in parts[:-1]:
                parent = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                handles.append(parent)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        else:
            # Open without consuming data, then validate the final handle path
            # before the first read. This also catches a junction/symlink race.
            current = root
            for part in parts:
                current /= part
                meta = current.lstat()
                if meta.st_file_attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
                    return None, 'unsupported'
            fd = os.open(current, os.O_RDONLY | os.O_BINARY)
        handles.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            return None, 'unsupported'
        if os.name == 'nt':
            import ctypes
            import msvcrt
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetFinalPathNameByHandleW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
            buffer = ctypes.create_unicode_buffer(32768)
            length = kernel.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(fd), buffer, len(buffer), 0)
            if not length or length >= len(buffer):
                return None, 'unsupported'
            final = buffer.value
            if final.startswith('\\\\?\\UNC\\'):
                final = '\\\\'+final[8:]
            elif final.startswith('\\\\?\\'):
                final = final[4:]
            if os.path.normcase(os.path.commonpath((str(root), final))) != os.path.normcase(str(root)):
                return None, 'unsupported'
        payload = bytearray()
        while len(payload) <= limit:
            chunk = os.read(fd, min(65536, limit+1-len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(fd)
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise InsightError('changed', 'A working file changed during inspection; refresh and try again.', 409)
        if len(payload) > limit:
            return None, 'unsupported'
        return bytes(payload), '100755' if before.st_mode & stat.S_IXUSR else '100644'
    except FileNotFoundError:
        return None, 'missing'
    except (OSError, ValueError):
        return None, 'unsupported'
    finally:
        for handle in reversed(handles):
            os.close(handle)


def _public(item):
    return {key: item[key] for key in ('id', 'label', 'kind', 'oid') if key in item}


def options(path, *, cancel_check=None):
    scan = Scan(path, cancel_check)
    inventory = scan.inventory()
    preferred = next((item['id'] for item in inventory['targets'] if item['ref'] in ('refs/heads/main', 'refs/heads/master')), None)
    return dict(sources=[_public(item) for item in inventory['sources']],
                targets=[_public(item) for item in inventory['targets']], default_target=preferred,
                warnings=['Some refs or stashes were omitted by the selection limit.'] if inventory['limited'] else [])


def _count(sequence, block):
    if not block:
        return 0
    count = 0
    for start in range(len(sequence)-len(block)+1):
        if sequence[start:start+len(block)] == block:
            count += 1
            if count > 1:
                break
    return count


def _classify(scan, before, desired, target):
    if desired == target and (desired is None or desired[0] in ('100644', '100755')):
        return 'present', 'The complete desired file bytes and Git mode match the target.'
    if any(entry and entry[0] not in ('100644', '100755') for entry in (before, desired, target)):
        return 'uncertain', 'Non-regular, unavailable, symlink, or submodule content is not compared.'
    old, new, current = (scan.blob(entry) for entry in (before, desired, target))
    if any(value is None or b'\0' in value for value in (old, new, current)):
        return 'uncertain', 'Binary or oversized content is not compared.'
    if before == target:
        return 'remaining', 'The target still matches the comparison base; the selected change is absent.'
    if desired is None or before is None or target is None:
        return 'uncertain', 'Addition/deletion overlaps a different target version; manual review is needed.'
    if old == new:
        return ('remaining', 'The selected file-mode change is absent from the target.') if current == new else ('uncertain', 'A mode-only change overlaps different target content.')
    if any(len(value.splitlines()) > MAX_LINES for value in (old, new, current)):
        return 'uncertain', 'This text file exceeds the bounded line-comparison limit.'
    a, b, c = [value.splitlines(keepends=True) for value in (old, new, current)]
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    flags = []
    for group in matcher.get_grouped_opcodes(3):
        scan.check()
        first, last = group[0], group[-1]
        old_block, new_block = a[first[1]:last[2]], b[first[3]:last[4]]
        old_count, new_count = _count(c, old_block), _count(c, new_block)
        flags.append('present' if new_count == 1 and old_count == 0 else
                     'remaining' if old_count == 1 and new_count == 0 else 'uncertain')
    if desired[0] != before[0]:
        flags.append('present' if target[0] == desired[0] else 'remaining' if target[0] == before[0] else 'uncertain')
    if not flags or 'uncertain' in flags:
        return 'uncertain', 'Changed blocks cannot be matched uniquely with their context; manual review is needed.'
    if all(flag == 'present' for flag in flags):
        return 'present', 'All selected change blocks match uniquely in the current target; unrelated target edits remain.'
    if all(flag == 'remaining' for flag in flags):
        return 'remaining', 'The original blocks match uniquely in the current target; the selected edits are absent.'
    return 'partial', 'Some selected change blocks are present and others are absent in the current target.'


def analyze(path, source_id, target_id, *, cancel_check=None, exclude_globs=()):
    scan = Scan(path, cancel_check, exclude_globs)
    inventory = scan.inventory()
    source = next((item for item in inventory['sources'] if item['id'] == source_id), None)
    target = next((item for item in inventory['targets'] if item['id'] == target_id), None)
    if source is None or target is None:
        raise InsightError('invalid_selection', 'Choose a source and target from the current local inspection options.', 409)
    if scan.run('rev-parse', '--is-shallow-repository').strip() != b'false':
        raise InsightError('incomplete_history', 'Shallow history cannot establish a complete comparison base.', 409)
    if source['kind'] in ('stash', 'stash_index'):
        base = _sha(scan.run('rev-parse', source['oid']+'^1'))
    else:
        bases = scan.run('merge-base', '--all', source['oid'], target['oid'], allow=(0, 1)).splitlines()
        if len(bases) != 1:
            raise InsightError('ambiguous_base', 'There is no single complete common base for this comparison.', 409)
        base = _sha(bases[0])
        if source['kind'] == 'branch' and base == source['oid'] and source['oid'] != target['oid']:
            raise InsightError('ambiguous_base', 'This source tip is already in target history. Its original change boundary is unknown, so an empty diff would not prove its changes still survive. Choose an unmerged branch or a stash.', 409)
    before, desired, current = scan.tree(base), scan.tree(source['oid']), scan.tree(target['oid'])
    working_stamp = None
    if source['kind'] in ('worktree', 'index'):
        desired, working_stamp = scan.working(source)
    elif source['kind'] == 'stash_index':
        desired = scan.tree(_sha(scan.run('rev-parse', source['oid']+'^2')))
    elif source['kind'] == 'stash':
        parents = scan.run('rev-list', '--parents', '-n', '1', source['oid']).split()
        if len(parents) == 4:
            desired = dict(desired)
            desired.update(scan.tree(_sha(parents[3])))
    names = sorted(name for name in set(before) | set(desired) if before.get(name) != desired.get(name))
    if len(names) > MAX_FILES:
        raise InsightError('budget_exceeded', f'This change exceeds the {MAX_FILES}-file inspection limit; no conclusion was returned.', 503)
    rows = []
    for name in names:
        state, explanation = _classify(scan, before.get(name), desired.get(name), current.get(name))
        rows.append(dict(path=name, integration=state, explanation=explanation,
                         preservation='unknown', saved_copies=[]))
    # Exact whole-file versions, across bounded tips/stashes/reflog commits.
    # These are locations in one Git object store, not independent backups.
    locations = [(item['label'], item['oid']) for item in inventory['refs'] + inventory['stashes']]
    for item in inventory['stashes']:
        parents = scan.run('rev-list', '--parents', '-n', '1', item['oid']).split()
        if len(parents) >= 3:
            locations.append((item['label']+' (staged files)', _sha(parents[2])))
        if len(parents) == 4:
            locations.append((item['label']+' (untracked files)', _sha(parents[3])))
    reflog_snapshot = scan.run('reflog', 'show', '--all', '-n', '4097', '--format=%H')
    reflog_raw = reflog_snapshot.splitlines()
    reflog = list(dict.fromkeys(reflog_raw))
    limited = inventory['limited'] or len(reflog) > MAX_REFLOG or len(reflog_raw) >= 4097
    seen = {oid for _, oid in locations}
    for raw in reflog[:MAX_REFLOG]:
        oid = _sha(raw)
        if oid not in seen:
            locations.append(('Reflog '+oid[:12], oid))
            seen.add(oid)
    saved = {}
    for label, oid in locations:
        for entry in set(scan.tree(oid).values()):
            if entry[0] in ('100644', '100755'):
                saved.setdefault(entry, []).append(label)
    for row in rows:
        entry = desired.get(row['path'])
        if entry is None or entry[0] not in ('100644', '100755') or entry[1] == 'unreadable':
            continue
        copies = saved.get(entry, [])
        if copies:
            row['preservation'] = 'matching_saved_version'
            row['saved_copies'] = copies[:6]
        elif not limited:
            row['preservation'] = 'no_matching_saved_version'
    if working_stamp is not None:
        _, after_stamp = scan.working(source)
        if after_stamp != working_stamp:
            raise InsightError('changed', 'Working files or the index changed during inspection; refresh and try again.', 409)
    if inventory['fingerprint'] != scan.inventory()['fingerprint'] or scan.identity != scan.run('rev-parse', '--path-format=absolute', '--git-common-dir').strip():
        raise InsightError('changed', 'Repository refs or worktrees changed during inspection; refresh and try again.', 409)
    if scan.run('reflog', 'show', '--all', '-n', '4097', '--format=%H') != reflog_snapshot:
        raise InsightError('changed', 'Saved reflog locations changed during inspection; refresh and try again.', 409)
    warnings = ['Content matches are textual evidence, not proof of equivalent behavior or safe deletion.',
                'Saved copies mean identical complete file bytes and Git mode in inspected Git states, not independent backups. No match does not prove the edits are unique.',
                'Saved-version search covers listed branch tips, stashes and recent reflog commits in this repository only. Other clones, other working files, older history and external backups are not searched.',
                'Remote branches are cached local refs; no network access or fetch was performed.']
    if source['kind'] in ('worktree', 'index') and base == source['oid'] and source['oid'] != target['oid']:
        warnings.append('The source HEAD is already in target history. This comparison covers only working/index changes after that HEAD; it does not establish whether earlier committed source changes still survive in the target.')
    if limited:
        warnings.append('Saved-state limits were reached. Unmatched files remain unknown rather than being reported without a saved copy.')
    if source['kind'] == 'worktree':
        warnings.append('Working files include tracked and non-ignored untracked files. Staged-only versions are separate: choose Staged files to inspect the index. Ignored files and submodule contents are excluded. Raw bytes are compared without Git content filters or line-ending conversion.')
    if source['kind'] == 'index':
        warnings.append('This selection includes the staged index; unstaged and untracked working files are not included.')
    if source['kind'] == 'stash':
        warnings.append('This selection includes the stash working-file version and saved untracked files. Staged-only stash versions are separate: choose the stash option marked staged files.')
    if source['kind'] == 'stash_index':
        warnings.append('This selection includes the stash staged-file version; the stash working-file version and untracked files are separate.')
    if scan.exclusions:
        warnings.append('Configured file exclusions were applied to all compared trees and working files.')
    counts = Counter(row['integration'] for row in rows)
    return dict(source=_public(source), target=_public(target), generated_at=datetime.now(timezone.utc).isoformat(),
                summary=dict(files=len(rows), **{key: counts[key] for key in ('present', 'remaining', 'partial', 'uncertain')},
                             no_matching_saved_version=sum(row['preservation']=='no_matching_saved_version' for row in rows)),
                files=rows, warnings=warnings,
                coverage=dict(base=base, source=source['oid'], target=target['oid'], saved_locations_checked=len(locations), files_checked=len(rows),
                              saved_search_limited=limited, commands=scan.commands, bytes_read=scan.bytes,
                              excludes=list(scan.exclusions), max_files=MAX_FILES, max_seconds=MAX_SECONDS))
