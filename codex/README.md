# Codex 配置

`config.toml` 是可同步的共享模板；本机提供商、认证、通知、插件和 MCP 进程路径应先确认后再加入本机配置，不要把密钥写入仓库。

`mcp.json` 是跨工具的 MCP 清单，不是 Codex 当前自动读取的配置文件。Codex 的 MCP 配置应写入用户级 `config.toml`，路径和密钥使用本机环境变量。
