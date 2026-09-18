[CmdletBinding()]
param([string]$PythonPath, [switch]$SkipFrontend)
. (Join-Path $PSScriptRoot 'common.ps1')

if (-not (Test-Path -LiteralPath $script:VenvPython)) {
    $python = Find-Python312 $PythonPath
    $launchArgs = @($python.Arguments)
    Write-Host "Creating app-local environment with $($python.Path)"
    & $python.Path @launchArgs -m venv (Join-Path $script:AppRoot '.venv')
    Assert-NativeSuccess 'Python environment creation'
}
$venv = Require-Venv
& $venv -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'The existing .venv is not Python 3.12. Recreate that app-local environment with Python 3.12 before installing.' }
$requirements = Join-Path $script:AppRoot 'requirements.lock'
if (-not (Test-Path -LiteralPath $requirements)) { $requirements = Join-Path $script:AppRoot 'requirements.txt' }
& $venv -m pip install --disable-pip-version-check -r $requirements
Assert-NativeSuccess 'Python dependency installation'
if (-not $SkipFrontend) { Invoke-Pnpm @('install', '--frozen-lockfile') }
Write-Host 'Setup complete. Run .\scripts\build.ps1, then .\scripts\start.ps1.'
