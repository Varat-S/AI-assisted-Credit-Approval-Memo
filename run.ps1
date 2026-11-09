<#
.SYNOPSIS
    One-command launcher for the credit memo web app (Windows).

.DESCRIPTION
    1. Finds uv outside the project's .venv (installs uv 0.12.23 if missing).
    2. Installs the locked dependencies into .venv (runtime + Vertex + PDF export).
    3. Creates .env from .env.example on first run and stops so you can fill it in.
    4. Runs the offline setup check (no model call), then creates data\browser_demo.db on first run
       or migrates an existing one.
    5. Starts the web app and opens http://127.0.0.1:<Port>/analysis/new.

    Stop the server with Ctrl+C.

.EXAMPLE
    .\run.ps1
    .\run.ps1 -Port 8010
    .\run.ps1 -SkipInstall -NoBrowser
#>
param(
    [int]$Port = 8001,
    [switch]$SkipInstall,
    [switch]$NoBrowser
)
# 'Continue' so uv's progress messages on stderr are not treated as errors by Windows PowerShell 5.1;
# failures are detected from exit codes instead.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
$venv = Join-Path $PSScriptRoot '.venv'

function Test-OutsideVenv([string]$path) {
    return -not $path.StartsWith($venv, [System.StringComparison]::OrdinalIgnoreCase)
}

function Find-Uv {
    # uv must never run from inside .venv: `uv sync` may need to rebuild that folder.
    foreach ($cmd in @(Get-Command uv -All -CommandType Application -ErrorAction SilentlyContinue)) {
        if (Test-OutsideVenv $cmd.Source) { return @($cmd.Source) }
    }
    foreach ($py in @(@('py', '-3'), @('python'))) {
        $exe = Get-Command $py[0] -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $exe -or -not (Test-OutsideVenv $exe.Source)) { continue }
        $pre = @($exe.Source) + @($py | Select-Object -Skip 1)
        & $pre[0] @($pre | Select-Object -Skip 1) -m uv --version *> $null
        if ($LASTEXITCODE -eq 0) { return $pre + @('-m', 'uv') }
    }
    return
}

function Fail([string]$message) {
    Write-Host $message -ForegroundColor Red
    exit 1
}

# 1. uv (pinned to the version the lockfile was produced with)
$uv = @(Find-Uv)
if ($uv.Count -eq 0) {
    $py = Get-Command py, python -CommandType Application -ErrorAction SilentlyContinue |
        Where-Object { Test-OutsideVenv $_.Source } | Select-Object -First 1
    if (-not $py) { Fail 'Python 3.11+ is required: https://www.python.org/downloads/' }
    Write-Host 'Installing uv 0.12.23...' -ForegroundColor Cyan
    & $py.Source -m pip install --user 'uv==0.12.23'
    if ($LASTEXITCODE -ne 0) { Fail 'Could not install uv.' }
    $uv = @(Find-Uv)
    if ($uv.Count -eq 0) { $uv = @($py.Source, '-m', 'uv') }
}
$uvExe = $uv[0]
$uvPre = @($uv | Select-Object -Skip 1)

# 2. Dependencies (--inexact keeps extra tools already in .venv, e.g. pytest)
if (-not $SkipInstall) {
    Write-Host 'Installing locked dependencies into .venv...' -ForegroundColor Cyan
    & $uvExe @uvPre sync --locked --inexact --extra vertex --extra pdf
    if ($LASTEXITCODE -ne 0) { Fail 'Dependency install failed (see above). Close anything running from .venv and retry.' }
}

# 3. Local configuration
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host ''
    Write-Host 'Created .env from .env.example. Before the first run, edit .env and set:' -ForegroundColor Yellow
    Write-Host '  SEC_USER_AGENT        your name and email (used to download 10-Ks from SEC EDGAR)'
    Write-Host '  GOOGLE_CLOUD_PROJECT  your Google Cloud project (or VERTEX_API_KEY instead)'
    Write-Host '  VERTEX_MODEL_NARROW   a Gemini model your project can use'
    Write-Host 'For Vertex ADC also run: gcloud auth application-default login'
    Write-Host 'Then run .\run.ps1 again.'
    exit 1
}

# 4. Offline setup check: warns but still starts, so saved runs remain viewable
& $uvExe @uvPre run --no-sync python -m app.doctor
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Setup check failed (see above). The app will start, but new analyses will not run until it passes.' -ForegroundColor Yellow
}

# 4b. Analysis database: create it on first run, otherwise bring an older schema up to date.
#     The web app's pre-run check only verifies the database and never creates or migrates it.
$database = 'data\browser_demo.db'
if (-not (Test-Path -LiteralPath $database)) {
    Write-Host "Creating analysis database $database..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force 'data' | Out-Null
    & $uvExe @uvPre run --no-sync python -c "from pathlib import Path; from app.models.base import create_engine_and_session, init_db; e, _ = create_engine_and_session('sqlite:///' + Path(r'$database').resolve().as_posix()); init_db(e); e.dispose()"
    if ($LASTEXITCODE -ne 0) { Fail 'Could not create the analysis database (see above).' }
} else {
    & $uvExe @uvPre run --no-sync python -m app.migrate --database $database
    if ($LASTEXITCODE -ne 0) { Fail 'Could not update the analysis database schema (see above). Close other copies of the app and retry.' }
}

# 5. Web app
$open = @()
if (-not $NoBrowser) { $open = @('--open') }
Write-Host ''
Write-Host "Credit memo web app: http://127.0.0.1:$Port/analysis/new   (Ctrl+C to stop)" -ForegroundColor Green
Write-Host 'Outputs: output\browser_demo\   Database: data\browser_demo.db'
& $uvExe @uvPre run --no-sync python -m app.preview --port $Port @open
