# Codex ByteGuard 源码实验版

目标：在发送请求前根据实际序列化 JSON 请求体字节数自动压缩并续跑，不依赖聊天日志估算或 token 换算。

上游：https://github.com/openai/codex

基线提交：89461ea6833832b0551ce24ee32205824d5c108d。

## 设计

- 自定义进程设置 `CODEX_MAX_REQUEST_BYTES` 后启用；未设置时保持上游行为。
- 默认启动上限 950000 字节：普通请求超过 855000 字节时，在网络发送前拦住，自动压缩一次，再重新读取历史继续同一个任务。
- HTTP 和 WebSocket 在完成输入、工具和元数据转换后检查 UTF-8 JSON 大小；不包含 HTTP 头、压缩或 TLS 开销。
- 压缩请求允许到上限 950000 字节，给它留 10% 余量。压缩请求仍太大时明确停止，不删除旧消息来凑大小。
- 每个模型步骤最多因字节上限触发一次压缩；压缩后仍超限则停止并报出实际大小，避免无限循环。
- 不自动压缩内部 Guardian 审核会话，不用 token-budget 的无摘要重置替代压缩，不绕过显式禁用自动压缩的限制。
- 不自动重试公司网关的所有 403，不改变代理或网络路由，不上传已有聊天。

它不能保证通宵任务永不停止：单个超大输入、超大工具结果、工具定义过大或压缩请求超限仍可能停止。此阶段不实现分段摘要，也不静默截断上下文。

## 构建与启动

需要 Rust（版本由源码 rust-toolchain.toml 指定）、Visual Studio C++ Build Tools 和 Windows SDK。

在本私有仓库源码中，从 `byteguard/Codex-ByteGuard` 运行：

```powershell
./Build.ps1
./Build.ps1 -Test
./Start.ps1
./Start.ps1 -MaxRequestBytes 1000000
```

脚本自动加载 Visual Studio C++ 开发环境。默认缓存为 `D:/CodexByteGuard-build`，可用 `-TargetDir` 修改。
网络访问沿用本机已有设置；脚本不修改代理或证书校验，也不绕过 PowerShell 执行策略。组织策略阻止脚本时，应按组织允许的流程运行。
Windows 二进制需在 Windows 自行构建；本次 Release 仅提供 Apple Silicon macOS 二进制。

启动器沿用当前用户的 `CODEX_HOME`（默认 `~/.codex`）、模型、认证和配置，不复制认证到项目。
未从启动器运行时，需要自行设置 `CODEX_MAX_REQUEST_BYTES` 才启用保护。
现有桌面客户端使用自己的内置版本；本发布不替换桌面客户端。
当前验证结果见根目录 `RELEASE-BYTEGUARD.md`，`VALIDATION.md` 仅为附件历史记录。

## HTML 监控接入

新版 Start.cmd / Start.ps1 自动设置本地状态目录为当前 CODEX_HOME 下的 `byteguard/status`。每次请求发送前记录实测字节数、阈值、线程 ID、进程 ID、检查和拦截计数，不保存请求正文、工具定义或认证。状态写入失败只警告，不影响字节保护。

打开容量监控 http://127.0.0.1:8769/ ，可看到 ByteGuard 面板及来源筛选。首次模型请求后才有实测；旧版本和直接运行 exe 而未配置状态目录的进程不会产生新记录。更新后二进制必须重新启动才生效。`CODEX_BYTE_GUARD_STATUS_DIR` 可覆盖默认状态目录，监控服务需要使用相同的环境变量。

“压缩检查次数”是发送前检查次数，包含被拦住的压缩请求，不等于压缩成功次数。最近一次检查通过也不表示网络请求成功，进程存活不表示模型正在生成；界面提供时间戳供判断。

## 自动压缩提示（v1.2）

当 ByteGuard 因请求字节数触发自动压缩时，CLI 对话区域会直接显示中文提示：开始自动压缩、压缩完成并继续任务；失败时显示失败原因。这些提示不再只收进警告查看器。开始提示附带实际请求字节数与阈值，完成后仍会重新检查请求大小。该提示针对 ByteGuard 的字节保护触发流程，原生 token 阈值压缩仍使用原生提示。已经运行的旧 CLI 需要退出后从 Start.cmd / Start.ps1 重新启动（可 resume 原会话）才会生效。

## macOS（ByteGuard 1.2.1）

需要 Xcode Command Line Tools 和 `codex-rs/rust-toolchain.toml` 指定的 Rust。
在源码根目录运行 `bash Build-Mac.sh`，然后 `bash Start-Mac.sh`；恢复会话运行 `bash Start-Mac.sh resume`。
构建缓存默认在 `~/Library/Caches/CodexByteGuard-build`，尊重 `CARGO_TARGET_DIR`。
启动器尊重 `CODEX_HOME`、`CODEX_MAX_REQUEST_BYTES` 和 `CODEX_BYTE_GUARD_STATUS_DIR`。
本地监控运行 `python3 byteguard/Codex-Chat-Guardian/server.py`。
安装预编译包时，将包内 codex 放在 `byteguard/Codex-ByteGuard/bin/codex`，再运行启动器。
