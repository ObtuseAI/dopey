#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Status','Start','Stop','Validate','RunOnce','RunForever','DunceRegression','Replenish','Promote','MineArtifacts','BenchmarkPrepare','BenchmarkReportOnly','Handoff')]
    [string]$Command = 'Status',
    [string]$OperatorApproved = 'false'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'blunder-full-autonomy-common.ps1')

switch ($Command) {
    'Status' {
        & (Join-Path $PSScriptRoot 'blunder-continuous-autonomy.ps1') -Mode Status
        return
    }
    'Start' {
        & (Join-Path $PSScriptRoot 'blunder-continuous-autonomy.ps1') -Mode Start -OperatorApproved $OperatorApproved
        return
    }
    'Stop' {
        & (Join-Path $PSScriptRoot 'blunder-continuous-autonomy.ps1') -Mode Stop
        return
    }
    'Validate' {
        Write-BlunderAutonomyPolicyRecord -Mode 'Validate' | Out-Null
        Write-BlunderBudgetGateRecord | Out-Null
        Write-BlunderQueueReplenishmentRecord -Mode 'Validate' -AdmitCandidates $false | Out-Null
        Write-BlunderPromotionPolicyRecord -Mode 'Validate' | Out-Null
        Write-BlunderArtifactMiningRecord -Mode 'Validate' | Out-Null
        Write-BlunderSkillTokenRecord -Mode 'Validate' | Out-Null
        Write-BlunderControlSurfaceRecord | Out-Null
        Write-BlunderOperatorTodo | Out-Null
        Write-BlunderOperatorHandoff | Out-Null
        $summary = Write-BlunderFinalValidationSummary
        $summary | ConvertTo-Json -Depth 100
        return
    }
    'RunOnce' {
        & (Join-Path $PSScriptRoot 'blunder-continuous-autonomy.ps1') -Mode RunOnce -OperatorApproved $OperatorApproved
        return
    }
    'RunForever' {
        & (Join-Path $PSScriptRoot 'blunder-continuous-autonomy.ps1') -Mode RunForever -OperatorApproved $OperatorApproved
        return
    }
    'DunceRegression' {
        & (Join-Path $PSScriptRoot 'blunder-dunce-proof-regression-pack.ps1') -Mode Validate
        return
    }
    'Replenish' {
        if (-not (ConvertTo-BlunderBoolean -Value $OperatorApproved)) { throw 'OperatorApproved true is required for Replenish.' }
        & (Join-Path $PSScriptRoot 'blunder-autonomous-queue-replenishment.ps1') -Mode ReplenishOnce
        return
    }
    'Promote' {
        if (-not (ConvertTo-BlunderBoolean -Value $OperatorApproved)) { throw 'OperatorApproved true is required for Promote.' }
        & (Join-Path $PSScriptRoot 'blunder-autonomous-promotion.ps1') -Mode PromoteSafe
        return
    }
    'MineArtifacts' {
        & (Join-Path $PSScriptRoot 'blunder-artifact-miner.ps1') -Mode MineOnce
        return
    }
    'BenchmarkPrepare' {
        & (Join-Path $PSScriptRoot 'benchmark-appliance-mode.ps1') -Mode Prepare
        return
    }
    'BenchmarkReportOnly' {
        & (Join-Path $PSScriptRoot 'benchmark-appliance-mode.ps1') -Mode ReportOnly
        return
    }
    'Handoff' {
        Write-BlunderOperatorTodo | Out-Null
        $handoffPath = Write-BlunderOperatorHandoff
        $report = Write-BlunderFinalReport
        [ordered]@{
            classification = $script:BlunderFullAutonomyClassification
            handoffPath = $handoffPath
            finalReportPath = $report.finalReportPath
            terminalState = $report.terminalState
            result = 'PASS'
        } | ConvertTo-Json -Depth 100
        return
    }
}
