$ErrorActionPreference = 'Stop'
$chainRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'qa-environment.ps1')
Assert-QaPortsAvailable -Ports @(8001)
Import-QaEnvironment -RepositoryRoot $chainRoot
$chainAgent = Start-Process -FilePath "$chainRoot\services\agent-runtime\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','--app-dir','services/agent-runtime/src','agent_runtime.app:app','--host','127.0.0.1','--port','8001') -WorkingDirectory $chainRoot -WindowStyle Hidden -RedirectStandardOutput "$chainRoot\.qa\wave2-agent.stdout.log" -RedirectStandardError "$chainRoot\.qa\wave2-agent.stderr.log" -PassThru
[pscustomobject]@{agent_pid=$chainAgent.Id} | ConvertTo-Json -Compress
