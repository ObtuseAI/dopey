[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$DesktopRoot = $PSScriptRoot
$RepositoryRoot = Split-Path -Parent $DesktopRoot
$LaunchScript = Join-Path $DesktopRoot "launch_desktop.ps1"
$Executable = Join-Path $DesktopRoot "release\DOPEY Control Center.exe"
$DesktopDirectory = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::DesktopDirectory)
$StartupDirectory = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
$DesktopShortcutPath = Join-Path $DesktopDirectory "DOPEY Control Center.lnk"
$StartupShortcutPath = Join-Path $StartupDirectory "DOPEY Control Center.lnk"
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source

if (-not (Test-Path -LiteralPath $LaunchScript -PathType Leaf)) {
    throw "DOPEY desktop launch script is missing: path=$LaunchScript"
}
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "DOPEY desktop executable is missing: path=$Executable"
}
if (-not (Test-Path -LiteralPath $DesktopDirectory -PathType Container)) {
    throw "Windows Desktop directory is missing: path=$DesktopDirectory"
}
if (-not (Test-Path -LiteralPath $StartupDirectory -PathType Container)) {
    throw "Windows Startup directory is missing: path=$StartupDirectory"
}

$Shell = New-Object -ComObject WScript.Shell
$ShortcutDefinitions = @(
    [pscustomobject]@{
        path = $DesktopShortcutPath
        description = "DOPEY research and owner-authorized Live Branch control center"
    },
    [pscustomobject]@{
        path = $StartupShortcutPath
        description = "Launch DOPEY research and Live Branch control center at Windows sign-in"
    }
)

foreach ($ShortcutDefinition in $ShortcutDefinitions) {
    $Shortcut = $Shell.CreateShortcut($ShortcutDefinition.path)
    $Shortcut.TargetPath = $PowerShell
    $Shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LaunchScript`""
    $Shortcut.WorkingDirectory = $RepositoryRoot
    $Shortcut.IconLocation = "$Executable,0"
    $Shortcut.Description = $ShortcutDefinition.description
    $Shortcut.Save()
}

foreach ($ShortcutDefinition in $ShortcutDefinitions) {
    if (-not (Test-Path -LiteralPath $ShortcutDefinition.path -PathType Leaf)) {
        throw "DOPEY shortcut creation failed: path=$($ShortcutDefinition.path)"
    }
}

[pscustomobject]@{
    status = "pass"
    shortcut = $DesktopShortcutPath
    desktop_shortcut = $DesktopShortcutPath
    startup_shortcut = $StartupShortcutPath
    launch_on_user_sign_in = $true
    target = $PowerShell
    arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$LaunchScript`""
    working_directory = $RepositoryRoot
    executable = $Executable
    paper_only = $false
    live_blocked = $false
    live_execution_enabled = $true
} | ConvertTo-Json -Depth 3
