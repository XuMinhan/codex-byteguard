$ErrorActionPreference = 'Stop'
# Keep Codex switches (especially -c) out of PowerShell parameter binding.
$taskArguments = @($args)
$MaxRequestBytes = 950000
if ($taskArguments.Count -gt 0 -and $taskArguments[0] -eq '-MaxRequestBytes') {
    if ($taskArguments.Count -lt 2) { throw '-MaxRequestBytes requires a byte count.' }
    $MaxRequestBytes = [int]$taskArguments[1]
    if ($MaxRequestBytes -lt 1024) { throw 'MaxRequestBytes must be at least 1024.' }
    $taskArguments = @($taskArguments | Select-Object -Skip 2)
}
$taskBinary = Join-Path $PSScriptRoot 'bin/codex.exe'
if (-not (Test-Path -LiteralPath $taskBinary)) { throw 'Build the custom executable first; see README.md.' }
$taskPrevious = [Environment]::GetEnvironmentVariable('CODEX_MAX_REQUEST_BYTES', 'Process')
$taskPreviousStatus = [Environment]::GetEnvironmentVariable('CODEX_BYTE_GUARD_STATUS_DIR', 'Process')
try {
    $env:CODEX_MAX_REQUEST_BYTES = [string]$MaxRequestBytes
    $taskCodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' }
    if (-not $env:CODEX_BYTE_GUARD_STATUS_DIR) { $env:CODEX_BYTE_GUARD_STATUS_DIR = Join-Path $taskCodexHome 'byteguard/status' }
    Write-Host "ByteGuard: generation limit $($MaxRequestBytes - [math]::Floor($MaxRequestBytes / 10)) bytes; compaction ceiling $MaxRequestBytes bytes."
    & $taskBinary @taskArguments
    $taskExit = $LASTEXITCODE
} finally {
    [Environment]::SetEnvironmentVariable('CODEX_MAX_REQUEST_BYTES', $taskPrevious, 'Process')
    [Environment]::SetEnvironmentVariable('CODEX_BYTE_GUARD_STATUS_DIR', $taskPreviousStatus, 'Process')
}
exit $taskExit
