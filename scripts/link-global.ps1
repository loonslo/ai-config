[CmdletBinding()]
param(
    [ValidateSet('Preview', 'Apply')]
    [string]$Mode = 'Preview',
    [switch]$IncludeCodexConfig
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$codexHome = Join-Path $env:USERPROFILE '.codex'
$claudeHome = Join-Path $env:USERPROFILE '.claude'
$backupRoot = Join-Path $env:USERPROFILE 'ai-config-backups'

$links = @(
    @{ Source = (Join-Path $repoRoot 'common\instructions.md'); Target = (Join-Path $codexHome 'AGENTS.md') },
    @{ Source = (Join-Path $repoRoot 'common\instructions.md'); Target = (Join-Path $claudeHome 'CLAUDE.md') }
)

if ($IncludeCodexConfig) {
    $links += @{ Source = (Join-Path $repoRoot 'codex\config.toml'); Target = (Join-Path $codexHome 'config.toml') }
}

function Get-ExistingTarget($path) {
    if (Test-Path -LiteralPath $path) {
        return Get-Item -LiteralPath $path -Force
    }
    return $null
}

function Backup-Target($item, $backupDir) {
    if ($null -eq $item) { return }
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $backupPath = Join-Path $backupDir $item.Name
    Copy-Item -LiteralPath $item.FullName -Destination $backupPath -Force
    Write-Output "Backed up $($item.FullName) -> $backupPath"
}

Write-Output "Mode: $Mode"
Write-Output "Repository: $repoRoot"
Write-Output "Shared rules are always included. Codex config included: $IncludeCodexConfig"

foreach ($link in $links) {
    if (-not (Test-Path -LiteralPath $link.Source)) {
        throw "Missing source file: $($link.Source)"
    }
    $existing = Get-ExistingTarget $link.Target
    if ($null -eq $existing) {
        Write-Output "Would create link: $($link.Target) -> $($link.Source)"
    } elseif ($existing.LinkType -eq 'SymbolicLink') {
        Write-Output "Would replace existing link: $($link.Target)"
    } else {
        Write-Output "Would back up and replace file: $($link.Target)"
    }
}

if ($Mode -eq 'Preview') {
    Write-Output 'Preview complete. No files were changed.'
    exit 0
}

$backupDir = Join-Path $backupRoot (Get-Date -Format 'yyyyMMdd-HHmmss')
foreach ($link in $links) {
    $targetParent = Split-Path -Parent $link.Target
    New-Item -ItemType Directory -Force -Path $targetParent | Out-Null
    $existing = Get-ExistingTarget $link.Target
    Backup-Target $existing $backupDir
    if ($null -ne $existing) {
        Remove-Item -LiteralPath $link.Target -Force
    }

    try {
        New-Item -ItemType SymbolicLink -Path $link.Target -Target $link.Source -Force | Out-Null
        Write-Output "Linked: $($link.Target) -> $($link.Source)"
    } catch {
        Copy-Item -LiteralPath $link.Source -Destination $link.Target -Force
        Write-Output "Symbolic link unavailable; copied: $($link.Source) -> $($link.Target)"
    }
}

Write-Output "Global configuration updated. Backups: $backupDir"
