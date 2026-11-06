"""Account-bound GitHub history with credentials confined to one fetch process."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from git_metrics import _Git, _git_capabilities, _history, _run, GitError
from public_repositories import PublicGit, public_url


class AuthenticatedRepositoryError(ValueError):
    """An intentionally safe, locally authored diagnostic."""


def _identity(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2 ** 63:
        raise AuthenticatedRepositoryError("GitHub repository/account/installation identity is invalid.")
    return value


def _overlaps(left, right):
    return left.is_relative_to(right) or right.is_relative_to(left)


def validate_cache_root(cache_root, config):
    """Resolve every local Git identity before permitting any private-cache write."""
    base = Path(cache_root).expanduser()
    if base.is_symlink():
        raise AuthenticatedRepositoryError("Authenticated cache root must not be a symlink.")
    base = base.resolve()
    _, lazy = _git_capabilities()
    for item in config.get("repositories", []):
        if item.get("url") or item.get("source_kind") in {"public", "github"}:
            continue
        try:
            configured = Path(item["path"]).expanduser().resolve()
            git = _Git(configured, lazy)
            roots = {configured,
                     Path(os.fsdecode(git.run("rev-parse", "--show-toplevel")).strip()).resolve(),
                     Path(os.fsdecode(git.run("rev-parse", "--path-format=absolute", "--git-common-dir")).strip()).resolve()}
            for field in git.run("worktree", "list", "--porcelain", "-z").split(b"\0"):
                if field.startswith(b"worktree "):
                    roots.add(Path(os.fsdecode(field[9:])).resolve())
        except Exception:
            raise AuthenticatedRepositoryError(
                "Cannot verify private-cache containment while a configured local repository is unavailable.") from None
        if any(_overlaps(base, root) for root in roots):
            raise AuthenticatedRepositoryError("Authenticated cache overlaps a monitored local repository.")
    return base


def _regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise AuthenticatedRepositoryError("Authenticated cache contains an unsafe file link.")


def _cache_directory(base, account_id, repository_id):
    identity = {"version": 1, "github_account_id": account_id, "github_repository_id": repository_id}
    name = hashlib.sha256(f"{account_id}:{repository_id}".encode("ascii")).hexdigest()
    cache = base / name
    if base.is_symlink() or cache.is_symlink():
        raise AuthenticatedRepositoryError("Authenticated cache must not be a symlink.")
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache.mkdir(exist_ok=True, mode=0o700)
    if cache.resolve().parent != base.resolve():
        raise AuthenticatedRepositoryError("Authenticated cache escaped its storage root.")
    if os.name == "posix" and (cache.stat().st_uid != os.getuid() or cache.stat().st_mode & 0o077):
        raise AuthenticatedRepositoryError("Authenticated cache must be private to the current local user.")
    marker = cache / "work-visibility-cache.json"
    if not marker.exists() and not marker.is_symlink():
        if any(cache.iterdir()):
            raise AuthenticatedRepositoryError("Authenticated cache is not owned by this monitor.")
        try:
            descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(identity, output)
        except FileExistsError:
            pass  # A concurrent observer must have written the identical marker.
    _regular_file(marker)
    with marker.open("rb") as source:
        raw = source.read(1024)
    if len(raw) >= 1024 or json.loads(raw) != identity:
        raise AuthenticatedRepositoryError("Authenticated cache identity does not match this account and repository.")
    # Git writes FETCH_HEAD and nested refs as well as the obvious config files.
    # Validate the whole existing cache before handing it to a write-capable Git
    # command; following just a small list of paths misses hardlink escapes.
    pending, entries = [cache], 0
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            entries += 1
            if entries > 100000:
                raise AuthenticatedRepositoryError("Authenticated cache exceeds the file validation budget.")
            info = path.lstat()
            # Windows junctions are reparse points but not symlinks. Inspect
            # attributes directly so Python 3.10/3.11 also reject them.
            if path.is_symlink() or (getattr(info, "st_file_attributes", 0)
                                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise AuthenticatedRepositoryError("Authenticated cache contains an unsafe path link.")
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise AuthenticatedRepositoryError("Authenticated cache contains an unsafe file link.")
    for relative in (".git", "commondir", "config.worktree", "objects/info/alternates", "objects/info/http-alternates"):
        path = cache / relative
        if path.exists() or path.is_symlink():
            raise AuthenticatedRepositoryError("Authenticated cache cannot share another Git directory or object store.")
    return cache


class AuthenticatedGit(PublicGit):
    def __init__(self, path):
        super().__init__(path)
        self.environment = {key: value for key, value in self.environment.items()
                            if not key.startswith(("GH_", "GITHUB_", "SSH_"))}
        self.prefix += ["-c", "core.askPass=", "-c", "credential.interactive=false",
                        "-c", "http.cookieFile=", "-c", "http.saveCookies=false"]

    def run(self, *args, **kwargs):
        try:
            code, out, _ = _run(self.prefix + list(args), environment=self.environment, **kwargs)
        except Exception:
            raise GitError("Authenticated Git command failed.") from None
        if code:
            raise GitError("Authenticated Git command failed.")
        return out

    def validate_config(self):
        # Reject custom URL rewrites, includes, per-URL headers and executable
        # configuration rather than trying to guess every override they imply.
        allowed = {"core.repositoryformatversion": {"0"}, "core.bare": {"true"},
                   "core.filemode": {"true", "false"}, "core.logallrefupdates": {"true", "false"},
                   "core.ignorecase": {"true", "false"}, "core.precomposeunicode": {"true", "false"},
                   "core.symlinks": {"true", "false"}}
        _regular_file(self.path / "config")
        found = {}
        for entry in self.run("config", "--local", "--no-includes", "--null", "--list").split(b"\0"):
            if not entry:
                continue
            key, separator, value = entry.partition(b"\n")
            key, value = key.decode("utf-8"), value.decode("utf-8").lower()
            if not separator or key not in allowed or value not in allowed[key] or key in found:
                raise AuthenticatedRepositoryError("Authenticated cache Git configuration was modified; collection is blocked.")
            found[key] = value
        if found.get("core.bare") != "true" or found.get("core.repositoryformatversion") != "0":
            raise AuthenticatedRepositoryError("Authenticated cache is not a supported bare Git repository.")
        if Path(os.fsdecode(self.run("rev-parse", "--absolute-git-dir")).strip()).resolve() != self.path.resolve():
            raise AuthenticatedRepositoryError("Authenticated cache Git directory does not match its storage path.")

    def fetch(self, url, branch, token, cancel_check):
        if not isinstance(token, str) or not token or any(c in token for c in "\r\n\0"):
            raise GitError("GitHub authorization is unavailable.")
        environment = dict(self.environment)
        header = "Authorization: Basic " + base64.b64encode(("x-access-token:" + token).encode()).decode("ascii")
        environment.update(GIT_CONFIG_COUNT="1",
                           GIT_CONFIG_KEY_0=f"http.{url}.git.extraHeader", GIT_CONFIG_VALUE_0=header)
        try:
            command = self.prefix + ["fetch", "--quiet", "--depth=2000", "--no-tags",
                "--no-recurse-submodules", "--no-auto-maintenance", "--", url + ".git",
                "+refs/heads/" + branch + ":refs/heads/observed"]
            code, _, _ = _run(command, environment=environment, cancel_check=cancel_check)
            if code:
                raise GitError("Authenticated Git fetch failed.")
        except Exception:
            raise GitError("Authenticated Git fetch failed or was cancelled.") from None
        finally:
            environment.clear()


def collect_authenticated(item, cache_root, config, auth):
    now = datetime.now(timezone.utc)
    result = {key: item[key] for key in ("name", "product", "exclude_globs", "github_repository_id",
               "github_account_id", "installation_id") if key in item}
    result.update(id="", path="", url="", source_kind="github", private=None,
        collected_at=now.isoformat(), status="error", errors=[],
        warnings=["Authenticated default-branch history only. Local work, unpublished commits, PRs and CI are not observed."],
        history=None, head=None, ref="HEAD", worktrees=[], branches=[], remote_branches=[], stashes=[],
        source_status={"history": "error", "worktrees": "not_requested", "branches": "not_requested", "stashes": "not_requested"})
    try:
        url = public_url(item["url"])
        account_id, repository_id, installation_id = (_identity(item[key]) for key in
            ("github_account_id", "github_repository_id", "installation_id"))
        result.update(id=f"github:{account_id}:{repository_id}", url=url, path=url,
                      private=item.get("private") if type(item.get("private")) is bool else None)
        generation = auth.generation

        def check_session():
            with auth.session_guard(generation, account_id):
                pass

        # Refresh a sleeping session before the expiry-sensitive publication
        # guard. Capture generation first so logout during refresh cannot bind
        # this observation to a replacement session. Fetch obtains its own
        # current credential later; no credential reaches local Git commands.
        auth.token()
        check_session()
        installation = auth.installation(installation_id)
        if not isinstance(installation, dict) or installation.get("id") != installation_id:
            raise AuthenticatedRepositoryError("GitHub installation authorization changed.")
        metadata = auth.request_json(f"/repositories/{repository_id}")
        if (not isinstance(metadata, dict) or metadata.get("id") != repository_id
                or public_url(metadata.get("html_url")) != url or type(metadata.get("private")) is not bool):
            raise AuthenticatedRepositoryError("GitHub repository identity or access changed; select it again.")
        branch = metadata.get("default_branch")
        if not isinstance(branch, str) or not branch or branch.startswith("-"):
            raise AuthenticatedRepositoryError("GitHub default branch is unavailable.")
        check_session()
        base = validate_cache_root(cache_root, config)
        check_session()
        cache = _cache_directory(base, account_id, repository_id)
        git = AuthenticatedGit(cache)
        if not (cache / "HEAD").exists():
            if set(path.name for path in cache.iterdir()) != {"work-visibility-cache.json"}:
                raise AuthenticatedRepositoryError("Authenticated cache is incomplete; collection is blocked.")
            git.run("init", "--bare", "--template=", str(cache))
        git.validate_config()
        git.run("check-ref-format", "refs/heads/" + branch)
        token = auth.token()
        check_session()
        try:
            git.fetch(url, branch, token, lambda: auth.generation != generation)
        finally:
            token = None
        check_session()
        git.validate_config()
        head = git.run("rev-parse", "--verify", "refs/heads/observed^{commit}").decode().strip()
        shallow = git.run("rev-parse", "--is-shallow-repository").strip() == b"true"
        zone_name = config["timezone"]
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone, zone_name = timezone.utc, "UTC"
            result["warnings"].append("Requested timezone unavailable; history uses UTC.")
        history = _history(git, ref=branch, head=head, days=config["days"], zone=zone,
            zone_name=zone_name, now=now, max_commits=config["max_commits"],
            patterns=tuple(item.get("exclude_globs", [])), shallow=shallow)
        history.update(collected_at=now.isoformat(), cached=False)
        # The caller also guards publication; this protects direct callers and
        # prevents a revoked session from returning cached private measurements.
        with auth.session_guard(generation, account_id):
            status = "partial" if shallow or history["truncated"] else "ok"
            result.update(head=head, ref=branch, history=history, private=metadata["private"], status=status)
            result["source_status"]["history"] = status
            if shallow:
                result["warnings"].append("GitHub cache is limited to 2,000 commit depth; earlier history and boundary LOC are incomplete.")
            return result
    except AuthenticatedRepositoryError as exc:
        result["errors"].append(str(exc))
    except Exception:
        # API/Git errors may contain response bodies, URLs or credentials. Never
        # copy them into the UI snapshot, persisted registry, logs or exports.
        result["errors"].append("GitHub access or collection is unavailable. Reconnect or check repository access and try again.")
    return result
