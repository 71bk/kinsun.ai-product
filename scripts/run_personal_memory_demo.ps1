param([Parameter(Mandatory=$true)][ValidateSet('core','agent','front')][string]$Service)
$ErrorActionPreference = 'Stop'
$demoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $demoRoot '.qa/qa-environment.ps1')
Import-QaEnvironment -RepositoryRoot $demoRoot
$env:FRONTEND_ORIGIN = 'http://localhost:3110'
$env:CORE_API_INTERNAL_URL = 'http://127.0.0.1:8010'
$env:AGENT_RUNTIME_URL = 'http://127.0.0.1:8011'
$env:EVIDENCE_AWARE_MEMORY = 'true'
$env:PERSONAL_MEMORY_ENABLED = 'true'
$env:AUTO_LOW_RISK_MEMORY = 'false'
Set-Location -LiteralPath $demoRoot
if ($Service -eq 'core') {
    & "$demoRoot/services/core-api/.venv/Scripts/python.exe" -m uvicorn --app-dir services/core-api app.main:app --host 127.0.0.1 --port 8010
} elseif ($Service -eq 'agent') {
    if (!$env:MODEL_PROVIDER -or $env:MODEL_PROVIDER -eq 'mock') { throw 'Configure a real MODEL_PROVIDER in .env for recording.' }
    & "$demoRoot/services/agent-runtime/.venv/Scripts/python.exe" -m uvicorn --app-dir services/agent-runtime/src agent_runtime.app:app --host 127.0.0.1 --port 8011
} else {
    Set-Location -LiteralPath "$demoRoot/packages/frontend"
    & node.exe ../../node_modules/next/dist/bin/next start -p 3110 -H 127.0.0.1
}
