#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Validate','Start','RunOnce','RunForever','Status','Stop','StopIfUnsafe','ReportOnly')]
    [string]$Mode = 'Status',
    [string]$OperatorApproved = 'false',
    [int]$LoopDelaySeconds = 30
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'blunder-full-autonomy-common.ps1')

$operatorApprovedBool = ConvertTo-BlunderBoolean -Value $OperatorApproved
$runtimePath = Join-Path $script:BlunderFullAutonomyArtifactRoot 'continuous_autonomy_runtime.json'
$stopPath = Join-Path $script:BlunderFullAutonomyArtifactRoot 'continuous_autonomy_stop.json'

if ($Mode -eq 'Validate') {
    $policy = Write-BlunderAutonomyPolicyRecord -Mode 'Validate'
    $queue = Write-BlunderQueueReplenishmentRecord -Mode 'Validate' -AdmitCandidates $false
    $record = [ordered]@{
        classification = $script:BlunderFullAutonomyClassification
        mode = $Mode
        timestamp = (Get-Date -Format 'o')
        policyResult = $policy.result
        queueResult = $queue.result
        runForeverReady = $true
        duplicateStartGuard = $true
        benchmarkLaunchesForbidden = $true
        budgetTokenRequestCostCapsUsedAsBlockers = $false
        result = $(if ($policy.result -eq 'PASS' -and $queue.result -eq 'PASS') { 'PASS' } else { 'FAIL' })
    }
    $record | ConvertTo-Json -Depth 100
    return
}

if ($Mode -eq 'StopIfUnsafe') {
    $safety = Get-BlunderForbiddenProcessState
    if ($safety.result -ne 'PASS') {
        Write-BlunderRuntimeStatus -Status 'STOPPED_UNSAFE' -Reason 'Forbidden process state detected.' | Out-Null
        throw 'Continuous autonomy stopped by hard safety state.'
    }
    $safety | ConvertTo-Json -Depth 100
    return
}

if ($Mode -eq 'Status' -or $Mode -eq 'ReportOnly') {
    $runtime = Read-BlunderJsonFile -Path $runtimePath
    $idle = Get-BlunderStatusSnapshot
    $record = [ordered]@{
        classification = $script:BlunderFullAutonomyClassification
        mode = $Mode
        timestamp = (Get-Date -Format 'o')
        runtime = $runtime
        idleStatusReadable = $idle.readable
        idleStatus = $idle.parsed
        runForeverReady = $true
        benchmarkLaunched = $false
        result = 'PASS'
    }
    $record | ConvertTo-Json -Depth 100
    return
}

if ($Mode -eq 'Stop') {
    Write-BlunderJsonFile -Value ([ordered]@{ requested = $true; requestedAt = (Get-Date -Format 'o'); requestedByPid = $PID }) -Path $stopPath | Out-Null
    $record = Write-BlunderRuntimeStatus -Status 'STOPPED' -Reason 'Operator stop requested.'
    $record | ConvertTo-Json -Depth 100
    return
}

if ($Mode -in @('Start','RunOnce','RunForever') -and -not $operatorApprovedBool) {
    throw "OperatorApproved true is required for $Mode."
}

if ($Mode -eq 'Start') {
    $existing = Read-BlunderJsonFile -Path $runtimePath
    if ($existing -and $existing.status -eq 'RUNNING') {
        $existing | ConvertTo-Json -Depth 100
        return
    }
    if (Test-Path -LiteralPath (Resolve-BlunderPath -Path $stopPath)) {
        Remove-Item -LiteralPath (Resolve-BlunderPath -Path $stopPath) -Force
    }
    $record = Write-BlunderRuntimeStatus -Status 'RUNNING' -Reason 'Operator-approved autonomy runtime record started.'
    $record | ConvertTo-Json -Depth 100
    return
}

if ($Mode -eq 'RunOnce') {
    $runtime = Read-BlunderJsonFile -Path $runtimePath
    if (-not $runtime -or $runtime.status -ne 'RUNNING') {
        Write-BlunderRuntimeStatus -Status 'RUNNING' -Reason 'RunOnce started runtime record.' | Out-Null
    }
    $summary = Write-BlunderBootstrapRun -TargetPasses 3
    Write-BlunderRuntimeStatus -Status 'STOPPED' -Reason 'RunOnce completed clean bootstrap passes.' | Out-Null
    $summary | ConvertTo-Json -Depth 100
    return
}

if ($Mode -eq 'RunForever') {
    Write-BlunderRuntimeStatus -Status 'RUNNING' -Reason 'RunForever foreground loop started.' | Out-Null
    while ($true) {
        if (Test-Path -LiteralPath (Resolve-BlunderPath -Path $stopPath)) {
            Write-BlunderRuntimeStatus -Status 'STOPPED' -Reason 'Stop file observed.' | Out-Null
            break
        }
        Write-BlunderBootstrapRun -TargetPasses 3 | Out-Null
        Start-Sleep -Seconds $LoopDelaySeconds
    }
    (Read-BlunderJsonFile -Path $runtimePath) | ConvertTo-Json -Depth 100
}
