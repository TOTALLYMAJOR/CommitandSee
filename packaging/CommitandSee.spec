# Native Windows, one-folder console distribution. Git is deliberately external.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'portable_launcher.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / filename), '.') for filename in
           ('dashboard.html', 'demo.html', 'demo.json', 'github_app_defaults.json')]
          + [(str(root / 'docs' / 'GITHUB-APP-SETUP.md'), 'docs')]
          + collect_data_files('tzdata'),
    hiddenimports=['github_auth', 'authenticated_repositories'] + collect_submodules('tzdata'),
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter'], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='CommitandSee',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='CommitandSee')
