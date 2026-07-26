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
$commandPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "research_supervisor.cmd")).Path
$taskName = "DOPEY_ResearchSupervisor"
$taskArguments = '//B //NoLogo "' + $launcherPath + '" research_supervisor'
$taskAction = New-ScheduledTaskAction -Execute $wscriptPath -Argument $taskArguments
$taskTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At "18:30"
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 15)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $taskAction `
    -Trigger $taskTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop
$taskInfo = Get-ScheduledTaskInfo -TaskPath "\" -TaskName $taskName -ErrorAction Stop
$actions = @($task.Actions)
if ($actions.Count -ne 1) {
    throw "Research supervisor task action count is not one: task=$taskName count=$($actions.Count)"
}
if (-not ([string]$actions[0].Execute).Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Research supervisor executable mismatch: task=$taskName actual=$($actions[0].Execute) expected=$wscriptPath"
}
if (-not ([string]$actions[0].Arguments).Trim().Equals($taskArguments, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Research supervisor arguments mismatch: task=$taskName actual=$($actions[0].Arguments) expected=$taskArguments"
}
if ([string]$task.Settings.MultipleInstances -ne "IgnoreNew") {
    throw "Research supervisor overlap policy mismatch: task=$taskName actual=$($task.Settings.MultipleInstances)"
}
if ([string]$task.Settings.ExecutionTimeLimit -ne "PT0S") {
    throw "Research supervisor execution limit must be disabled for graceful completion: task=$taskName actual=$($task.Settings.ExecutionTimeLimit)"
}

$auditPath = Join-Path $repoRoot "artifacts\dopey\scheduler\research_supervisor_schedule_installation.json"
$auditDirectory = Split-Path -Parent $auditPath
New-Item -ItemType Directory -Path $auditDirectory -Force | Out-Null
$record = [ordered]@{
    artifact_type = "dopey_research_supervisor_schedule_installation"
    schedule_version = "dopey-research-supervisor-schedule-v2"
    generated_utc = [DateTimeOffset]::UtcNow.ToString("o")
    repository_root = $repoRoot
    task_name = $taskName
    state = [string]$task.State
    next_run_time = $taskInfo.NextRunTime.ToString("o")
    launcher = $launcherPath
    launcher_sha256 = (Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256).Hash.ToLowerInvariant()
    command = $commandPath
    command_sha256 = (Get-FileHash -LiteralPath $commandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    multiple_instances = [string]$task.Settings.MultipleInstances
    execution_time_limit = [string]$task.Settings.ExecutionTimeLimit
    cadence = "weekdays_18_30_local"
    credentials_stored = $false
    broker_authority = $false
    order_authority = $false
    paper_only = $true
    live_blocked = $true
}
$temporaryAuditPath = "$auditPath.tmp"
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporaryAuditPath -Encoding utf8
Move-Item -LiteralPath $temporaryAuditPath -Destination $auditPath -Force
$record | ConvertTo-Json -Depth 6
