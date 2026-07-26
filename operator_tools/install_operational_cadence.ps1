[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$expectedRoot = "C:\Users\CH\dopey"
if (-not $repoRoot.Equals($expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Repository root mismatch: expected=$expectedRoot actual=$repoRoot"
}

$cadence = [ordered]@{
    "DOPEY_DailyRitual" = @{
        trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "15:15"
        expected_start = "15:15:00"
        cadence = "weekdays_15_15_local_after_market_close"
    }
    "DOPEY_ResearchSupervisor" = @{
        trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At "18:30"
        expected_start = "18:30:00"
        cadence = "weekdays_18_30_local_after_daily_ritual"
    }
    "DOPEY_Nightly" = @{
        trigger = New-ScheduledTaskTrigger -Daily -At "05:00"
        expected_start = "05:00:00"
        cadence = "daily_05_00_local_after_supervisor_budget"
    }
}

$records = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $cadence.GetEnumerator()) {
    $taskName = [string]$entry.Key
    $policy = $entry.Value
    $task = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop
    if ([string]$task.Settings.MultipleInstances -ne "IgnoreNew") {
        throw "Task overlap policy must remain IgnoreNew: task=$taskName actual=$($task.Settings.MultipleInstances)"
    }
    Set-ScheduledTask -TaskPath "\" -TaskName $taskName -Trigger $policy.trigger -ErrorAction Stop | Out-Null
    $verified = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop
    $triggers = @($verified.Triggers)
    if ($triggers.Count -ne 1) {
        throw "Operational cadence trigger count is not one: task=$taskName count=$($triggers.Count)"
    }
    $startTime = ([DateTimeOffset]::Parse([string]$triggers[0].StartBoundary)).ToString("HH:mm:ss")
    if ($startTime -ne [string]$policy.expected_start) {
        throw "Operational cadence start time mismatch: task=$taskName actual=$startTime expected=$($policy.expected_start)"
    }
    $info = Get-ScheduledTaskInfo -TaskPath "\" -TaskName $taskName -ErrorAction Stop
    $records.Add([pscustomobject]@{
        task_name = $taskName
        state = [string]$verified.State
        cadence = [string]$policy.cadence
        start_boundary = [string]$triggers[0].StartBoundary
        next_run_time = $info.NextRunTime.ToString("o")
        multiple_instances = [string]$verified.Settings.MultipleInstances
        execution_time_limit = [string]$verified.Settings.ExecutionTimeLimit
    })
}

$record = [ordered]@{
    artifact_type = "dopey_operational_cadence_installation"
    schedule_version = "dopey-operational-cadence-v1"
    generated_utc = [DateTimeOffset]::UtcNow.ToString("o")
    repository_root = $repoRoot
    timezone = "America/Chicago"
    task_count = $records.Count
    tasks = @($records)
    cadence_policy = "daily_ritual_then_supervisor_then_nightly_without_expected_overlap"
    credentials_stored = $false
    broker_authority_changed = $false
    options_authority_changed = $false
}

$auditPath = Join-Path $repoRoot "artifacts\dopey\scheduler\operational_cadence_installation.json"
$auditDirectory = Split-Path -Parent $auditPath
New-Item -ItemType Directory -Path $auditDirectory -Force | Out-Null
$temporaryAuditPath = "$auditPath.tmp"
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryAuditPath -Encoding utf8
Move-Item -LiteralPath $temporaryAuditPath -Destination $auditPath -Force
$record | ConvertTo-Json -Depth 8
