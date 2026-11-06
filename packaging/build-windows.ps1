param(
    [string]$Python = "python",
    [string]$BuildRoot = "",
    [string]$OutputDirectory = ""
)
$ErrorActionPreference = "Stop"
$sourceRoot = Split-Path -Parent $PSScriptRoot
if (-not $BuildRoot) {
    $BuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("CommitandSee-build-" + [guid]::NewGuid().ToString("N"))
}
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $BuildRoot "artifacts" }
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
$buildPython = Join-Path $BuildRoot "venv\Scripts\python.exe"
if (-not (Test-Path $buildPython)) {
    & $Python -m venv (Join-Path $BuildRoot "venv")
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated build environment." }
}
& $buildPython -m pip --disable-pip-version-check install --only-binary=:all: -r (Join-Path $PSScriptRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Installing the pinned build dependencies failed." }
& $buildPython (Join-Path $PSScriptRoot "build_portable.py") --source-root $sourceRoot --build-root $BuildRoot --output-directory $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw "Portable build failed; no validated ZIP was produced." }
