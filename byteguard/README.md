> 当前维护版本：ByteGuard 1.2.1；本次来源和验证见 [发布记录](../RELEASE-BYTEGUARD.md)。以下 v1.2.0 内容保留为原始维护背景。

# ByteGuard 版本管理

私有仓库：https://github.com/XuMinhan/codex-byteguard

官方仓库：https://github.com/openai/codex

## 分支和远程

| 名称 | 用途 |
| --- | --- |
| remote `origin` | 自己的私有仓库，保存维护分支、基线和发布标签 |
| remote `upstream` | 官方仓库，只拉取；本地 push URL 设置为 DISABLED |
| branch `upstream` | 当前已采用的纯官方基线，不接受内部 PR |
| branch `byteguard` | 可构建的内部维护版本，也是私有仓库默认分支 |
| branch `upgrade/<version>` | 每次升级时创建，验证后通过内部 PR 合入 byteguard |
| tag `byteguard-v1.2.0` | 首个纳入版本管理的 ByteGuard 发布基线 |

提交身份继承用户已有 Git 配置，不改全局设置。旧的 main、byte-budget-guard 本地分支保留。所有 PR 都应位于自己的私有仓库，不向 openai/codex 提交。Draft 不是隐私控制，隐私来自仓库的 private 设置。

GitHub Actions 暂时关闭，避免原样继承的官方工作流在内部仓库执行。后续可增加专用 Windows 构建工作流，再有选择地启用。

## 从新电脑开始

```powershell
git clone https://github.com/XuMinhan/codex-byteguard.git
cd codex-byteguard
git remote add upstream https://github.com/openai/codex.git
git remote set-url --push upstream DISABLED
git switch byteguard
./byteguard/Codex-ByteGuard/Build.ps1
./byteguard/Codex-ByteGuard/Start.ps1
```

Windows 需要 Rust 及 Visual Studio C++ Build Tools 和 SDK。默认构建缓存是 D:/CodexByteGuard-build，没有 D 盘时传 `-TargetDir` 指定路径。启动时读取该电脑现有的 Codex 配置和登录；仓库不分发这些文件。

## 修改和验证

后续优先修改仓库内文件，outputs 和桌面目录作为构建、运行或发布副本，不再作为唯一源码。CLI 工具位于 byteguard/Codex-ByteGuard，监控位于相邻的 Codex-Chat-Guardian。

```powershell
git switch byteguard
git switch -c feature/your-change
./byteguard/Codex-ByteGuard/Build.ps1
./byteguard/Codex-ByteGuard/Build.ps1 -Test
python ./byteguard/Codex-ByteGuard/test_byte_guard.py ./byteguard/Codex-ByteGuard/bin/codex.exe
```

TUI 提示变更还需在与 Build.ps1 相同的 VS 开发环境和构建缓存下，从 codex-rs 目录执行：

```powershell
cargo test -p codex-tui --lib byteguard_compaction_notices_are_visible_in_chat --profile dev-small
```

验证重点：请求超限前被阻止；压缩后同任务继续；压缩无效或压缩自身超限时明确停止；关闭保护时恢复原行为；提示可见。WebSocket 尚无端到端测试，升级涉及该路径时需要补测。

## 跟进官方版本

先选定经过评估的官方 tag 或提交，下面以占位符 `<official-ref>` 表示，不自动跟随 main。

```powershell
git fetch upstream --tags
git switch byteguard
git pull --ff-only origin byteguard
git switch -c upgrade/your-version
git merge --no-ff <official-ref>
```

解决冲突时重点检查 core/src/client.rs、request_byte_budget.rs、session/turn.rs、compact.rs 和 tui 的提示处理。更新 version.json 的 upstream_commit 和 version，执行上述构建和测试，必要时用实际配置做小规模验证。

```powershell
git push -u origin upgrade/your-version
```

在私有仓库创建 Draft PR，base 选 byteguard，head 选升级分支。审核和验证完成后正常 merge，保留官方合并历史；不要 squash/rebase 整个升级 PR，否则下一次升级可能重复处理官方历史。合入后将纯官方基线分支快进到本次采用的官方提交：

```powershell
git fetch origin
git switch upstream
git merge --ff-only <official-ref>
git push origin upstream
git switch byteguard
git pull --ff-only origin byteguard
```

只给 origin 推送，不给官方 upstream 推送。

## 发布和回退

验证完成后，用递增版本创建带注释标签。更新验证记录后再打标签，不移动已经发布的标签。

```powershell
git tag -a byteguard-vX.Y.Z -m "ByteGuard X.Y.Z"
git push origin byteguard
git push origin byteguard-vX.Y.Z
```

ZIP 以标签中的跟踪文件为基础组装，单独加入该提交编译出的 bin/codex.exe；生成清单记录版本、source commit、upstream commit、构建时间和二进制 SHA256。不要递归打包当前工作目录、CODEX_HOME 或运行目录。bin、聊天、状态、备份、PID、日志不进 Git。

初始 byteguard-v1.2.0 对应的桌面 ZIP 在版本管理建立前已验证生成，其程序与源码一致，但包内文档尚无本次维护信息；以后发布应按上述流程从标签生成。

每个版本并排安装，保留旧版。回退时启动上一版本目录下的 Start.cmd，使用 resume 接回会话；不要覆盖正在运行的 exe。Git 代码回退可以在独立检出目录使用发布标签，避免重置维护分支或改写已推送历史。
