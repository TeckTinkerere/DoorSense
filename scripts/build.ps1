[CmdletBinding()]
param([switch]$SkipModelVerification)
. (Join-Path $PSScriptRoot 'common.ps1')
$python = Require-Venv
if (-not $SkipModelVerification) {
    & $python (Join-Path $PSScriptRoot 'package_models.py') --verify
    Assert-NativeSuccess 'Frozen model verification'
}
$oldApiBase = $env:NEXT_PUBLIC_API_BASE
$env:NEXT_PUBLIC_API_BASE = ''
try { Invoke-Pnpm @('run', 'build') }
finally { $env:NEXT_PUBLIC_API_BASE = $oldApiBase }
if (-not (Test-Path -LiteralPath (Join-Path $script:AppRoot 'frontend\out\index.html'))) { throw 'The frontend static export was not created.' }
Write-Host 'Build complete. Run .\scripts\start.ps1 and open http://127.0.0.1:8000.'
