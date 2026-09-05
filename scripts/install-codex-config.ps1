[CmdletBinding()]
param(
    [ValidateSet('Preview', 'Apply')]
    [string]$Mode = 'Preview'
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$codexHome = Join-Path $env:USERPROFILE '.codex'
$backupRoot = Join-Path $codexHome 'backups\codex-config'
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'

$files = @(
    @{ Source = (Join-Path $repoRoot 'config.toml'); Target = (Join-Path $codexHome 'config.toml') },
    @{ Source = (Join-Path $repoRoot 'AGENTS.md'); Target = (Join-Path $codexHome 'AGENTS.md') }
)

Write-Output "Mode: $Mode"
Write-Output "Codex home: $codexHome"

foreach ($file in $files) {
    if (-not (Test-Path -LiteralPath $file.Source)) {
        throw "Missing source file: $($file.Source)"
    }

    Write-Output "Would copy: $($file.Source) -> $($file.Target)"
}

if ($Mode -eq 'Preview') {
    Write-Output 'Preview complete. No files were changed.'
    exit 0
}

New-Item -ItemType Directory -Force -Path $codexHome, $backupRoot | Out-Null
$backupDir = Join-Path $backupRoot $timestamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

foreach ($file in $files) {
    if (Test-Path -LiteralPath $file.Target) {
        Copy-Item -LiteralPath $file.Target -Destination (Join-Path $backupDir (Split-Path -Leaf $file.Target)) -Force
    }
    Copy-Item -LiteralPath $file.Source -Destination $file.Target -Force
}

Write-Output "Applied shared files. Backup: $backupDir"
