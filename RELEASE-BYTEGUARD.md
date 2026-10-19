# Codex ByteGuard 1.2.1

日期：2026-10-19（Asia/Shanghai）。

## 来源与审阅

- 官方源码： https://github.com/openai/codex
- 本次获取并复核的官方 HEAD：`89461ea6833832b0551ce24ee32205824d5c108d`。
- 官方 HEAD 与附件 v1.2.0 基线完全一致；逐项核对生成请求、压缩请求、工具元数据处理、重试和 TUI 提示流程后导入变更，没有覆盖其他上游改动。
- `changed-files.zip` SHA256：`8909e62ac83ca96ed8d2e6cdd15a064365fa12a0491950f45daa84e9c5558474`。
- 修改记录附件 SHA256：`cb115e6934d9cd91b7a2c2079897a0ae65788246eedf352d6a4acc318747b05a`。

## 功能

`CODEX_MAX_REQUEST_BYTES` 启用发送前 UTF-8 JSON 字节保护。普通请求使用上限的 90%，压缩使用完整上限；启动器默认 950000 / 855000 字节。计量不含请求头、TLS 或传输压缩。

HTTP 和 WebSocket 在输入和元数据转换后检查；前台及后台压缩共用受保护发送路径。超限在当前模型步骤调用原生压缩一次，重新读取历史继续；仍超限或压缩自身超限时明确失败，不为满足字节限制静默丢弃历史。显式禁用自动压缩、token-budget 模式和内部 Guardian 会话保留原有限制。

CLI 对话区显示中文开始、完成、失败提示。本地状态仅包含大小、阈值、线程/进程标识、时间和计数。监控页面可选读取本机聊天作估算，估算与实际请求大小分开展示。

1.2.1 补齐 Mac 构建/启动脚本，修正监控器对原生 Mac 程序的识别，增加监控隔离测试和运行数据忽略规则，整理构建说明。Windows 构建脚本移除原包可选的代理/证书吊销检查覆盖行为，启动器移除执行策略绕过参数。

## 构建与验证

在 Apple Silicon / macOS 14.4 上使用 Rust 1.95.0 构建：

- `cargo build --locked -p codex-cli --bin codex --profile dev-small`：通过。
- `cargo test --locked -p codex-core --lib request_byte_budget --profile dev-small`：4 项通过。
- `cargo test --locked -p codex-tui --lib byteguard_compaction_notices_are_visible_in_chat --profile dev-small`：1 项通过。
- `python3 byteguard/Codex-ByteGuard/test_byte_guard.py <binary>`：4 项通过（成功续跑、压缩无效、压缩自身超限、关闭保护）。
- `python3 byteguard/Codex-Chat-Guardian/test_server.py`：2 项通过，使用合成数据与空目录验证估算、接口及 Host/路径保护。
- 修改包的 Rust 格式检查、Mac shell 语法检查、Python 语法检查、Git 空白检查：通过。
- Mac 启动器 `--version` 检查通过；动态依赖仅包含系统库。
- 最终 32 个新增/修改文件的已知密钥模式扫描无命中；认证、配置、会话、数据库、状态、日志和构建产物忽略检查通过。未运行整个上游工作区测试集。

成功续跑场景的模拟服务实收请求体为 39633 字节（普通）、263792 字节（压缩）、40219 字节（续跑）。测试上限 300000 字节，普通阈值 270000 字节；超限普通请求在本地拦截，没有到达服务端。

ByteGuard 版本由发布标签和 `byteguard/version.json` 标识；CLI 的 `--version` 保留上游开发分支的 `codex-cli 0.0.0`。

## 隐私与发布范围

仅提交官方源码及审阅后的 ByteGuard 文件。保留官方 LICENSE、NOTICE 和历史。提交身份使用本机既有 Git 配置；GitHub 使用既有 XuMinhan 登录，凭据由系统钥匙串与凭据助手管理，不写入远程 URL、源码或发布包。

原有私有仓库的 bootstrap 分支保留；新增版本分支，不强制推送。发布前关闭该仓库 Actions，避免源码上传触发工作流。

未将个人配置、认证、会话、数据库、备份、运行状态或构建日志纳入提交/发布。测试使用合成会话和临时 CODEX_HOME，不读取真实聊天。密钥模式扫描仅能说明已检查内容未命中已知模式，不代表组织对源码上传的额外审批。

## 已知边界

不承诺真实大上下文任务永不停止；超大的单项输入、工具定义、工具输出或压缩请求仍可能失败。本次没有真实账号模型请求、通宵运行或 WebSocket 端到端验证。Windows/Intel Mac/Linux 未在本机编译验证。发布二进制为 Apple Silicon macOS 的 dev-small 构建（无优化、调试信息关闭），没有 Apple 开发者签名或公证。源码支持按上游流程自行构建。
