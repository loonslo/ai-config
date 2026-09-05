# ai-config

用于 Codex、Claude Code 和其他 AI Coding 工具的个人全局配置仓库。

## 目录分层

```text
ai-config/
├── common/       # 跨工具的个人工程规范
├── codex/        # Codex 配置模板和 MCP 清单
├── claude/       # Claude Code 模板
├── prompts/      # 可复用提示词
└── scripts/      # 全局挂载、备份和安全检查
```

配置优先级保持为：全局规则 → 工具规则 → 项目 `AGENTS.md` / `CLAUDE.md` → 当前任务指令。

## 全局配置同步

本仓库不替代整个 `%USERPROFILE%\.codex` 或 `%USERPROFILE%\.claude` 目录。两个目录还包含登录状态、会话、缓存、插件和本机运行时文件，不能跟随 Git 跨设备同步。

脚本默认只挂载共享规则：

```powershell
.\scripts\link-global.ps1 -Mode Preview
.\scripts\link-global.ps1 -Mode Apply
```

它会备份已有的全局规则文件，然后将：

- `common/instructions.md` 挂载为 `%USERPROFILE%\.codex\AGENTS.md`
- `common/instructions.md` 挂载为 `%USERPROFILE%\.claude\CLAUDE.md`

`codex/config.toml` 不会默认覆盖当前 Codex 配置。当前配置可能包含提供商、MCP、通知、插件和本机路径；确认模板适合本机后，再显式执行：

```powershell
.\scripts\link-global.ps1 -Mode Apply -IncludeCodexConfig
```

如果 Windows 不允许创建符号链接，脚本会回退为带备份的文件复制；之后在同步仓库后重新执行即可。

## 设备差异和 MCP

每台设备只设置自己的 `AI_WORKSPACE`，例如：

```powershell
[Environment]::SetEnvironmentVariable('AI_WORKSPACE', 'D:\workspace', 'User')
```

MCP 清单只提交命令、参数和环境变量名。绝对路径、API Key 和 Access Token 放在本机环境变量或 Windows Credential Manager 中。Codex 当前直接使用 TOML 配置 MCP，`codex/mcp.json` 作为跨工具维护清单，不会被 Codex 自动读取。

## 日常维护

```powershell
.\scripts\check-secrets.ps1
git pull
.\scripts\link-global.ps1 -Mode Apply
```

修改通用规范时，编辑 `common/`；修改 Codex 行为时编辑 `codex/config.toml`；项目独有规则仍放在项目自己的 `AGENTS.md` 中。
