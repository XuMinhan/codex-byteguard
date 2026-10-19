$ErrorActionPreference = 'Stop'
$taskUrl = 'http://127.0.0.1:8769'
try {
    $taskStatus = Invoke-RestMethod "$taskUrl/api/chats" -TimeoutSec 3
    if ($taskStatus.metric -eq 'UTF-8 compact JSON of response_item payloads; not HTTP request size') {
        Start-Process $taskUrl
        exit
    }
    throw '端口 8769 已被其他服务使用。'
} catch {
    if ($_.Exception.Message -like '*端口 8769*') { throw }
}
$taskCandidates = @()
$taskBundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (Test-Path -LiteralPath $taskBundled) { $taskCandidates += ,@($taskBundled) }
foreach ($taskName in @('py','python','python3')) {
    $taskCommand = Get-Command $taskName -ErrorAction SilentlyContinue
    if ($taskCommand) {
        if ($taskName -eq 'py') { $taskCandidates += ,@($taskCommand.Source, '-3') }
        else { $taskCandidates += ,@($taskCommand.Source) }
    }
}
$taskPython = $null
foreach ($taskCandidate in $taskCandidates) {
    $taskExecutable = $taskCandidate[0]
    $taskPrefix = @($taskCandidate | Select-Object -Skip 1)
    try {
        & $taskExecutable @taskPrefix -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $taskPython = $taskCandidate; break }
    } catch {}
}
if (-not $taskPython) { throw '未找到 Python 3.10+。请安装 Python 并勾选 Add Python to PATH 后重试。' }
$taskExecutable = $taskPython[0]
$taskArguments = @($taskPython | Select-Object -Skip 1)
$taskArguments += '"' + (Join-Path $PSScriptRoot 'server.py') + '"'
$taskProcess = Start-Process -FilePath $taskExecutable -ArgumentList $taskArguments -WindowStyle Hidden -PassThru
$taskProcess.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'server.pid')
$taskReady = $false
for ($taskAttempt = 0; $taskAttempt -lt 15; $taskAttempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $taskStatus = Invoke-RestMethod "$taskUrl/api/chats" -TimeoutSec 3
        if ($taskStatus.metric -eq 'UTF-8 compact JSON of response_item payloads; not HTTP request size') { $taskReady = $true; break }
    } catch {}
    if ($taskProcess.HasExited) { break }
}
if (-not $taskReady) { throw '服务启动失败。请运行 python server.py 查看错误，检查端口 8769 是否被占用。' }
Start-Process $taskUrl
