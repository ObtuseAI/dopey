[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$DesktopRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $DesktopRoot
$BuildVenv = Join-Path $DesktopRoot ".desktop-venv"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$PythonLock = Join-Path $DesktopRoot "requirements-build.lock"
$PackageLock = Join-Path $DesktopRoot "package-lock.json"
$FrontendEntry = Join-Path $DesktopRoot "dist\index.html"
$AssetGenerator = Join-Path $DesktopRoot "tools\generate_brand_assets.py"
$ManifestGenerator = Join-Path $DesktopRoot "tools\generate_release_manifest.py"
$VisualQaGenerator = Join-Path $DesktopRoot "tools\generate_visual_qa.mjs"
$SpecFile = Join-Path $DesktopRoot "DOPEYControlCenter.spec"
$ReleaseRoot = Join-Path $DesktopRoot "release"
$ReleaseStagingRoot = Join-Path $DesktopRoot "build\release-staging"
$WorkRoot = Join-Path $DesktopRoot "build\pyinstaller"
$Executable = Join-Path $ReleaseRoot "DOPEY Control Center.exe"
$StagedExecutable = Join-Path $ReleaseStagingRoot "DOPEY Control Center.exe"
$PromotionExecutable = Join-Path $ReleaseRoot "DOPEY Control Center.exe.promoting"
$BackupExecutable = Join-Path $ReleaseRoot "DOPEY Control Center.exe.previous"
$ReleaseManifest = Join-Path $ReleaseRoot "DOPEY_Control_Center_RELEASE_MANIFEST.json"
$ReleaseHash = Join-Path $ReleaseRoot "DOPEY Control Center.exe.sha256"
$SourceSmokePath = Join-Path $DesktopRoot "build\source-smoke.json"
$ExpectedPythonVersion = "3.13.13"
$ExpectedNodeVersion = "v24.15.0"
$ExpectedNpmVersion = "11.14.1"

$ResolvedDesktopRoot = [System.IO.Path]::GetFullPath($DesktopRoot).TrimEnd('\')
$ResolvedBuildVenv = [System.IO.Path]::GetFullPath($BuildVenv)
$ResolvedReleaseStagingRoot = [System.IO.Path]::GetFullPath($ReleaseStagingRoot)
if (
    -not $ResolvedBuildVenv.StartsWith(
        "$ResolvedDesktopRoot\",
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or
    (Split-Path -Leaf $ResolvedBuildVenv) -ne ".desktop-venv"
) {
    throw "Refusing to recreate an unexpected desktop build environment path: $ResolvedBuildVenv"
}
$ExpectedReleaseStagingRoot = "$ResolvedDesktopRoot\build\release-staging"
if (-not [System.String]::Equals($ResolvedReleaseStagingRoot, $ExpectedReleaseStagingRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to recreate an unexpected release staging path: $ResolvedReleaseStagingRoot"
}
$ResolvedExecutable = [System.IO.Path]::GetFullPath($Executable)
$RunningReleaseProcesses = @(
    Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
        $_.ExecutablePath -and [System.String]::Equals(
            [System.IO.Path]::GetFullPath([string]$_.ExecutablePath),
            $ResolvedExecutable,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    }
)
if ($RunningReleaseProcesses.Count -gt 0) {
    $ProcessIds = @($RunningReleaseProcesses | ForEach-Object { [string]$_.ProcessId }) -join ","
    throw "desktop_release_in_use: close DOPEY Control Center before rebuilding; executable=$ResolvedExecutable; process_ids=$ProcessIds"
}
if (Test-Path -LiteralPath $ResolvedBuildVenv) {
    Remove-Item -LiteralPath $ResolvedBuildVenv -Recurse -Force
}
if (Test-Path -LiteralPath $ResolvedReleaseStagingRoot) {
    Remove-Item -LiteralPath $ResolvedReleaseStagingRoot -Recurse -Force
}

$PythonLauncher = Get-Command py.exe -ErrorAction Stop
& $PythonLauncher.Source -3.13 -m venv $BuildVenv
if ($LASTEXITCODE -ne 0) {
    throw "Dedicated desktop build environment creation failed with exit code $LASTEXITCODE"
}
$ActualPythonVersion = (& $BuildPython -c "import platform; print(platform.python_version())").Trim()
if ($ActualPythonVersion -ne $ExpectedPythonVersion) {
    throw "Desktop build requires Python $ExpectedPythonVersion, found $ActualPythonVersion"
}

$Npm = Get-Command npm.cmd -ErrorAction Stop
$Node = Get-Command node.exe -ErrorAction Stop
if (-not (Test-Path -LiteralPath $PythonLock -PathType Leaf)) {
    throw "desktop/requirements-build.lock is required for a hash-verified Python build"
}
if (-not (Test-Path -LiteralPath $PackageLock -PathType Leaf)) {
    throw "desktop/package-lock.json is required for a deterministic npm ci build"
}
$NodeVersion = (& $Node.Source --version).Trim()
$NpmVersion = (& $Npm.Source --version).Trim()
if ($NodeVersion -ne $ExpectedNodeVersion) {
    throw "Desktop build requires Node $ExpectedNodeVersion, found $NodeVersion"
}
if ($NpmVersion -ne $ExpectedNpmVersion) {
    throw "Desktop build requires npm $ExpectedNpmVersion, found $NpmVersion"
}

& $BuildPython -m pip install --disable-pip-version-check --no-input --require-hashes --requirement $PythonLock
if ($LASTEXITCODE -ne 0) {
    throw "Hash-verified Python desktop dependency installation failed with exit code $LASTEXITCODE"
}

Push-Location $DesktopRoot
try {
    & $Npm.Source ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
        throw "npm ci failed with exit code $LASTEXITCODE"
    }
    & $Npm.Source run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $FrontendEntry -PathType Leaf)) {
    throw "Frontend build did not produce desktop/dist/index.html"
}

$env:PYTHONPATH = $RepoRoot
Push-Location $RepoRoot
try {
    & $BuildPython -m desktop.tools.generate_visual_fixture --repo-root $RepoRoot --output (Join-Path $DesktopRoot "visual-qa\control-state.json")
}
finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    throw "Desktop visual fixture generation failed with exit code $LASTEXITCODE"
}
& $Node.Source $VisualQaGenerator
if ($LASTEXITCODE -ne 0) {
    throw "Desktop visual QA page generation failed with exit code $LASTEXITCODE"
}

& $BuildPython $AssetGenerator
if ($LASTEXITCODE -ne 0) {
    throw "Brand asset generation failed with exit code $LASTEXITCODE"
}

$env:DOPEY_REPO_ROOT = $RepoRoot
$env:PYTHONHASHSEED = "0"
$env:SOURCE_DATE_EPOCH = "1784342400"
Push-Location $RepoRoot
try {
    $SourceSmokeOutput = & $BuildPython -m dopey_dashboard.desktop_app --smoke-check
}
finally {
    Pop-Location
}
if ($LASTEXITCODE -ne 0) {
    throw "Source desktop smoke check failed with exit code $LASTEXITCODE"
}
$SourceSmokeJson = $SourceSmokeOutput -join [System.Environment]::NewLine
$SourceSmoke = $SourceSmokeJson | ConvertFrom-Json
$ExpectedApiMethods = "close_window,get_chart,get_chart_coach,get_state,get_symbol_lab,minimize_window,set_instrument_mode,set_llm_provider,set_openrouter_api_key,set_options_execution,set_research_core,toggle_maximize_window"
if (
    $SourceSmoke.status -ne "pass" -or
    $SourceSmoke.server_started -ne $false -or
    $SourceSmoke.live_execution_enabled -ne $true -or
    $SourceSmoke.paper_only -ne $false -or
    $SourceSmoke.live_blocked -ne $false -or
    ((@($SourceSmoke.desktop_api_methods) -join ",") -ne $ExpectedApiMethods)
) {
    throw "Source desktop smoke contract is invalid: $SourceSmokeJson"
}
$SourceSmokeDirectory = Split-Path -Parent $SourceSmokePath
New-Item -ItemType Directory -Path $SourceSmokeDirectory -Force | Out-Null
Set-Content -LiteralPath $SourceSmokePath -Value $SourceSmokeJson -Encoding utf8

& $BuildPython -m PyInstaller --noconfirm --clean --distpath $ReleaseStagingRoot --workpath $WorkRoot $SpecFile
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $StagedExecutable -PathType Leaf)) {
    throw "PyInstaller did not produce the expected staged executable: $StagedExecutable"
}

$SmokeProcess = Start-Process -FilePath $StagedExecutable -ArgumentList @("--smoke-check") -WorkingDirectory $RepoRoot -WindowStyle Hidden -Wait -PassThru
if ($SmokeProcess.ExitCode -ne 0) {
    throw "Packaged desktop smoke check failed with exit code $($SmokeProcess.ExitCode)"
}

New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
Copy-Item -LiteralPath $StagedExecutable -Destination $PromotionExecutable -Force
if (Test-Path -LiteralPath $Executable -PathType Leaf) {
    if (Test-Path -LiteralPath $BackupExecutable) {
        Remove-Item -LiteralPath $BackupExecutable -Force
    }
    [System.IO.File]::Replace($PromotionExecutable, $Executable, $BackupExecutable, $true)
    if (-not (Test-Path -LiteralPath $BackupExecutable -PathType Leaf)) {
        throw "Desktop release atomic replacement did not produce its verified backup: $BackupExecutable"
    }
    Remove-Item -LiteralPath $BackupExecutable -Force
}
else {
    Move-Item -LiteralPath $PromotionExecutable -Destination $Executable
}
if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "Desktop release promotion did not produce the expected executable: $Executable"
}

$Artifact = Get-Item -LiteralPath $Executable
$Hash = Get-FileHash -LiteralPath $Executable -Algorithm SHA256
$Signature = Get-AuthenticodeSignature -LiteralPath $Executable
& $BuildPython $ManifestGenerator --repo-root $RepoRoot --executable $Executable --output $ReleaseManifest --sha256-sidecar $ReleaseHash --node-version $NodeVersion --npm-version $NpmVersion --authenticode-status $Signature.Status.ToString() --source-smoke $SourceSmokePath --packaged-smoke-passed
if ($LASTEXITCODE -ne 0) {
    throw "Release manifest generation failed with exit code $LASTEXITCODE"
}
[pscustomobject]@{
    status = "pass"
    executable = $Artifact.FullName
    bytes = $Artifact.Length
    sha256 = $Hash.Hash.ToLowerInvariant()
    release_manifest = $ReleaseManifest
    sha256_sidecar = $ReleaseHash
    authenticode_status = $Signature.Status.ToString()
    server_started = $false
    paper_only = $false
    live_blocked = $false
    live_execution_enabled = $true
} | ConvertTo-Json -Depth 3
