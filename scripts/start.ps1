[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8000)
. (Join-Path $PSScriptRoot 'common.ps1')
$python = Require-Venv
if (-not (Test-Path -LiteralPath (Join-Path $script:AppRoot 'frontend\out\index.html'))) { throw 'Missing production frontend. Run .\scripts\build.ps1 first.' }
Write-Host "DoorLens: http://127.0.0.1:$Port (Ctrl+C to stop)"
Push-Location $script:AppRoot
try {
    & $python -m uvicorn doorlens.main:app --app-dir (Join-Path $script:AppRoot 'backend') --host 127.0.0.1 --port $Port
    Assert-NativeSuccess 'DoorLens server'
} finally { Pop-Location }
