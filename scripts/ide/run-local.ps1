[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("agent-runtime", "core-api", "frontend", "speech-gateway", "prepare-database")]
    [string]$Target,

    [switch]$CheckOnly
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
    Write-Host "[kinsun] Applying additive Alembic migrations only (no reset or downgrade)."
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "current")
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "heads")
    Invoke-LocalCommand -WorkingDirectory $configuration.WorkingDirectory -Executable "uv" -Arguments @("run", "alembic", "upgrade", "head")
    Write-Host "[kinsun] database preparation completed"
    exit 0
}

Invoke-LocalCommand `
    -WorkingDirectory $configuration.WorkingDirectory `
    -Executable $configuration.Executable `
    -Arguments $configuration.Arguments
