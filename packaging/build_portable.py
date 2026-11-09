"""Build a source-bound Windows ZIP from an isolated native Python environment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

# Prospective package version; changing this recipe does not publish an artifact.
VERSION = '0.5.0-rc.1'
INPUTS = (
    'portable_launcher.py', 'git_dashboard.py', 'git_metrics.py', 'windows_job.py',
    'local_insights.py',
    'public_repositories.py', 'repository_registry.py', 'dashboard.html', 'demo.html',
    'github_auth.py', 'authenticated_repositories.py', 'github_app_defaults.json',
    'docs/GITHUB-APP-SETUP.md',
    'demo.json', 'LICENSE', 'packaging/CommitandSee.spec',
    'packaging/requirements-build.txt', 'packaging/build-windows.ps1',
    'packaging/build_portable.py', 'packaging/START-HERE.txt',
    'packaging/THIRD-PARTY-NOTICES.txt', 'packaging/README.md',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(root):
    return {name: digest(root / name) for name in INPUTS}


def licenses(destination):
    destination.mkdir()
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('Native Python LICENSE.txt is required for distribution.')
    shutil.copy2(python_license, destination / 'Python-LICENSE.txt')
    for name in ('pyinstaller', 'tzdata'):
        dist = metadata.distribution(name)
        selected = [p for p in dist.files or ()
                    if 'licenses' in (part.lower() for part in p.parts)
                    or p.name.lower().startswith(('license', 'copying'))]
        if not selected:
            raise RuntimeError(f'No license files found for {name}; do not distribute this build.')
        for relative in selected:
            source = Path(dist.locate_file(relative))
            if source.is_file():
                target = destination / name / Path(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--build-root', required=True, type=Path)
    parser.add_argument('--output-directory', required=True, type=Path)
    args = parser.parse_args()
    if os.name != 'nt' or platform.machine().upper() not in ('AMD64', 'X86_64'):
        parser.error('Build this Windows x64 distribution with native Windows x64 Python.')
    root, build, output = (p.resolve() for p in (args.source_root, args.build_root, args.output_directory))
    before = source_hashes(root)
    source_digest = hashlib.sha256(json.dumps(before, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    snapshot = build / ('source-' + source_digest[:12])
    snapshot.mkdir(parents=True, exist_ok=False)
    for relative in INPUTS:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target)
    if source_hashes(snapshot) != before or source_hashes(root) != before:
        raise RuntimeError('Build inputs changed while being captured; retry after the source is stable.')
    build_command = [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm',
                     '--workpath', str(build / ('work-' + source_digest[:12])),
                     '--distpath', str(build / ('dist-' + source_digest[:12])),
                     str(snapshot / 'packaging' / 'CommitandSee.spec')]
    build_log = build / ('build-' + source_digest[:12] + '.log')
    print(f'Building captured source {source_digest}; log: {build_log}', flush=True)
    with build_log.open('w', encoding='utf-8') as log:
        log.write(json.dumps(build_command) + '\n')
        log.flush()
        subprocess.run(build_command, check=True, stdout=log, stderr=subprocess.STDOUT)
    bundle = build / ('dist-' + source_digest[:12]) / 'CommitandSee'
    licenses(bundle / 'licenses')
    for source, name in (('LICENSE', 'LICENSE.txt'), ('packaging/START-HERE.txt', 'START-HERE.txt'),
                         ('packaging/THIRD-PARTY-NOTICES.txt', 'THIRD-PARTY-NOTICES.txt')):
        shutil.copy2(snapshot / source, bundle / name)
    info = {'version': VERSION, 'built_at': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
            'python': sys.version, 'pyinstaller': metadata.version('pyinstaller'),
            'tzdata': metadata.version('tzdata'), 'source_digest': source_digest,
            'source_files': before, 'signed': False, 'git_bundled': False}
    (bundle / 'BUILD-INFO.json').write_text(json.dumps(info, indent=2) + '\n', encoding='utf-8')
    freeze = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], check=True, capture_output=True, text=True)
    (bundle / 'BUILD-DEPENDENCIES.txt').write_text(freeze.stdout, encoding='utf-8')
    subprocess.run([str(bundle / 'CommitandSee.exe'), '--help'], check=True, timeout=20)
    if source_hashes(root) != before:
        raise RuntimeError('Build inputs changed during packaging; rebuild before distributing.')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('CommitandSee-' + VERSION + '-Windows-x64-' + source_digest[:12] + '.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                stream.write(path, Path('CommitandSee') / path.relative_to(bundle))
    checksum = digest(archive)
    archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
    report = {'archive': str(archive), 'sha256': checksum, 'bytes': archive.stat().st_size,
              'source_digest': source_digest, 'executable': str(bundle / 'CommitandSee.exe'),
              'source_snapshot': str(snapshot), 'build_log': str(build_log)}
    (output / 'build-result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
