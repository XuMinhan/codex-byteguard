param(
    [string]$Source = (Join-Path $PSScriptRoot '../../codex-rs'),
    [string]$TargetDir = 'D:/CodexByteGuard-build',
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
$taskNames = @('PATH','HTTPS_PROXY','HTTP_PROXY','CARGO_TARGET_DIR','CARGO_NET_GIT_FETCH_WITH_CLI','CARGO_BUILD_JOBS')
$taskSaved = @{}
foreach ($taskName in $taskNames) { $taskSaved[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process') }
try {
    if (-not (Get-Command link.exe -ErrorAction SilentlyContinue)) {
        $taskVsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
        if (-not (Test-Path -LiteralPath $taskVsWhere)) { throw 'Install Visual Studio C++ Build Tools and Windows SDK first.' }
        $taskVsRoot = & $taskVsWhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $taskVsRoot) { throw 'No complete Visual Studio C++ Build Tools installation found.' }
        & (Join-Path $taskVsRoot 'Common7/Tools/Launch-VsDevShell.ps1') -Arch amd64 -HostArch amd64 -SkipAutomaticLocation
    }
    $env:PATH = (Join-Path $env:USERPROFILE '.cargo/bin') + ';' + $env:PATH
    $env:CARGO_TARGET_DIR = $TargetDir
    $env:CARGO_NET_GIT_FETCH_WITH_CLI = 'true'
    $env:CARGO_BUILD_JOBS = '4'
    Push-Location -LiteralPath $Source
    try {
        if ($Test) {
            & cargo test -p codex-core --lib request_byte_budget --profile dev-small
        } else {
            & cargo build --locked -p codex-cli --bin codex --profile dev-small
        }
        if ($LASTEXITCODE -ne 0) { throw "Cargo failed ($LASTEXITCODE)" }
        if (-not $Test) {
            $taskBinDir = Join-Path $PSScriptRoot 'bin'
            New-Item -ItemType Directory -Force -Path $taskBinDir | Out-Null
            Copy-Item -LiteralPath (Join-Path $TargetDir 'dev-small/codex.exe') -Destination (Join-Path $taskBinDir 'codex.exe')
        }
    } finally { Pop-Location }
} finally {
    foreach ($taskName in $taskNames) { [Environment]::SetEnvironmentVariable($taskName, $taskSaved[$taskName], 'Process') }
}
