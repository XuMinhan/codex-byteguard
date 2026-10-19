# Codex ByteGuard

本仓库是 OpenAI Codex 的私有维护版本。ByteGuard 在模型请求发送前按 JSON 字节数检查，必要时调用原生上下文压缩并继续任务。

- [维护与升级说明](byteguard/README.md)
- [CLI 使用说明](byteguard/Codex-ByteGuard/README.md)
- [本地监控使用说明](byteguard/Codex-Chat-Guardian/README.md)
- [验证记录](RELEASE-BYTEGUARD.md)
- [版本与官方基线](byteguard/version.json)

上游原始 README 和许可证保留在原位置。本仓库不包含登录凭据、个人配置、聊天记录或编译后的程序。

macOS 源码构建：`bash Build-Mac.sh`。启动：`bash Start-Mac.sh`；恢复会话：`bash Start-Mac.sh resume`。
本次运行包面向 Apple Silicon；Windows 构建入口保留在 `byteguard/Codex-ByteGuard/Build.ps1`。
