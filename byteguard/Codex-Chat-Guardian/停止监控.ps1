$ErrorActionPreference = 'Stop'
$taskPidFile = Join-Path $PSScriptRoot 'server.pid'
if (-not (Test-Path -LiteralPath $taskPidFile)) { Write-Host '本目录没有服务进程记录。'; exit }
$taskServiceId = [int](Get-Content -LiteralPath $taskPidFile)
$taskProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$taskServiceId"
$taskExpected = Join-Path $PSScriptRoot 'server.py'
if ($taskProcess -and $taskProcess.CommandLine.Contains($taskExpected)) {
    Stop-Process -Id $taskServiceId
    Remove-Item -LiteralPath $taskPidFile
    Write-Host '监控服务已停止。'
} else { Write-Host '记录的进程不存在或不属于本目录，未结束任何进程。' }
