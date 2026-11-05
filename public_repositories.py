"""Anonymous public GitHub history, isolated from user clones and credentials."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from git_metrics import _Git, _history, _run, _git_capabilities, GitError


def public_url(value):
    if not isinstance(value, str):
        raise ValueError('Enter a public GitHub repository URL.')
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9_.-]{1,100})/?', value.strip(), re.I)
    if not match:
        raise ValueError('Use https://github.com/owner/repository, without credentials, query, or fragment.')
    owner, name = match.groups()
    if name.endswith('.git'):
        name = name[:-4]
    if not name or name in {'.', '..'}:
        raise ValueError('Invalid repository name.')
    return f'https://github.com/{owner.lower()}/{name.lower()}'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def public_metadata(url):
    url = public_url(url)
    request = Request('https://api.github.com/repos/' + url.removeprefix('https://github.com/'),
                      headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Work-Visibility'})
    try:
        with build_opener(NoRedirect).open(request, timeout=10) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError('Repository metadata exceeded the response budget.')
        data = json.loads(payload)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError('Public repository not found. Private repositories require a local checkout.') from None
        if exc.code in (403, 429):
            raise ValueError('GitHub rate limit or access restriction. Try again later.') from None
        raise ValueError('GitHub metadata request failed; check the canonical repository URL.') from None
    except (URLError, TimeoutError, OSError):
        raise ValueError('Cannot reach GitHub. Check the connection and try again.') from None
    if not isinstance(data, dict) or data.get('private') is not False or data.get('visibility', 'public') != 'public':
        raise ValueError('Only anonymously accessible public GitHub repositories are supported.')
    canonical = public_url(data.get('html_url'))
    if canonical != url:
        raise ValueError('Use the canonical public repository URL: ' + canonical)
    return data


class PublicGit(_Git):
    def __init__(self, path):
        _, lazy = _git_capabilities()
        super().__init__(path, lazy)
        self.prefix += ['-c', 'core.hooksPath=' + os.devnull, '-c', 'credential.helper=',
                        '-c', 'http.extraHeader=', '-c', 'http.followRedirects=false',
                        '-c', 'protocol.allow=never', '-c', 'protocol.https.allow=always',
                        '-c', 'maintenance.auto=false', '-c', 'gc.auto=0']
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(HOME=str(path), XDG_CONFIG_HOME=str(path), CURL_HOME=str(path),
            GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM='1',
            GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', LC_ALL='C')

    def run(self, *args, **kwargs):
        code, out, _ = _run(self.prefix + list(args), environment=self.environment, **kwargs)
        if code:
            raise GitError('Public Git request failed. The repository may be unavailable or exceed the collection budget.')
        return out


def collect_public(item, cache_root, config):
    url = public_url(item['url'])
    now = datetime.now(timezone.utc)
    result = {**item, 'id': url, 'path': url, 'source_kind': 'public', 'collected_at': now.isoformat(),
        'status': 'error', 'errors': [], 'warnings': ['Public default-branch history only. Local work, stashes, unpublished commits, PRs and CI are not observed.'],
        'history': None, 'head': None, 'worktrees': [], 'branches': [], 'stashes': [], 'remote_branches': [],
        'source_status': {'history': 'error', 'worktrees': 'not_requested', 'branches': 'not_requested', 'stashes': 'not_requested'}}
    try:
        metadata = public_metadata(url)
        cache = Path(cache_root) / hashlib.sha256(url.encode()).hexdigest()[:24]
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = cache / 'work-visibility-cache.json'
        if not marker.exists():
            if any(cache.iterdir()):
                raise GitError('Cache directory is not owned by this monitor.')
            marker.write_text(json.dumps({'url': url}))
        if json.loads(marker.read_text()) != {'url': url}:
            raise GitError('Cache identity mismatch.')
        git = PublicGit(cache)
        if not (cache / 'HEAD').exists():
            git.run('init', '--bare', '--template=', str(cache))
        branch = metadata.get('default_branch')
        if not isinstance(branch, str) or not branch or branch.startswith('-'):
            raise GitError('Public default branch is unavailable.')
        git.run('check-ref-format', 'refs/heads/' + branch)
        git.run('fetch', '--quiet', '--depth=2000', '--no-tags', '--no-recurse-submodules',
                '--no-auto-maintenance', '--', url + '.git', '+refs/heads/' + branch + ':refs/heads/observed')
        head = git.run('rev-parse', '--verify', 'refs/heads/observed^{commit}').decode().strip()
        shallow = git.run('rev-parse', '--is-shallow-repository').strip() == b'true'
        zone_name = config['timezone']
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError:
            zone, zone_name = timezone.utc, 'UTC'
            result['warnings'].append('Requested timezone unavailable; history uses UTC.')
        history = _history(git, ref=branch, head=head, days=config['days'], zone=zone,
            zone_name=zone_name, now=now, max_commits=config['max_commits'],
            patterns=tuple(item.get('exclude_globs', [])), shallow=shallow)
        history.update(collected_at=now.isoformat(), cached=False)
        result.update(head=head, ref=branch, history=history, status='partial' if shallow or history['truncated'] else 'ok')
        result['source_status']['history'] = 'partial' if result['status'] == 'partial' else 'ok'
        if shallow:
            result['warnings'].append('Public cache is limited to 2,000 commit depth; earlier history and boundary LOC are incomplete.')
    except (ValueError, OSError, GitError) as exc:
        result['errors'].append(str(exc))
    return result
