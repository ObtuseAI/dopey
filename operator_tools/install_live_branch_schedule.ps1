[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$projectMarker = Join-Path $repoRoot "pyproject.toml"
$commandMarker = Join-Path $repoRoot "operator_tools\live_branch.cmd"
if (
    -not (Test-Path -LiteralPath $projectMarker -PathType Leaf) -or
    -not (Test-Path -LiteralPath $commandMarker -PathType Leaf)
) {
    throw "Resolved repository root lacks required DOPEY release markers: root=$repoRoot"
}

$systemRoot = [Environment]::GetEnvironmentVariable("SystemRoot")
if ([string]::IsNullOrWhiteSpace($systemRoot)) {
    throw "SystemRoot is required to resolve the trusted Windows Script Host"
}
$wscriptPath = [System.IO.Path]::GetFullPath((Join-Path $systemRoot "System32\wscript.exe"))
$launcherPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "run_scheduled_hidden.vbs")).Path
$commandPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "live_branch.cmd")).Path
$taskName = "DOPEY_LiveBranch"
$taskArguments = '//B //NoLogo "' + $launcherPath + '" live_branch'
$taskAction = New-ScheduledTaskAction -Execute $wscriptPath -Argument $taskArguments
$taskTrigger = New-ScheduledTaskTrigger `
    -Weekly `
    -WeeksInterval 1 `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "08:30"
$taskTrigger.Repetition.Interval = "PT15M"
$taskTrigger.Repetition.Duration = "PT6H30M"
$taskTrigger.Repetition.StopAtDurationEnd = $true
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 12) `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 2)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $taskAction `
    -Trigger $taskTrigger `
    -Principal $taskPrincipal `
    -Settings $taskSettings `
    -Force | Out-Null
Enable-ScheduledTask -TaskPath "\" -TaskName $taskName | Out-Null

$task = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop
$actions = @($task.Actions)
if ($actions.Count -ne 1) {
    throw "Live Branch task action count is not one: count=$($actions.Count)"
}
$actualExecute = [System.IO.Path]::GetFullPath([string]$actions[0].Execute)
$actualArguments = ([string]$actions[0].Arguments).Trim()
if (-not $actualExecute.Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Live Branch task executable mismatch: expected=$wscriptPath actual=$actualExecute"
}
if (-not $actualArguments.Equals($taskArguments, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Live Branch task arguments mismatch: expected=$taskArguments actual=$actualArguments"
}
if ([string]$task.Principal.LogonType -ne "Interactive" -or [string]$task.Principal.RunLevel -ne "Limited") {
    throw "Live Branch task principal must remain Interactive and Limited"
}

$record = [ordered]@{
    artifact_type = "dopey_live_branch_schedule_installation"
    schedule_version = "dopey-live-branch-schedule-v1"
    generated_utc = [DateTimeOffset]::UtcNow.ToString("o")
    task_name = $taskName
    repository_root = $repoRoot
    command_path = $commandPath
    command_sha256 = (Get-FileHash -LiteralPath $commandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    launcher_path = $launcherPath
    launcher_sha256 = (Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256).Hash.ToLowerInvariant()
    enabled = [bool]$task.Settings.Enabled
    principal_logon_type = [string]$task.Principal.LogonType
    principal_run_level = [string]$task.Principal.RunLevel
    interval = "PT15M"
    session = "XNYS_regular_market_hours"
    paper_twin_required = $true
    no_day_trading_enforced = $true
    options_execution_enabled = $false
    credentials_stored = $false
}
$auditPath = Join-Path $repoRoot "artifacts\dopey\live_branch\schedule_installation.json"
$auditDirectory = Split-Path -Parent $auditPath
New-Item -ItemType Directory -Path $auditDirectory -Force | Out-Null
$temporaryAuditPath = "$auditPath.tmp"
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporaryAuditPath -Encoding utf8
Move-Item -LiteralPath $temporaryAuditPath -Destination $auditPath -Force
$record | ConvertTo-Json -Depth 6
