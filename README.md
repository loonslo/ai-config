# codex-config

一个可版本管理、可在多台 Windows 设备之间同步的 AI Coding 配置仓库。

## 这个仓库管理什么

- `config.toml`：共享的 Codex 配置模板。它不包含密钥，也不会自动替换本机配置。
- `AGENTS.md`：Codex 能直接读取的仓库级工作约定。
- `instructions.md`：面向 Codex、Claude Code、Cursor、Continue 等工具的通用说明源文件。
- `mcp.json`：跨工具的 MCP 服务清单，仅记录结构和非敏感参数。
- `prompts/`：可复用的任务提示词。
- `scripts/`：同步、备份和安全检查脚本。

## 推荐的边界

Codex 的个人配置仍放在 `%USERPROFILE%\.codex\config.toml`，项目级配置放在项目内的 `.codex\config.toml`。这个仓库是配置源，不是完整的 `.codex` 运行目录。

不要把整个 `%USERPROFILE%\.codex` 目录软链接到本仓库。该目录还包含登录状态、会话、缓存、插件和本机运行时文件，跨设备同步会带来泄密和兼容性风险。需要应用共享设置时，只同步 `config.toml` 和 `AGENTS.md`，并保留自动备份。

## 第一次使用

1. 将本目录初始化为 Git 私有仓库，并推送到你的 GitHub Private Repo。
2. 在其他设备将仓库克隆到同样的工作区路径，例如 `D:\workspace\codex-config`。
3. 先执行预览：

   ```powershell
   .\scripts\install-codex-config.ps1 -Mode Preview
   ```

4. 确认无误后再执行应用。脚本会先备份现有文件：

   ```powershell
   .\scripts\install-codex-config.ps1 -Mode Apply
   ```

5. 将各工具的密钥放在 Windows Credential Manager 或环境变量中，不要写进 `config.toml`、`mcp.json`、`.env` 或提示词文件。

## MCP 说明

`mcp.json` 是便于跨工具维护的清单。Codex 当前使用 TOML 配置 MCP 服务；添加服务前，应把清单中的非敏感内容转换为本机配置，并通过环境变量注入密钥。不要直接把某一台设备的绝对路径复制到所有设备。

## 日常维护

- 修改通用规则时，先改 `instructions.md`，再执行 `sync-instructions.ps1` 更新 `AGENTS.md`。
- 新增 MCP 服务时，只提交命令、参数和环境变量名，不提交值。
- 提交前运行 `check-secrets.ps1`。
- 设备差异放在未跟踪的 `*.local.*` 文件或本机环境变量中。
