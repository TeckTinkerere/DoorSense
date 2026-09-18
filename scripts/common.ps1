Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:AppRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:VenvPython = Join-Path $script:AppRoot '.venv\Scripts\python.exe'

function Assert-NativeSuccess([string]$Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed (exit code $LASTEXITCODE)." }
}

function Find-Python312([string]$PythonPath) {
    $candidates = @()
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python executable not found: $PythonPath" }
        $candidates += [pscustomobject]@{ Path = $PythonPath; Arguments = @() }
    } else {
        $userPython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
        if (Test-Path -LiteralPath $userPython) { $candidates += [pscustomobject]@{ Path = $userPython; Arguments = @() } }
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) { $candidates += [pscustomobject]@{ Path = $launcher.Source; Arguments = @('-3.12') } }
        $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($onPath) { $candidates += [pscustomobject]@{ Path = $onPath.Source; Arguments = @() } }
        $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $bundled) { $candidates += [pscustomobject]@{ Path = $bundled; Arguments = @() } }
    }
    foreach ($candidate in $candidates) {
        $launchArgs = @($candidate.Arguments)
        try {
            $version = & $candidate.Path @launchArgs -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>$null
            if ($LASTEXITCODE -eq 0 -and "$version".Trim() -eq '3.12') { return $candidate }
        } catch {
            if ($PythonPath) { throw "Could not run the requested Python executable: $PythonPath. $($_.Exception.Message)" }
        }
    }
    throw 'Python 3.12 is required. Install Python 3.12 or pass -PythonPath C:\path\to\python.exe to setup.ps1.'
}

function Require-Venv {
    if (-not (Test-Path -LiteralPath $script:VenvPython)) { throw 'Missing app-local Python environment. Run .\scripts\setup.ps1 first.' }
    return $script:VenvPython
}

function Find-Pnpm {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $nodePath = if ($node) { $node.Source } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' }
    if (-not (Test-Path -LiteralPath $nodePath)) { throw 'Node.js is required to install/build the frontend. Install a supported Node.js LTS release.' }
    $nodeDirectory = Split-Path -Parent $nodePath
    if (($env:PATH -split ';') -notcontains $nodeDirectory) { $env:PATH = "$nodeDirectory;$env:PATH" }
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($pnpm) { return [pscustomobject]@{ Path = $pnpm.Source; Arguments = @() } }
    $cliCandidates = @(
        (Join-Path $script:AppRoot 'node_modules\pnpm\bin\pnpm.cjs'),
        (Join-Path $nodeDirectory 'node_modules\pnpm\bin\pnpm.cjs'),
        (Join-Path (Split-Path -Parent $nodeDirectory) 'node_modules\pnpm\bin\pnpm.cjs'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.cjs')
    )
    foreach ($cli in $cliCandidates) {
        if (Test-Path -LiteralPath $cli) { return [pscustomobject]@{ Path = $nodePath; Arguments = @($cli) } }
    }
    throw 'pnpm is required. Install the packageManager version declared in frontend/package.json, then rerun setup.ps1.'
}

function Invoke-Pnpm([string[]]$CommandArguments) {
    $runner = Find-Pnpm
    $prefix = @($runner.Arguments)
    Push-Location (Join-Path $script:AppRoot 'frontend')
    try {
        & $runner.Path @prefix @CommandArguments
        Assert-NativeSuccess 'pnpm'
    } finally { Pop-Location }
}
