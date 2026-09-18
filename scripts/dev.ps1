[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$ApiPort = 8000)
. (Join-Path $PSScriptRoot 'common.ps1')
$python = Require-Venv
$logDirectory = Join-Path $script:AppRoot '.local'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$backendDirectory = Join-Path $script:AppRoot 'backend'
$arguments = @('-m', 'uvicorn', 'doorlens.main:app', '--app-dir', ('"' + $backendDirectory + '"'), '--host', '127.0.0.1', '--port', "$ApiPort")
$backendProcess = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $script:AppRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'backend.out.log') -RedirectStandardError (Join-Path $logDirectory 'backend.err.log')
$oldApiBase = $env:NEXT_PUBLIC_API_BASE
$env:NEXT_PUBLIC_API_BASE = "http://127.0.0.1:$ApiPort"
try {
    Start-Sleep -Milliseconds 800
    if ($backendProcess.HasExited) { throw "Backend exited. Read $logDirectory\backend.err.log." }
    Invoke-Pnpm @('run', 'dev', '--hostname', '127.0.0.1')
} finally {
    $env:NEXT_PUBLIC_API_BASE = $oldApiBase
    if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id }
}
