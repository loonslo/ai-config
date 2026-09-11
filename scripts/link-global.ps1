[CmdletBinding()]
param(
    [ValidateSet('Preview', 'Apply')][string]$Mode = 'Preview',
    [string]$Local = (Join-Path (Split-Path -Parent $PSScriptRoot) 'device.json'),
    [switch]$IncludeCodexConfig
)
$ErrorActionPreference = 'Stop'
$syncArgs = @((Join-Path $PSScriptRoot 'sync.py'), 'rules', '--local', $Local)
if ($Mode -eq 'Apply') { $syncArgs += '--apply' }
& python @syncArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($IncludeCodexConfig) {
    $configArgs = @((Join-Path $PSScriptRoot 'sync.py'), 'config', '--local', $Local)
    if ($Mode -eq 'Apply') { $configArgs += '--apply' }
    & python @configArgs
    exit $LASTEXITCODE
}
