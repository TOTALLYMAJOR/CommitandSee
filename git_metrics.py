"""Read-only Git metrics for the local dashboard (Python standard library only).

History is non-merge commit churn reachable from one selected ref, grouped by
committer date. Branch comparisons use locally cached refs; this module never
fetches, pushes, edits an index, or executes a configured repository filter.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import functools
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if os.name == "nt":
    from windows_job import WindowsJob


UTC = dt.timezone.utc
MAX_OUTPUT = 64 * 1024 * 1024
COMMAND_TIMEOUT = 30
HISTORY_MARKER = b"GIT_DASH_COMMIT"
HISTORY_MODE = "non-merge commits reachable from selected ref"


class GitError(RuntimeError):
    """A Git observation failed or exceeded an explicit collection budget."""


def _text(value: bytes) -> str:
    return value.decode("utf-8", "replace")


def _iso(timestamp: float | None = None) -> str:
    value = dt.datetime.now(UTC) if timestamp is None else dt.datetime.fromtimestamp(timestamp, UTC)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    # A shell's temporary Git overrides must not redirect the configured path.
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_PREFIX", "GIT_NAMESPACE", "GIT_EXTERNAL_DIFF", "GIT_CONFIG",
                "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"):
        env.pop(key, None)
    for key in list(env):
        if key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
            env.pop(key)
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
               GIT_NO_LAZY_FETCH="1", GIT_PAGER="cat", LC_ALL="C", LANG="C")
    return env


def _run(command: list[str], *, input_data: bytes | None = None,
         limit: int = MAX_OUTPUT, timeout: float = COMMAND_TIMEOUT,
         environment: dict[str, str] | None = None) -> tuple[int, bytes, bytes]:
    """Bound output and cancel Git with its transport helpers, without a shell."""
    chunks: list[list[bytes]] = [[], []]
    overflow = threading.Event()
    stdin_file = tempfile.TemporaryFile() if input_data is not None else None
    if stdin_file is not None:
        stdin_file.write(input_data)
        stdin_file.seek(0)
    # Git can spawn remote helpers which outlive a killed Git parent and retain
    # its output pipes. Give ordinary descendants one cancellation boundary.
    process_options = {"start_new_session": True} if os.name == "posix" else {}
    job = None
    try:
        if os.name == "nt":
            job = WindowsJob()
        start = job.start if job is not None else subprocess.Popen
        process = start(command, stdin=stdin_file or subprocess.DEVNULL,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=_environment() if environment is None else environment,
                        **process_options)
    except (OSError, ValueError) as exc:
        if job is not None:
            job.close()
        if stdin_file is not None:
            stdin_file.close()
        raise GitError(f"Cannot run Git: {exc}") from exc

    cancellation_lock = threading.Lock()
    cancelled = False

    def cancel_tree() -> None:
        nonlocal cancelled
        with cancellation_lock:
            if cancelled:
                return
            cancelled = True
            if os.name == "posix":
                try:
                    # Do this even if the group leader exited: its helpers may
                    # still be alive with inherited stdout/stderr handles.
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif job is not None:
                job.terminate()
                return  # TerminateJobObject already includes the parent.
            try:
                process.kill()
            except ProcessLookupError:
                pass

    def drain(pipe, index: int, budget: int) -> None:
        total = 0
        try:
            while True:
                piece = pipe.read1(65536)
                if not piece:
                    break
                remaining = budget - total
                if remaining > 0:
                    chunks[index].append(piece[:remaining])
                total += len(piece)
                if total > budget:
                    overflow.set()
                    cancel_tree()
                    break
        finally:
            pipe.close()

    readers = []
    owned_pipes = set()
    try:
        for pipe, index, budget in ((process.stdout, 0, limit), (process.stderr, 1, 256 * 1024)):
            reader = threading.Thread(target=drain, args=(pipe, index, budget), daemon=True)
            reader.start()
            readers.append(reader)
            owned_pipes.add(pipe)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            cancel_tree()
            raise GitError(f"Git command exceeded {timeout:g} seconds") from exc
        # A process can exit before its readers drain the final pipe buffers.
        # Join before inspecting overflow or constructing the returned bytes.
        for reader in readers:
            reader.join(timeout=2)
        if any(reader.is_alive() for reader in readers):
            raise GitError("Git output could not be fully collected")
        if overflow.is_set():
            raise GitError("Git output exceeded the collection budget")
        return code, b"".join(chunks[0]), b"".join(chunks[1])
    finally:
        try:
            if process.poll() is None or any(reader.is_alive() for reader in readers):
                cancel_tree()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired as exc:
                raise GitError("Git process could not be terminated") from exc
            for reader in readers:
                reader.join(timeout=2)
        finally:
            if job is not None:
                job.close()
                process.close()
            # A failed Thread.start leaves its pipe without a reader owner.
            for pipe in (process.stdout, process.stderr):
                if pipe not in owned_pipes and not pipe.closed:
                    pipe.close()
            if stdin_file is not None:
                stdin_file.close()


@functools.lru_cache(maxsize=1)
def _git_capabilities() -> tuple[str, bool]:
    code, raw, err = _run(["git", "--version"], limit=16384)
    match = re.search(rb"git version (\d+)\.(\d+)", raw)
    if code or not match:
        raise GitError("Git is unavailable: " + _text(err).strip()[:300])
    version = tuple(map(int, match.groups()))
    if version < (2, 37):
        raise GitError("Git 2.37 or newer is required for date filtering and safe fsmonitor disabling")
    code, _, _ = _run(["git", "--no-lazy-fetch", "--version"], limit=16384)
    return _text(raw).strip(), code == 0


class _Git:
    def __init__(self, path: Path, no_lazy_fetch: bool):
        self.path = path
        self.prefix = ["git", "--no-optional-locks"]
        if no_lazy_fetch:
            self.prefix.append("--no-lazy-fetch")
        self.prefix += ["-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                        "-c", "diff.autoRefreshIndex=false", "-c", "diff.external=",
                        "-c", "log.showSignature=false",
                        "-c", "submodule.recurse=false", "-c", "color.ui=false", "-C", str(path)]
        self.warnings: list[str] = []

    def run(self, *args: str, input_data: bytes | None = None,
            allow: Iterable[int] = (0,), limit: int = MAX_OUTPUT) -> bytes:
        code, out, err = _run(self.prefix + list(args), input_data=input_data, limit=limit)
        message = _text(err).strip()
        if code not in allow:
            raise GitError(f"git {args[0]} failed: {message[:700] or f'exit {code}'}")
        if code == 0 and message and message not in self.warnings:
            self.warnings.append(message[:700])
        return out


def _excluded(path: bytes, patterns: Iterable[str]) -> bool:
    label = _text(path)
    return any(fnmatch.fnmatchcase(label, pattern) for pattern in patterns)


def _numstat_record(tokens: list[bytes], position: int) -> tuple[dict, int]:
    token = tokens[position].lstrip(b"\n")
    parts = token.split(b"\t", 2)
    if len(parts) != 3 or not all(p == b"-" or p.isdigit() for p in parts[:2]):
        raise GitError("Unrecognized NUL-delimited numstat record")
    added, deleted, path = parts
    if (added == b"-") != (deleted == b"-"):
        raise GitError("Inconsistent binary numstat record")
    previous = None
    position += 1
    if path == b"":
        if position + 1 >= len(tokens):
            raise GitError("Incomplete NUL-delimited rename record")
        previous, path = tokens[position:position + 2]
        position += 2
    if not path:
        raise GitError("Empty path in numstat output")
    return {"path": path, "old_path": previous,
            "added": None if added == b"-" else int(added),
            "deleted": None if deleted == b"-" else int(deleted),
            "binary": added == b"-"}, position


def parse_numstat(data: bytes, exclude_globs: Iterable[str] | None = None) -> dict:
    """Aggregate -z numstat, including binary and two-path rename records."""
    patterns = tuple(exclude_globs or ())
    totals = {"added": 0, "deleted": 0, "binary_files": 0, "files": 0}
    tokens = data.split(b"\0")
    position = 0
    while position < len(tokens):
        if tokens[position] in (b"", b"\n"):
            position += 1
            continue
        record, position = _numstat_record(tokens, position)
        if _excluded(record["path"], patterns):
            continue
        totals["files"] += 1
        if record["binary"]:
            totals["binary_files"] += 1
        else:
            totals["added"] += record["added"]
            totals["deleted"] += record["deleted"]
    return totals


def parse_log_numstat(data: bytes, exclude_globs: Iterable[str] | None = None) -> list[dict]:
    """Read our NUL-delimited commit headers and Git's NUL numstat records."""
    patterns = tuple(exclude_globs or ())
    tokens = data.split(b"\0")
    records: list[dict] = []
    current = None
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if token in (b"", b"\n"):
            position += 1
            continue
        if token.lstrip(b"\n") == HISTORY_MARKER:
            if position + 3 >= len(tokens):
                raise GitError("Incomplete history header")
            sha, epoch, subject = tokens[position + 1:position + 4]
            if not re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", sha) or not epoch.isdigit():
                raise GitError("Invalid history identity or timestamp")
            current = {"sha": _text(sha), "epoch": int(epoch), "subject": _text(subject),
                       "added": 0, "deleted": 0, "binary_changes": 0}
            records.append(current)
            position += 4
            continue
        if current is None:
            raise GitError("File statistics occurred before a commit header")
        record, position = _numstat_record(tokens, position)
        if _excluded(record["path"], patterns):
            continue
        if record["binary"]:
            current["binary_changes"] += 1
        else:
            current["added"] += record["added"]
            current["deleted"] += record["deleted"]
    return records


def parse_status(data: bytes) -> list[dict]:
    """Parse porcelain v2 -z without treating spaces/newlines as path separators."""
    tokens = data.split(b"\0")
    files: list[dict] = []
    position = 0
    while position < len(tokens):
        token = tokens[position]
        position += 1
        if not token or token.startswith(b"# "):
            continue
        if token.startswith(b"? "):
            files.append({"path": _text(token[2:]), "index": "?", "worktree": "?",
                          "kind": "untracked", "_path": token[2:]})
            continue
        if token.startswith(b"! "):
            continue
        count = {b"1": 8, b"2": 9, b"u": 10}.get(token[:1])
        if count is None:
            raise GitError("Unrecognized porcelain v2 status record")
        fields = token.split(b" ", count)
        if len(fields) != count + 1 or len(fields[1]) != 2:
            raise GitError("Incomplete porcelain v2 status record")
        kind = "conflict" if token.startswith(b"u ") else "tracked"
        record = {"path": _text(fields[-1]), "index": chr(fields[1][0]),
                  "worktree": chr(fields[1][1]), "kind": kind,
                  "submodule": _text(fields[2]), "_path": fields[-1]}
        if token.startswith(b"2 "):
            if position >= len(tokens) or not tokens[position]:
                raise GitError("Missing original path in rename status")
            record["old_path"] = _text(tokens[position])
            record["_old_path"] = tokens[position]
            record["kind"] = "copied" if fields[-2].startswith(b"C") else "renamed"
            position += 1
        files.append(record)
    return files


def _stat(path: Path) -> tuple | None:
    try:
        stat = path.lstat()
        return stat.st_mode, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino
    except FileNotFoundError:
        return None


def _file_fingerprints(root: Path, files: list[dict]) -> list:
    records = []
    for item in files:
        for field in ("_path", "_old_path"):
            if field in item:
                raw = item[field]
                records.append((raw, _stat(root / os.fsdecode(raw))))
    return records


def _active_content_filters(git: _Git) -> bool:
    """Only refuse filters actually assigned to a tracked/untracked path.

    Git for Windows often configures LFS globally even in non-LFS repositories.
    Attribute queries and ls-files do not run the clean/process command.
    """
    config = git.run("config", "--null", "--get-regexp", r"^filter\..*\.(clean|process)$", allow=(0, 1))
    drivers = set()
    for record in config.split(b"\0"):
        if b"\n" not in record:
            continue
        key, command = record.split(b"\n", 1)
        if command.strip():
            drivers.add(key[len(b"filter."):].rsplit(b".", 1)[0])
    if not drivers:
        return False
    paths = git.run("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if not paths:
        return False
    attributes = git.run("check-attr", "-z", "--stdin", "filter", input_data=paths).split(b"\0")
    if attributes and attributes[-1] == b"":
        attributes.pop()
    if len(attributes) % 3:
        raise GitError("Incomplete filter attribute observation")
    return any(attributes[index + 2] in drivers for index in range(0, len(attributes), 3))


def _working_head(git: _Git) -> str | None:
    raw = git.run("rev-parse", "--verify", "HEAD^{commit}", allow=(0, 128))
    return _text(raw).strip() or None


def _worktree(git: _Git, metadata: dict, patterns: tuple[str, ...]) -> dict:
    result = {"path": str(git.path), "branch": metadata.get("branch"),
              "head": metadata.get("HEAD"), "status": "error", "staged": None,
              "unstaged": None, "untracked": None, "conflicts": None, "dirty": None,
              "files": [], "loc": {"staged": None, "unstaged": None, "net": None},
              "errors": [], "fingerprint": None}
    try:
        if not git.path.is_dir():
            raise GitError("Registered worktree path is missing or inaccessible")
        if _active_content_filters(git):
            raise GitError("Working-tree scan unavailable: an executable clean/process filter applies; no filter was run")
        # Status can otherwise invoke a child's filters while looking for dirty
        # submodule contents. Observe gitlink changes, but leave each child's
        # working-tree contents to a separately configured repository scan.
        staged_paths = git.run("ls-files", "--stage", "-z")
        submodules = sorted({_text(item.partition(b"\t")[2])
                             for item in staged_paths.split(b"\0") if item.startswith(b"160000 ")})
        result["submodule_paths"] = submodules
        index = Path(os.fsdecode(git.run("rev-parse", "--path-format=absolute", "--git-path", "index").rstrip(b"\n")))
        diff_options = ("--numstat", "-z", "--find-renames", "-l1000", "--no-ext-diff", "--no-textconv",
                        "--ignore-submodules=dirty", "--submodule=short")
        status_options = ("status", "--porcelain=v2", "-z", "--untracked-files=all", "--ignore-submodules=dirty")
        for attempt in range(2):
            head = _working_head(git)
            before = (head, _stat(index))
            raw_status = git.run(*status_options)
            files = parse_status(raw_status)
            fingerprints = _file_fingerprints(git.path, files)
            conflicts = sum(item["kind"] == "conflict" for item in files)
            loc = {"staged": None, "unstaged": None, "net": None}
            metric_errors = []
            if conflicts:
                metric_errors.append("LOC unavailable while merge conflicts are present")
            else:
                # No HEAD in an unborn repository: the staged comparison is to
                # Git's empty tree; --cached without a commit handles this.
                commands = {
                    "staged": ("diff", "--cached", *diff_options, "--"),
                    "unstaged": ("diff", *diff_options, "--"),
                    "net": (("diff", *diff_options, head, "--") if head else None),
                }
                for kind, command in commands.items():
                    if command is None:
                        metric_errors.append("Net tracked LOC unavailable before the first commit; staged and unstaged counts remain separate")
                        continue
                    try:
                        loc[kind] = parse_numstat(git.run(*command), patterns)
                    except GitError as exc:
                        metric_errors.append(f"{kind} LOC: {exc}")
            after_files = _file_fingerprints(git.path, files)
            after_status = git.run(*status_options)
            after = (_working_head(git), _stat(index))
            if before != after or raw_status != after_status or fingerprints != after_files:
                if attempt == 0:
                    continue
                raise GitError("Inconsistent observation: HEAD, index, or files changed during both scan attempts")
            result.update(head=head, status="partial" if metric_errors else "ok",
                          staged=sum(item["kind"] != "conflict" and item["index"] not in (".", "?") for item in files),
                          unstaged=sum(item["kind"] != "conflict" and item["worktree"] not in (".", "?") for item in files),
                          untracked=sum(item["kind"] == "untracked" for item in files),
                          conflicts=conflicts, dirty=bool(files), loc=loc,
                          files=[{key: value for key, value in item.items() if not key.startswith("_")} for item in files])
            result["errors"].extend(metric_errors)
            material = repr((before, fingerprints)).encode("utf-8", "backslashreplace") + raw_status
            result["fingerprint"] = hashlib.sha256(material).hexdigest()
            if submodules:
                result["errors"].append("Nested submodule contents are not scanned; configure each submodule separately for working-tree status and LOC")
                result["status"] = "partial"
                if not files:
                    result["dirty"] = None
            if git.warnings:
                result["errors"].extend("Git warning: " + warning for warning in git.warnings)
                result["status"] = "partial"
            return result
    except (GitError, OSError, ValueError) as exc:
        result["errors"].append(str(exc))
    return result


def _registered_worktrees(git: _Git) -> list[dict]:
    records = []
    current = {}
    for token in git.run("worktree", "list", "--porcelain", "-z").split(b"\0"):
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = token.partition(b" ")
        current[_text(key)] = _text(value) if value else True
    if current:
        records.append(current)
    return records


def _history(git: _Git, *, ref: str, head: str | None, days: int, zone,
             zone_name: str, now: dt.datetime, max_commits: int,
             patterns: tuple[str, ...], shallow: bool) -> dict:
    today = now.astimezone(zone).date()
    start = today - dt.timedelta(days=days - 1)
    cutoff = dt.datetime.combine(start, dt.time.min, zone)
    daily = {str(start + dt.timedelta(days=i)): {"date": str(start + dt.timedelta(days=i)),
             "commits": 0, "added": 0, "deleted": 0} for i in range(days)}
    result = {"ref": ref, "head": head, "days": days, "timezone": zone_name,
              "mode": HISTORY_MODE, "commits": 0, "total_added": 0, "total_deleted": 0,
              "binary_changes": 0, "truncated": False, "shallow": shallow,
              "daily": [], "weekly": [], "recent": []}
    records = []
    if head:
        # Shallow boundaries look like roots to Git; their full trees are not new work.
        # Omit parentless deltas in shallow histories and retain the partial marker.
        raw = git.run("-c", "log.showRoot=false" if shallow else "log.showRoot=true",
                      "log", "--no-merges", "--numstat", "-z", "--find-renames", "-l1000",
                      "--no-ext-diff", "--no-textconv", "--submodule=short",
                      f"--since-as-filter={cutoff.isoformat()}", f"--max-count={max_commits + 1}",
                      "--format=%x00GIT_DASH_COMMIT%x00%H%x00%ct%x00%s%x00", head, "--")
        records = parse_log_numstat(raw, patterns)
        result["truncated"] = len(records) > max_commits
        records = records[:max_commits]
    eligible = []
    for record in records:
        timestamp = dt.datetime.fromtimestamp(record["epoch"], UTC)
        day = timestamp.astimezone(zone).date()
        if not (start <= day <= today) or timestamp > now:
            continue
        bucket = daily[str(day)]
        bucket["commits"] += 1
        for field in ("added", "deleted"):
            bucket[field] += record[field]
            result["total_" + field] += record[field]
        result["commits"] += 1
        result["binary_changes"] += record["binary_changes"]
        eligible.append(record)
    weeks = {}
    for key, bucket in daily.items():
        day = dt.date.fromisoformat(key)
        monday = str(day - dt.timedelta(days=day.weekday()))
        week = weeks.setdefault(monday, {"date": monday, "commits": 0, "added": 0, "deleted": 0})
        for field in ("commits", "added", "deleted"):
            week[field] += bucket[field]
    result["daily"] = list(daily.values())
    result["weekly"] = list(weeks.values())
    for record in sorted(eligible, key=lambda item: item["epoch"], reverse=True)[:60]:
        result["recent"].append({key: value for key, value in record.items() if key != "epoch"}
                                | {"timestamp": _iso(record["epoch"])})
    return result


def _branches(git: _Git, head: str | None, now: dt.datetime, shallow: bool,
              stale_days: int) -> tuple[list[dict], list[dict]]:
    fmt = "%(refname)%00%(refname:short)%00%(objectname)%00%(committerdate:unix)%00%(upstream)%00%(upstream:short)%00%(upstream:track)%00%(symref)%00"
    raw = git.run("for-each-ref", f"--format={fmt}", "refs/heads", "refs/remotes")
    tokens = raw.split(b"\0")
    rows = []
    position = 0
    while position < len(tokens):
        if tokens[position] in (b"", b"\n"):
            position += 1
            continue
        if position + 7 >= len(tokens):
            raise GitError("Incomplete branch metadata")
        values = tokens[position:position + 8]
        values[0] = values[0].lstrip(b"\n")
        rows.append(values)
        position += 8
    merged = None
    if head:
        merged = set(git.run("for-each-ref", f"--merged={head}", "--format=%(refname)",
                             "refs/heads", "refs/remotes").splitlines())
    local, remote = [], []
    ref_shas = {values[0]: values[2] for values in rows}
    for full, name, sha, epoch, upstream, upstream_short, track, symbolic in rows:
        if symbolic:
            continue
        timestamp = int(epoch) if epoch.isdigit() else None
        age = max(0.0, (now.timestamp() - timestamp) / 86400) if timestamp is not None else None
        is_merged = None if merged is None or timestamp is None else full in merged
        if is_merged is False and shallow:
            is_merged = None
        record = {"name": _text(name), "sha": _text(sha),
                  "committed_at": _iso(timestamp) if timestamp is not None else None,
                  "age_days": round(age, 2) if age is not None else None,
                  "merged_into_ref": is_merged,
                  "stale": age is not None and age >= stale_days}
        if full.startswith(b"refs/remotes/"):
            remote.append(record)
            continue
        state, ahead, behind = "missing", None, None
        if upstream:
            if b"gone" in track:
                state = "gone"
            elif not track or re.fullmatch(rb"\[(?:ahead \d+|behind \d+|ahead \d+, behind \d+)\]", track):
                state = "cached"
                a, b = re.search(rb"ahead (\d+)", track), re.search(rb"behind (\d+)", track)
                ahead, behind = int(a[1]) if a else 0, int(b[1]) if b else 0
            else:
                state = "unknown"
        if shallow and state == "cached" and ref_shas.get(upstream) != sha:
            # Different tips can have an unseen common history beyond a
            # shallow boundary. Equality remains an exact zero/zero result.
            state, ahead, behind = "unknown", None, None
        record.update(upstream=_text(upstream_short) or None, upstream_ref=_text(upstream) or None,
                      upstream_state=state, ahead=ahead, behind=behind)
        local.append(record)
    return local, remote


def _stashes(git: _Git) -> list[dict]:
    tokens = git.run("stash", "list", "--format=%gd%x00%H%x00%ct%x00%s%x00").split(b"\0")
    result = []
    position = 0
    while position < len(tokens):
        if tokens[position] in (b"", b"\n"):
            position += 1
            continue
        if position + 3 >= len(tokens):
            raise GitError("Incomplete stash observation")
        ref, sha, epoch, subject = tokens[position:position + 4]
        if not epoch.isdigit():
            raise GitError("Invalid stash timestamp")
        result.append({"ref": _text(ref.lstrip(b"\n")), "sha": _text(sha),
                       "timestamp": _iso(int(epoch)), "subject": _text(subject)})
        position += 4
    return result


def collect_repository(path, *, name=None, ref="HEAD", days=180,
                       timezone="America/Chicago", max_commits=20000,
                       stale_days=14, exclude_globs=None, include_history=True) -> dict:
    """Collect one clone and its registered worktrees without fetching or writing.

    `include_history=False` lets the caller cache history by HEAD, settings and
    calendar date. Missing evidence is represented by null fields and errors.
    The caller should deduplicate clones by `id`/`common_dir` before aggregation.
    """
    now = dt.datetime.now(UTC)
    result = {"id": None, "name": name or Path(path).name or str(path), "path": str(path),
              "common_dir": None, "ref": ref, "head": None, "collected_at": _iso(now.timestamp()),
              "status": "error", "errors": [], "warnings": [], "history": None,
              "worktrees": [], "branches": [], "remote_branches": [], "stashes": [],
              "fetch_head_updated_at": None,
              "source_status": {"history": "not_requested" if not include_history else "unknown",
                                "worktrees": "unknown", "branches": "unknown", "stashes": "unknown"}}
    try:
        if not isinstance(ref, str) or not ref or "\0" in ref:
            raise GitError("A nonempty Git ref is required")
        days, max_commits, stale_days = int(days), int(max_commits), int(stale_days)
        if not 1 <= days <= 3660 or not 1 <= max_commits <= 100000 or stale_days < 0:
            raise GitError("Use days 1..3660, max_commits 1..100000, and a nonnegative stale_days")
        patterns = tuple(exclude_globs or ())
        if not all(isinstance(pattern, str) for pattern in patterns):
            raise GitError("exclude_globs must contain strings")
        directory = Path(path).expanduser().resolve()
        result["path"] = str(directory)
        version, no_lazy_fetch = _git_capabilities()
        result["git_version"] = version
        git = _Git(directory, no_lazy_fetch)
        common = Path(os.fsdecode(git.run("rev-parse", "--path-format=absolute", "--git-common-dir").rstrip(b"\n"))).resolve()
        result.update(common_dir=str(common), id=hashlib.sha256(os.fsencode(common)).hexdigest()[:20])
        # Older versions do not honor --no-lazy-fetch. Refuse promisor-backed
        # repositories there instead of accidentally acquiring missing objects.
        partial_config = git.run("config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$", allow=(0, 1))
        if partial_config.strip() and not no_lazy_fetch:
            raise GitError("This partial clone requires a Git version supporting --no-lazy-fetch")
        shallow = git.run("rev-parse", "--is-shallow-repository").strip() == b"true"
        if shallow:
            result["warnings"].append("Shallow clone: history is incomplete and negative ancestry comparisons are unknown")
        try:
            zone = UTC if timezone == "UTC" else ZoneInfo(timezone)
            zone_name = timezone
        except (ZoneInfoNotFoundError, ValueError):
            zone, zone_name = UTC, "UTC"
            result["warnings"].append(f"Timezone {timezone!r} unavailable; history buckets use UTC")
        head = None
        valid_ref = True
        try:
            head = _text(git.run("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}" )).strip()
        except GitError as exc:
            heads = git.run("for-each-ref", "--format=%(refname)", "refs/heads")
            if ref == "HEAD" and not heads.strip() and _working_head(git) is None:
                result["warnings"].append("Unborn repository: no commit history yet")
            else:
                valid_ref = False
                result["errors"].append(f"history ref: {exc}")
        result["head"] = head
        if include_history and valid_ref:
            try:
                result["history"] = _history(git, ref=ref, head=head, days=days, zone=zone,
                                             zone_name=zone_name, now=now, max_commits=max_commits,
                                             patterns=patterns, shallow=shallow)
                partial = result["history"]["truncated"] or shallow
                result["source_status"]["history"] = "partial" if partial else "ok"
                if result["history"]["truncated"]:
                    result["warnings"].append(f"History limited to {max_commits:,} selected commits; totals are partial")
            except (GitError, OSError, ValueError, OverflowError) as exc:
                result["source_status"]["history"] = "error"
                result["errors"].append(f"history: {exc}")
        elif include_history:
            result["source_status"]["history"] = "error"
        try:
            metadata = _registered_worktrees(git)
            seen = set()
            for item in metadata:
                if item.get("bare"):
                    result["warnings"].append("Bare repository has no working tree to scan")
                    continue
                workpath = Path(item["worktree"]).resolve()
                if str(workpath) in seen:
                    continue
                seen.add(str(workpath))
                if isinstance(item.get("branch"), str):
                    item["branch"] = item["branch"].removeprefix("refs/heads/")
                observation = _worktree(_Git(workpath, no_lazy_fetch), item, patterns)
                result["worktrees"].append(observation)
            result["source_status"]["worktrees"] = "partial" if any(w["status"] != "ok" for w in result["worktrees"]) else "ok"
        except (GitError, OSError, ValueError, KeyError) as exc:
            result["source_status"]["worktrees"] = "error"
            result["errors"].append(f"worktrees: {exc}")
        try:
            result["branches"], result["remote_branches"] = _branches(git, head, now, shallow, stale_days)
            result["source_status"]["branches"] = "ok"
        except (GitError, ValueError, OverflowError) as exc:
            result["source_status"]["branches"] = "error"
            result["errors"].append(f"branches: {exc}")
        try:
            result["stashes"] = _stashes(git)
            result["source_status"]["stashes"] = "ok"
        except (GitError, ValueError, OverflowError) as exc:
            result["source_status"]["stashes"] = "error"
            result["errors"].append(f"stashes: {exc}")
        try:
            # This is an informational file mtime, not remote-data freshness.
            fetch_file = Path(os.fsdecode(git.run("rev-parse", "--path-format=absolute", "--git-path", "FETCH_HEAD").rstrip(b"\n")))
            if fetch_file.is_file():
                result["fetch_head_updated_at"] = _iso(fetch_file.stat().st_mtime)
        except (OSError, GitError):
            pass
        result["warnings"].extend(git.warnings)
        result["warnings"].append("Remote comparisons use cached local refs; no fetch or GitHub PR lookup was performed")
        result["status"] = "partial" if result["errors"] or any(s in ("error", "partial") for s in result["source_status"].values()) else "ok"
    except (GitError, OSError, ValueError, TypeError) as exc:
        result["errors"].append(str(exc))
    return result
