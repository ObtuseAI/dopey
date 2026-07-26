[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$expectedRoot = "C:\Users\CH\dopey"
if (-not $repoRoot.Equals($expectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Repository root mismatch: expected=$expectedRoot actual=$repoRoot"
}

$systemRoot = [Environment]::GetEnvironmentVariable("SystemRoot")
if ([string]::IsNullOrWhiteSpace($systemRoot)) {
    throw "SystemRoot is required to resolve the trusted Windows Script Host"
}
$wscriptPath = [System.IO.Path]::GetFullPath((Join-Path $systemRoot "System32\wscript.exe"))
$launcherPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "run_scheduled_hidden.vbs")).Path
$auditPath = Join-Path $repoRoot "artifacts\dopey\scheduler\durable_schedule_installation.json"

$activeTasks = [ordered]@{
    "DOPEY_AccelerationCycle" = "acceleration_cycle"
    "DOPEY_DailyRitual" = "daily_ritual"
    "DOPEY_MondayPreflight" = "monday_preflight"
    "DOPEY_Nightly" = "nightly"
    "DOPEY_WeekendSoak" = "weekend_soak"
}
$subsumedTasks = [ordered]@{
    "DOPEY_Intraday" = "intraday"
}

function Get-ExpectedArguments {
    param(
        [Parameter(Mandatory = $true)]
        [string]$CommandKey
    )

    return '//B //NoLogo "' + $launcherPath + '" ' + $CommandKey
}

function Test-OperatorIdentity {
    param(
        [Parameter(Mandatory = $true)]
        [string]$UserId
    )

    $allowedIdentities = @(
        $env:USERNAME,
        "$env:USERDOMAIN\$env:USERNAME"
    )
    return @(
        $allowedIdentities | Where-Object {
            $UserId.Equals($_, [System.StringComparison]::OrdinalIgnoreCase)
        }
    ).Count -eq 1
}

function Get-AllowlistedTask {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TaskName,
        [Parameter(Mandatory = $true)]
        [string]$CommandKey
    )

    $task = Get-ScheduledTask -TaskPath "\" -TaskName $TaskName -ErrorAction Stop
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        throw "Scheduled task action count is not one: task=$TaskName count=$($actions.Count)"
    }
    $actualExecute = [System.IO.Path]::GetFullPath([string]$actions[0].Execute)
    $actualArguments = ([string]$actions[0].Arguments).Trim()
    $expectedArguments = Get-ExpectedArguments -CommandKey $CommandKey
    if (-not $actualExecute.Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Scheduled task executable is outside the allowlist: task=$TaskName actual=$actualExecute expected=$wscriptPath"
    }
    if (-not $actualArguments.Equals($expectedArguments, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Scheduled task arguments are outside the allowlist: task=$TaskName actual=$actualArguments expected=$expectedArguments"
    }
    if (-not (Test-OperatorIdentity -UserId ([string]$task.Principal.UserId))) {
        throw "Scheduled task principal is not the current operator: task=$TaskName actual=$($task.Principal.UserId) expected=$env:USERNAME or $env:USERDOMAIN\$env:USERNAME"
    }
    if ([string]$task.Principal.LogonType -ne "Interactive") {
        throw "Scheduled task must remain interactive and credential-free: task=$TaskName logon_type=$($task.Principal.LogonType)"
    }
    if ([string]$task.Principal.RunLevel -ne "Limited") {
        throw "Scheduled task must remain limited privilege: task=$TaskName run_level=$($task.Principal.RunLevel)"
    }
    return $task
}

function New-DurableSettings {
    return New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
        -StartWhenAvailable `
        -WakeToRun `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)
}

function Test-LogonTrigger {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$Triggers
    )

    return @(
        $Triggers | Where-Object {
            $_.CimClass.CimClassName -eq "MSFT_TaskLogonTrigger" -and
            (Test-OperatorIdentity -UserId ([string]$_.UserId))
        }
    ).Count -eq 1
}

function Assert-DurablePostcondition {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TaskName,
        [Parameter(Mandatory = $true)]
        [bool]$RequiresLogonTrigger
    )

    $task = Get-ScheduledTask -TaskPath "\" -TaskName $TaskName -ErrorAction Stop
    $settings = $task.Settings
    $failures = [System.Collections.Generic.List[string]]::new()
    if (-not [bool]$settings.Enabled) { $failures.Add("disabled") }
    if (-not [bool]$settings.StartWhenAvailable) { $failures.Add("start_when_available_false") }
    if (-not [bool]$settings.WakeToRun) { $failures.Add("wake_to_run_false") }
    if ([bool]$settings.DisallowStartIfOnBatteries) { $failures.Add("battery_start_blocked") }
    if ([bool]$settings.StopIfGoingOnBatteries) { $failures.Add("battery_transition_stops_task") }
    if ([int]$settings.RestartCount -ne 3) { $failures.Add("restart_count_not_three") }
    if ([string]$settings.RestartInterval -ne "PT5M") { $failures.Add("restart_interval_not_five_minutes") }
    if ([string]$settings.MultipleInstances -ne "IgnoreNew") { $failures.Add("multiple_instances_not_ignore_new") }
    if ($RequiresLogonTrigger -and -not (Test-LogonTrigger -Triggers @($task.Triggers))) {
        $failures.Add("operator_logon_trigger_missing")
    }
    if ($failures.Count -gt 0) {
        throw "Durable schedule postcondition failed: task=$TaskName failures=$($failures -join ',')"
    }
    return $task
}

$results = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $activeTasks.GetEnumerator()) {
    $taskName = [string]$entry.Key
    $commandKey = [string]$entry.Value
    $task = Get-AllowlistedTask -TaskName $taskName -CommandKey $commandKey
    $triggers = @($task.Triggers)
    $logonTriggerAdded = $false
    if ($taskName -eq "DOPEY_AccelerationCycle" -and -not (Test-LogonTrigger -Triggers $triggers)) {
        $logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $logonTrigger.Delay = "PT45S"
        $triggers += $logonTrigger
        $logonTriggerAdded = $true
    }
    $settings = New-DurableSettings
    Set-ScheduledTask -TaskPath "\" -TaskName $taskName -Trigger $triggers -Settings $settings -ErrorAction Stop | Out-Null
    Enable-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop | Out-Null
    $verified = Assert-DurablePostcondition -TaskName $taskName -RequiresLogonTrigger ($taskName -eq "DOPEY_AccelerationCycle")
    $info = Get-ScheduledTaskInfo -TaskPath "\" -TaskName $taskName -ErrorAction Stop
    $results.Add([pscustomobject]@{
        task_name = $taskName
        status = [string]$verified.State
        enabled = [bool]$verified.Settings.Enabled
        start_when_available = [bool]$verified.Settings.StartWhenAvailable
        wake_to_run = [bool]$verified.Settings.WakeToRun
        battery_continuity = -not [bool]$verified.Settings.DisallowStartIfOnBatteries -and -not [bool]$verified.Settings.StopIfGoingOnBatteries
        restart_count = [int]$verified.Settings.RestartCount
        restart_interval = [string]$verified.Settings.RestartInterval
        logon_trigger_added = $logonTriggerAdded
        trigger_types = @($verified.Triggers | ForEach-Object { $_.CimClass.CimClassName })
        last_run_time = $info.LastRunTime.ToString("o")
        last_task_result = [int]$info.LastTaskResult
        next_run_time = if ($null -eq $info.NextRunTime) { $null } else { $info.NextRunTime.ToString("o") }
        hidden_launcher = $true
        paper_only = $true
        live_blocked = $true
    })
}

foreach ($entry in $subsumedTasks.GetEnumerator()) {
    $taskName = [string]$entry.Key
    $commandKey = [string]$entry.Value
    $task = Get-AllowlistedTask -TaskName $taskName -CommandKey $commandKey
    if ([bool]$task.Settings.Enabled) {
        throw "Subsumed legacy task unexpectedly enabled: task=$taskName"
    }
    $results.Add([pscustomobject]@{
        task_name = $taskName
        status = [string]$task.State
        enabled = $false
        subsumed_by = "DOPEY_AccelerationCycle"
        duplicate_scanner_prevented = $true
        hidden_launcher = $true
        paper_only = $true
        live_blocked = $true
    })
}

$record = [ordered]@{
    artifact_type = "dopey_durable_research_schedule_installation"
    schedule_version = "dopey-durable-research-schedule-v1"
    generated_utc = [DateTimeOffset]::UtcNow.ToString("o")
    repository_root = $repoRoot
    launcher = $launcherPath
    launcher_sha256 = (Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256).Hash.ToLowerInvariant()
    active_task_count = $activeTasks.Count
    subsumed_task_count = $subsumedTasks.Count
    tasks = @($results)
    auto_resume_policy = "logon_kick_plus_calendar_triggers_plus_start_when_available_plus_failure_restart"
    credentials_stored = $false
    broker_authority = $false
    order_authority = $false
    paper_only = $true
    live_blocked = $true
}

$auditDirectory = Split-Path -Parent $auditPath
New-Item -ItemType Directory -Path $auditDirectory -Force | Out-Null
$temporaryAuditPath = "$auditPath.tmp"
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryAuditPath -Encoding utf8
Move-Item -LiteralPath $temporaryAuditPath -Destination $auditPath -Force
$record | ConvertTo-Json -Depth 8
