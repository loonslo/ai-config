$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'check-secrets.py')
exit $LASTEXITCODE
