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
if (-not (Test-Path -LiteralPath $wscriptPath -PathType Leaf)) {
    throw "Trusted Windows Script Host is missing: $wscriptPath"
}
$launcherPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "run_scheduled_hidden.vbs")).Path

$taskCommands = [ordered]@{
    "DOPEY_AccelerationCycle" = "acceleration_cycle"
    "DOPEY_DailyRitual" = "daily_ritual"
    "DOPEY_Intraday" = "intraday"
    "DOPEY_LiveBranch" = "live_branch"
    "DOPEY_MondayPreflight" = "monday_preflight"
    "DOPEY_Nightly" = "nightly"
    "DOPEY_ResearchSupervisor" = "research_supervisor"
    "DOPEY_WeekendSoak" = "weekend_soak"
}

$results = @()
foreach ($entry in $taskCommands.GetEnumerator()) {
    $taskName = [string]$entry.Key
    $commandKey = [string]$entry.Value
    $commandPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "$commandKey.cmd"))
    if (-not (Test-Path -LiteralPath $commandPath -PathType Leaf)) {
        throw "Scheduled command is missing: task=$taskName path=$commandPath"
    }
    $task = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction SilentlyContinue
    if ($null -eq $task) {
        $results += [pscustomobject]@{
            task_name = $taskName
            status = "not_present"
            action_updated = $false
        }
        continue
    }
    $actions = @($task.Actions)
    if ($actions.Count -ne 1) {
        throw "Scheduled task action count is not one: task=$taskName count=$($actions.Count)"
    }
    $currentExecute = [System.IO.Path]::GetFullPath([string]$actions[0].Execute)
    $currentArguments = ([string]$actions[0].Arguments).Trim()
    $expectedArguments = '//B //NoLogo "' + $launcherPath + '" ' + $commandKey
    $isLegacyAction = $currentExecute.Equals($commandPath, [System.StringComparison]::OrdinalIgnoreCase) -and [string]::IsNullOrWhiteSpace($currentArguments)
    $isHiddenAction = $currentExecute.Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase) -and $currentArguments.Equals($expectedArguments, [System.StringComparison]::OrdinalIgnoreCase)
    if (-not $isLegacyAction -and -not $isHiddenAction) {
        throw "Scheduled task action is outside the legacy or hidden allowlist and was preserved: task=$taskName execute=$currentExecute arguments=$currentArguments"
    }
    if (-not $isHiddenAction) {
        $action = New-ScheduledTaskAction -Execute $wscriptPath -Argument $expectedArguments
        Set-ScheduledTask -TaskPath "\" -TaskName $taskName -Action $action -ErrorAction Stop | Out-Null
    }
    $verified = Get-ScheduledTask -TaskPath "\" -TaskName $taskName -ErrorAction Stop
    $verifiedActions = @($verified.Actions)
    if ($verifiedActions.Count -ne 1) {
        throw "Hidden action verification count failed: task=$taskName count=$($verifiedActions.Count)"
    }
    $verifiedExecute = [System.IO.Path]::GetFullPath([string]$verifiedActions[0].Execute)
    $verifiedArguments = ([string]$verifiedActions[0].Arguments).Trim()
    if (-not $verifiedExecute.Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase) -or -not $verifiedArguments.Equals($expectedArguments, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Hidden action verification failed: task=$taskName execute=$verifiedExecute arguments=$verifiedArguments"
    }
    $results += [pscustomobject]@{
        task_name = $taskName
        status = [string]$verified.State
        enabled = [bool]$verified.Settings.Enabled
        action_updated = -not $isHiddenAction
        execute = $verifiedExecute
        arguments = $verifiedArguments
        no_window = $true
    }
}

[pscustomobject]@{
    artifact_type = "dopey_hidden_scheduled_launcher_installation"
    launcher = $launcherPath
    launcher_sha256 = (Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256).Hash.ToLowerInvariant()
    task_count = $results.Count
    tasks = $results
    consoles_hidden = $true
} | ConvertTo-Json -Depth 5
