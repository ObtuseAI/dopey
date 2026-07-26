[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$DesktopRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $DesktopRoot
$Executable = Join-Path $DesktopRoot "release\DOPEY Control Center.exe"

if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "The desktop executable is missing. Run desktop\build_desktop.ps1 first."
}

$env:DOPEY_REPO_ROOT = $RepoRoot
Start-Process -FilePath $Executable -WorkingDirectory $RepoRoot
