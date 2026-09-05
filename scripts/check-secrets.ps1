[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$excluded = '\\.git(\\|$)|\\.env($|\\)|\\.local\\.|\\.example\\.|\\.codex-home(\\|$)|\\secrets(\\|$)|\\credentials(\\|$)'
$patterns = @(
    'sk-[A-Za-z0-9_-]{20,}',
    '(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret)\s*[:=]\s*["''][^"'']{12,}["'']',
    '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----'
)

$findings = @()
Get-ChildItem -LiteralPath $repoRoot -Recurse -File -Force |
    Where-Object { $_.FullName -notmatch $excluded } |
    ForEach-Object {
        $content = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
        if ($null -ne $content) {
            foreach ($pattern in $patterns) {
                if ($content -match $pattern) {
                    $findings += $_.FullName
                    break
                }
            }
        }
    }

if ($findings.Count -gt 0) {
    Write-Output 'Potential secret-like values found in:'
    $findings | Sort-Object -Unique | ForEach-Object { Write-Output "- $_" }
    exit 1
}

Write-Output 'No secret-like values detected.'
