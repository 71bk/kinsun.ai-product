[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Profile,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Region,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{12}$')]
    [string]$ExpectedAccountId
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host "ok    $Message"
}

$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
if ($null -eq $awsCommand) {
    throw "AWS CLI v2 was not found on PATH. Install it before running this preflight."
}

$versionOutput = & aws --version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Unable to execute AWS CLI."
}

$versionText = [string]::Join(" ", @($versionOutput))
if ($versionText -notmatch '^aws-cli/2\.') {
    throw "AWS CLI v2 is required; detected: $versionText"
}
Write-Check "AWS CLI v2 is available"

$previousPager = $env:AWS_PAGER
try {
    $env:AWS_PAGER = ""
    $identityOutput = & aws sts get-caller-identity `
        --profile $Profile `
        --region $Region `
        --output json `
        --no-cli-pager 2>&1
    $identityExitCode = $LASTEXITCODE
}
finally {
    $env:AWS_PAGER = $previousPager
}

if ($identityExitCode -ne 0) {
    throw "AWS identity lookup failed for the selected profile and Region. Refresh the approved SSO session and retry."
}

try {
    $identity = [string]::Join([Environment]::NewLine, @($identityOutput)) | ConvertFrom-Json
}
catch {
    throw "AWS identity lookup returned invalid JSON."
}

if ($null -eq $identity.Account -or [string]$identity.Account -notmatch '^\d{12}$') {
    throw "AWS identity lookup did not return a valid account ID."
}

if ([string]$identity.Account -ne $ExpectedAccountId) {
    throw "AWS account mismatch. Refusing to continue with the selected profile."
}

if ([string]::IsNullOrWhiteSpace([string]$identity.Arn)) {
    throw "AWS identity lookup did not return an ARN."
}

$accountSuffix = $ExpectedAccountId.Substring(8, 4)
Write-Check "AWS credentials are valid"
Write-Check "expected AWS account matched (********$accountSuffix)"
Write-Check "explicit Region selected: $Region"

$configuredRegionOutput = & aws configure get region --profile $Profile 2>$null
$configuredRegionExitCode = $LASTEXITCODE
$configuredRegion = [string]::Join("", @($configuredRegionOutput)).Trim()
if ($configuredRegionExitCode -eq 0 -and
    -not [string]::IsNullOrWhiteSpace($configuredRegion) -and
    $configuredRegion -ne $Region) {
    Write-Warning "Profile default Region differs from the explicit Region. This preflight used the explicit Region."
}

Write-Host ""
Write-Host "AWS access preflight passed. No deployment or resource existence was inferred."
