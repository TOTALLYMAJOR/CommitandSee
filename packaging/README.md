# Native Windows portable ZIP

The one-folder PyInstaller bundle includes Python and timezone data. Users extract
the ZIP and open `CommitandSee.exe`; they still need Git for Windows. The launcher
uses `%LOCALAPPDATA%\CommitandSee`, starts on an available loopback port, checks HTTP
readiness, and then opens the default browser. It leaves the source CLI unchanged.

Build from native Windows PowerShell, using 64-bit Python 3.11 or newer:

```powershell
.\packaging\build-windows.ps1 -Python C:\Python314\python.exe
```

The script creates an isolated environment in a new temporary directory and
installs `requirements-build.txt` there. `-BuildRoot` and `-OutputDirectory` can
select other build-owned locations. Do not use a live app/settings directory.
No packages are installed globally. Downloading build dependencies requires network.

If host policy blocks an unsigned PowerShell script on a network/WSL path, keep
that policy intact and invoke the native Python build steps directly:

```powershell
$build = Join-Path $env:TEMP ("CommitandSee-" + [guid]::NewGuid().ToString("N"))
python -m venv "$build\venv"
& "$build\venv\Scripts\python.exe" -m pip install --only-binary=:all: -r .\packaging\requirements-build.txt
& "$build\venv\Scripts\python.exe" .\packaging\build_portable.py --source-root $PWD.Path --build-root $build --output-directory "$build\artifacts"
```

The build captures only the allowlisted runtime files, assets, license, and build
recipe. It verifies their hashes before and after building, refuses a changed
snapshot, and emits a ZIP, SHA-256 file, and `build-result.json`. It never copies
the working checkout wholesale or includes private configuration, registry, state,
Git metadata, screenshots, or public-repository caches. `BUILD-INFO.json` identifies
the source hashes and tool versions; `BUILD-DEPENDENCIES.txt` records resolved
build dependencies. A digest match is provenance, not functional acceptance.

Run focused launcher tests with `python -B -m unittest -v test_portable_launcher`.
The native executable additionally needs HTTP, add/remove, restart persistence,
and process-exit smoke validation. Run the included native harness against the ZIP:

```powershell
python .\packaging\smoke_portable.py --archive C:\build\CommitandSee-Windows.zip --git "C:\Program Files\Git\cmd\git.exe"
```

It uses disposable settings and Git data, strips Python from the child PATH,
checks graceful Ctrl+Break shutdown, and retains its logs/result path. It does not
open the real browser (`--no-browser`); browser launch ordering is checked in the
launcher tests. A successful `--help` during packaging only
establishes that the bundled interpreter can start. Do not claim hosted, signed,
SmartScreen, clean-machine, or broad Windows support from a local build.

Stop the running app before replacing its extracted folder. Ship the complete
folder, including `_internal`, licenses, and start instructions. No service or
auto-update mechanism is installed. Current native subprocess containment uses
Windows 10/Server 2016-or-newer creation-time Job Object admission.
Stop all observer instances before copying or moving saved configuration and its
SQLite registry sidecar together.

Primary references: [PyInstaller operating modes](https://pyinstaller.org/en/stable/operating-mode.html),
[spec files and data](https://pyinstaller.org/en/stable/spec-files.html),
[external program DLL handling](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application),
and [Python timezone data](https://docs.python.org/3/library/zoneinfo.html#data-sources).
