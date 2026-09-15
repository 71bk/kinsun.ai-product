$ErrorActionPreference = 'Stop'
$ragRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'qa-environment.ps1')
Assert-QaPortsAvailable -Ports @(3000, 8000, 8001)
Import-QaEnvironment -RepositoryRoot $ragRoot
$ragStamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$ragAgent = Start-Process -FilePath "$ragRoot\services\agent-runtime\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','--app-dir','services/agent-runtime/src','agent_runtime.app:app','--host','127.0.0.1','--port','8001') -WorkingDirectory $ragRoot -WindowStyle Hidden -RedirectStandardOutput "$ragRoot\.qa\law-agent-$ragStamp.stdout.log" -RedirectStandardError "$ragRoot\.qa\law-agent-$ragStamp.stderr.log" -PassThru
$ragCore = Start-Process -FilePath "$ragRoot\services\core-api\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','--app-dir','services/core-api','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $ragRoot -WindowStyle Hidden -RedirectStandardOutput "$ragRoot\.qa\law-core-$ragStamp.stdout.log" -RedirectStandardError "$ragRoot\.qa\law-core-$ragStamp.stderr.log" -PassThru
$ragFrontend = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('../../node_modules/next/dist/bin/next','start','-p','3000','-H','127.0.0.1') -WorkingDirectory "$ragRoot\packages\frontend" -WindowStyle Hidden -RedirectStandardOutput "$ragRoot\.qa\law-frontend-$ragStamp.stdout.log" -RedirectStandardError "$ragRoot\.qa\law-frontend-$ragStamp.stderr.log" -PassThru
[pscustomobject]@{agent_pid=$ragAgent.Id;core_pid=$ragCore.Id;frontend_pid=$ragFrontend.Id;log_stamp=$ragStamp} | ConvertTo-Json -Compress
