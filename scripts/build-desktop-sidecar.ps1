param(
    [string]$PythonVersion = "3.14",
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DesktopRoot = Join-Path $RepositoryRoot "desktop"
$BuildEnvironment = Join-Path $DesktopRoot ".build-venv"
$Python = Join-Path $BuildEnvironment "Scripts\python.exe"
$OutputDirectory = Join-Path $DesktopRoot "src-tauri\binaries"
$WorkDirectory = Join-Path $DesktopRoot ".build"
$Requirements = Join-Path $DesktopRoot "requirements-windows.lock.txt"
$Entrypoint = Join-Path $RepositoryRoot "scripts\desktop_rpc.py"
$ExpectedName = "ai-config-rpc-$TargetTriple"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python $PythonVersion for the build host."
}

if (-not (Test-Path $Python)) {
    & py "-$PythonVersion" -m venv $BuildEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python $PythonVersion build environment." }
}

$RuntimeVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or $RuntimeVersion.Trim() -ne $PythonVersion) {
    throw "Expected Python $PythonVersion in $BuildEnvironment, found '$RuntimeVersion'. Remove that build environment and retry."
}

& $Python -m pip install --disable-pip-version-check -r $Requirements
if ($LASTEXITCODE -ne 0) { throw "Could not install the pinned desktop build requirements." }

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$Arguments = @(
    "-m", "PyInstaller",
    "--clean", "--noconfirm", "--onefile", "--console",
    "--name", $ExpectedName,
    "--distpath", $OutputDirectory,
    "--workpath", $WorkDirectory,
    "--specpath", $WorkDirectory,
    "--paths", $RepositoryRoot,
    "--add-data", "$(Join-Path $RepositoryRoot 'common');common",
    "--add-data", "$(Join-Path $RepositoryRoot 'templates');templates",
    "--add-data", "$(Join-Path $RepositoryRoot 'schemas');schemas",
    "--add-data", "$(Join-Path $RepositoryRoot 'codex/config.toml');codex",
    "--add-data", "$(Join-Path $RepositoryRoot 'claude/settings.shared.json');claude",
    "--collect-all", "tomlkit",
    "--collect-all", "cryptography",
    "--hidden-import", "keyring.backends.Windows",
    "--copy-metadata", "keyring",
    "--exclude-module", "keyring.testing",
    "--exclude-module", "pytest",
    $Entrypoint
)

Push-Location $RepositoryRoot
try {
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build the RPC sidecar." }
}
finally {
    Pop-Location
}

$Artifact = Join-Path $OutputDirectory "$ExpectedName.exe"
if (-not (Test-Path -LiteralPath $Artifact -PathType Leaf)) {
    throw "Expected sidecar output was not created: $Artifact"
}

Write-Output "Built $Artifact"
