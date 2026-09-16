$ErrorActionPreference = 'Stop'
$previousRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'qa-environment.ps1')
Assert-QaPortsAvailable -Ports @(3000, 8000)
Import-QaEnvironment -RepositoryRoot $previousRoot
$previousCore = Start-Process -FilePath "$previousRoot\services\core-api\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','--app-dir','services/core-api','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $previousRoot -WindowStyle Hidden -RedirectStandardOutput "$previousRoot\.qa\previous-real-core.stdout.log" -RedirectStandardError "$previousRoot\.qa\previous-real-core.stderr.log" -PassThru
$previousFront = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('../../node_modules/next/dist/bin/next','start','-p','3000','-H','127.0.0.1') -WorkingDirectory "$previousRoot\packages\frontend" -WindowStyle Hidden -RedirectStandardOutput "$previousRoot\.qa\previous-real-front.stdout.log" -RedirectStandardError "$previousRoot\.qa\previous-real-front.stderr.log" -PassThru
[pscustomobject]@{core_pid=$previousCore.Id;frontend_pid=$previousFront.Id} | ConvertTo-Json -Compress
