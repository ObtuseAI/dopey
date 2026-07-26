#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Validate','EvaluateCandidate','PromoteSafe','Rollback','ReportOnly')]
    [string]$Mode = 'Validate'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'blunder-full-autonomy-common.ps1')

$record = Write-BlunderPromotionPolicyRecord -Mode $Mode
$record | ConvertTo-Json -Depth 100
