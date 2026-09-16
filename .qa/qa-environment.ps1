# Shared Windows QA setup. Dot-source this file; it does not start services.
function Import-QaEnvironment {
    param([Parameter(Mandatory = $true)][string]$RepositoryRoot)
    $qaPython = Join-Path $RepositoryRoot 'services/core-api/.venv/Scripts/python.exe'
    $qaEnvFile = Join-Path $RepositoryRoot '.env'
    if (-not (Test-Path -LiteralPath $qaPython -PathType Leaf)) {
        throw 'Run uv sync --extra test --extra dev in services/core-api first.'
    }
    if (-not (Test-Path -LiteralPath $qaEnvFile -PathType Leaf)) {
        throw 'Configure the repository .env locally before starting QA.'
    }
    # Capture the parser output privately. Never write it to the console or logs.
    $qaEnvironmentJson = & $qaPython -c 'import json, sys; from dotenv import dotenv_values; print(json.dumps(dotenv_values(sys.argv[1])))' $qaEnvFile
    if ($LASTEXITCODE -ne 0) { throw 'Environment parsing failed.' }
    $qaEnvironment = $qaEnvironmentJson | ConvertFrom-Json
    if (($qaEnvironment.APP_ENV -and $qaEnvironment.APP_ENV -ne 'development') -or
        ($env:APP_ENV -and $env:APP_ENV -ne 'development')) {
        throw 'These launchers only support a development environment.'
    }
    foreach ($qaProperty in $qaEnvironment.PSObject.Properties) {
        if ($null -ne $qaProperty.Value) {
            [Environment]::SetEnvironmentVariable($qaProperty.Name, [string]$qaProperty.Value, 'Process')
        }
    }
    $qaEnvironmentJson = $null
    $qaEnvironment = $null
    $env:APP_ENV = 'development'
    $env:FAKE_AUTH_ENABLED = 'false'
    $env:FRONTEND_ORIGIN = 'http://localhost:3000'
    $env:CORE_API_INTERNAL_URL = 'http://127.0.0.1:8000'
}

function Assert-QaPortsAvailable {
    param([Parameter(Mandatory = $true)][int[]]$Ports)
    $qaListeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $Ports })
    if ($qaListeners.Count -ne 0) { throw 'QA ports are occupied; inspect existing services first.' }
}
