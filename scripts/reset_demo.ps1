[CmdletBinding()]
param(
    [switch]$ConfirmLocalReset
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repoRoot ".env"

if (-not $env:DATABASE_URL -and (Test-Path -LiteralPath $envFile)) {
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        if ($line -match '^\s*DATABASE_URL\s*=\s*(.+?)\s*$') {
            $env:DATABASE_URL = $Matches[1].Trim('"', "'")
            break
        }
    }
}

if (-not $env:DATABASE_URL) {
    throw "DATABASE_URL is required. Copy .env.example to .env first."
}
if ($env:APP_ENV -and $env:APP_ENV.ToLowerInvariant() -ne "development") {
    throw "Demo reset is allowed only when APP_ENV=development."
}

$databaseUri = [System.Uri]$env:DATABASE_URL
$allowedHosts = @("localhost", "127.0.0.1", "::1")
if ($databaseUri.Scheme -ne "postgresql+asyncpg" -or
    $allowedHosts -notcontains $databaseUri.Host -or
    $databaseUri.AbsolutePath -ne "/kinsun") {
    throw "Demo reset is restricted to postgresql+asyncpg on localhost database kinsun."
}
if (-not $ConfirmLocalReset) {
    throw "This deletes and rebuilds eldercare_ai in local database kinsun. Re-run with -ConfirmLocalReset."
}

Write-Host "Reset target: $($databaseUri.Host)$($databaseUri.AbsolutePath), schema eldercare_ai"
$uv = Get-Command uv -ErrorAction SilentlyContinue
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not $uv -and -not (Test-Path -LiteralPath $python)) {
    throw "Neither uv nor the repository .venv Python is available. Run uv sync first."
}

Push-Location (Join-Path $repoRoot "services/core-api")
try {
    if ($uv) {
        uv run alembic downgrade base
        uv run alembic upgrade head
    }
    else {
        & $python -m alembic downgrade base
        & $python -m alembic upgrade head
    }
}
finally {
    Pop-Location
}

Push-Location $repoRoot
try {
    if ($uv) {
        uv run --project services/core-api python scripts/seed_demo.py
    }
    else {
        & $python scripts/seed_demo.py
    }
}
finally {
    Pop-Location
}
