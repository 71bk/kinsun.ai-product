param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'qa-environment.ps1')
Assert-QaPortsAvailable -Ports @(3000, 8000)
Import-QaEnvironment -RepositoryRoot $repoRoot
Set-Location -LiteralPath $repoRoot
if (-not $SkipBuild) {
    npm.cmd run build --workspace @elderly-care/frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
}
$coreProcess = Start-Process -FilePath "$repoRoot\services\core-api\.venv\Scripts\python.exe" -ArgumentList @('-m','uvicorn','--app-dir','services/core-api','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $repoRoot -WindowStyle Hidden -RedirectStandardOutput "$repoRoot\.qa\wave2-core.stdout.log" -RedirectStandardError "$repoRoot\.qa\wave2-core.stderr.log" -PassThru
$frontProcess = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @('../../node_modules/next/dist/bin/next','start','-p','3000','-H','127.0.0.1') -WorkingDirectory "$repoRoot\packages\frontend" -WindowStyle Hidden -RedirectStandardOutput "$repoRoot\.qa\wave2-front.stdout.log" -RedirectStandardError "$repoRoot\.qa\wave2-front.stderr.log" -PassThru
[pscustomobject]@{core_pid=$coreProcess.Id;frontend_pid=$frontProcess.Id} | ConvertTo-Json -Compress
