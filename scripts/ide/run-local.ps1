[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("agent-runtime", "core-api", "frontend", "speech-gateway", "prepare-database")]
    [string]$Target,

    [switch]$CheckOnly,

    # prepare-database only: apply migrations even if the database is not local.
    [switch]$AllowRemote
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))

function Assert-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Required directory not found: $Path"
    }
}

function Assert-Executable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-LocalCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Push-Location -LiteralPath $WorkingDirectory
    try {
        Write-Host "[kinsun] $Executable $($Arguments -join ' ')"
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command '$Executable' exited with code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }
}

function Test-LocalDatabase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    # Let alembic/env.py resolve the URL offline (it never connects), so this
    # judges exactly the database Alembic would use. Only the classification is
    # printed, never the URL; any failure counts as not local.
    $probe = @'
import os

scope = "unknown"
try:
    from alembic.config import Config
    from alembic.runtime.environment import EnvironmentContext
    from alembic.script import ScriptDirectory
    from sqlalchemy.engine import make_url

    class UrlResolved(Exception):
        pass

    def stop_at_configure(**kwargs):
        raise UrlResolved(kwargs["url"])

    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    context = EnvironmentContext(config, script, as_sql=True)
    context.configure = stop_at_configure
    try:
        with context:
            script.run_env()
    except UrlResolved as resolved:
        url = make_url(resolved.args[0])
        loopback = (url.host or "").lower() in {"localhost", "127.0.0.1", "::1"}
        # libpq can send a loopback URL elsewhere through these overrides.
        redirected = {"host", "hostaddr", "service"} & set(url.query) or any(
            os.environ.get(name) for name in ("PGHOSTADDR", "PGSERVICE")
        )
        scope = "local" if loopback and not redirected else "remote"
except Exception:
    pass
print("kinsun-database-scope=" + scope)
'@

    Push-Location -LiteralPath $WorkingDirectory
    try {
        $output = $probe | & uv run python -
        return ($LASTEXITCODE -eq 0) -and (@($output) -contains "kinsun-database-scope=local")
    }
    finally {
        Pop-Location
    }
}

Assert-Directory -Path $repositoryRoot

$configuration = switch ($Target) {
    "agent-runtime" {
        @{
            WorkingDirectory = Join-Path $repositoryRoot "services\agent-runtime"
            Executable       = "uv"
            Arguments        = @("run", "uvicorn", "--app-dir", "src", "agent_runtime.app:app", "--reload", "--port", "8001")
        }
    }
    "core-api" {
        @{
            WorkingDirectory = Join-Path $repositoryRoot "services\core-api"
            Executable       = "uv"
            Arguments        = @("run", "uvicorn", "app.main:app", "--reload", "--port", "8000")
        }
    }
    "frontend" {
        @{
            WorkingDirectory = $repositoryRoot
            Executable       = "npm"
            Arguments        = @("run", "dev", "--workspace", "@elderly-care/frontend")
        }
    }
    "speech-gateway" {
        @{
            WorkingDirectory = Join-Path $repositoryRoot "services\speech-gateway"
            Executable       = "uv"
            Arguments        = @("run", "uvicorn", "--app-dir", "src", "speech_gateway.app:app", "--reload", "--port", "8002")
        }
    }
    "prepare-database" {
        @{
            WorkingDirectory = Join-Path $repositoryRoot "services\core-api"
            Executable       = "uv"
            Arguments        = @()
        }
    }
}

Assert-Directory -Path $configuration.WorkingDirectory
Assert-Executable -Name $configuration.Executable

if ($CheckOnly) {
    Write-Host "[kinsun] check passed: target=$Target"
    Write-Host "[kinsun] repository=$repositoryRoot"
    Write-Host "[kinsun] working_directory=$($configuration.WorkingDirectory)"
    exit 0
}

Write-Host "[kinsun] starting target=$Target"

if ($Target -eq "prepare-database") {
    $isLocalDatabase = Test-LocalDatabase -WorkingDirectory $configuration.WorkingDirectory
    Write-Host "[kinsun] database scope: $(if ($isLocalDatabase) { 'local' } else { 'remote or undetermined' })"
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "current")
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "heads")
    if (-not $isLocalDatabase -and -not $AllowRemote) {
        Write-Host "[kinsun] Migrations NOT applied: the database is not confirmed to be local."
        Write-Host "[kinsun] Review the pending migrations, then re-run with -AllowRemote to apply them."
        exit 2
    }
    Write-Host "[kinsun] Applying pending Alembic migrations (upgrade only, no reset or downgrade)."
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "upgrade", "head")
    Write-Host "[kinsun] database preparation completed"
    exit 0
}

Invoke-LocalCommand `
    -WorkingDirectory $configuration.WorkingDirectory `
    -Executable $configuration.Executable `
    -Arguments $configuration.Arguments
