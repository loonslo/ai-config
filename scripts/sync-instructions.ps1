[CmdletBinding()]
param()

$repoRoot = Split-Path -Parent $PSScriptRoot
$source = Join-Path $repoRoot 'instructions.md'
$target = Join-Path $repoRoot 'AGENTS.md'

if (-not (Test-Path -LiteralPath $source)) {
    throw "Missing source file: $source"
}

Copy-Item -LiteralPath $source -Destination $target -Force
Write-Output "Synchronized instructions.md -> AGENTS.md"
