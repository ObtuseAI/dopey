$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$expectedRoot = "C:\Users\CH\dopey"
if ($repoRoot -ne $expectedRoot) {
    throw "Repository root mismatch: expected=$expectedRoot actual=$repoRoot"
}

$commandPath = Join-Path $repoRoot "operator_tools\acceleration_cycle.cmd"
if (-not (Test-Path -LiteralPath $commandPath -PathType Leaf)) {
    throw "Acceleration command is missing: $commandPath"
}

$taskName = "DOPEY_AccelerationCycle"
$wscriptPath = Join-Path $env:SystemRoot "System32\wscript.exe"
$hiddenLauncherPath = Join-Path $repoRoot "operator_tools\run_scheduled_hidden.vbs"
if (-not (Test-Path -LiteralPath $wscriptPath -PathType Leaf)) {
    throw "Trusted Windows Script Host is missing: $wscriptPath"
}
if (-not (Test-Path -LiteralPath $hiddenLauncherPath -PathType Leaf)) {
    throw "Hidden scheduled launcher is missing: $hiddenLauncherPath"
}
$taskArguments = '//B //NoLogo "' + $hiddenLauncherPath + '" acceleration_cycle'
$taskAction = New-ScheduledTaskAction -Execute $wscriptPath -Argument $taskArguments
$taskTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At "00:05" `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$taskLogonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$taskLogonTrigger.Delay = "PT45S"
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$taskSettings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger @($taskTrigger, $taskLogonTrigger) -Principal $taskPrincipal -Settings $taskSettings -Force | Out-Null

$legacyIntradayTaskName = "DOPEY_Intraday"
$legacyIntradayCommandPath = (Resolve-Path -LiteralPath (Join-Path $repoRoot "operator_tools\intraday.cmd")).Path
$legacyIntradayTask = Get-ScheduledTask -TaskName $legacyIntradayTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacyIntradayTask) {
    $legacyActions = @($legacyIntradayTask.Actions)
    if ($legacyActions.Count -ne 1) {
        throw "Legacy intraday task has unexpected action count and was preserved: task=$legacyIntradayTaskName count=$($legacyActions.Count)"
    }
    $legacyExecutePath = [System.IO.Path]::GetFullPath([string]$legacyActions[0].Execute)
    $legacyArguments = ([string]$legacyActions[0].Arguments).Trim()
    $legacyHiddenArguments = '//B //NoLogo "' + $hiddenLauncherPath + '" intraday'
    $legacyDirectAction = $legacyExecutePath.Equals($legacyIntradayCommandPath, [System.StringComparison]::OrdinalIgnoreCase) -and [string]::IsNullOrWhiteSpace($legacyArguments)
    $legacyHiddenAction = $legacyExecutePath.Equals($wscriptPath, [System.StringComparison]::OrdinalIgnoreCase) -and $legacyArguments.Equals($legacyHiddenArguments, [System.StringComparison]::OrdinalIgnoreCase)
    if (-not $legacyDirectAction -and -not $legacyHiddenAction) {
        throw "Legacy intraday task action mismatch and was preserved: task=$legacyIntradayTaskName expected_direct=$legacyIntradayCommandPath expected_hidden=$legacyHiddenArguments actual_execute=$legacyExecutePath actual_arguments=$legacyArguments"
    }
    Disable-ScheduledTask -TaskName $legacyIntradayTaskName | Out-Null
}

& schtasks.exe /Query /TN $taskName /FO LIST
if ($LASTEXITCODE -ne 0) {
    throw "Task Scheduler verification failed: task=$taskName exit_code=$LASTEXITCODE"
}
