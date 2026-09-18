[CmdletBinding()]
param([switch]$SkipFrontend, [switch]$SkipModelVerification)
. (Join-Path $PSScriptRoot 'common.ps1')
$python = Require-Venv
Push-Location $script:AppRoot
try {
    & $python -m pytest tests -q
    Assert-NativeSuccess 'Python tests'
    if (-not $SkipModelVerification) {
        & $python (Join-Path $PSScriptRoot 'package_models.py') --verify
        Assert-NativeSuccess 'Frozen model verification'
    }
    if (-not $SkipFrontend) { Invoke-Pnpm @('run', 'typecheck') }
} finally { Pop-Location }
