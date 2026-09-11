# Codex 配置

`config.toml` 是可同步的共享模板；本机提供商、认证、通知、插件和 MCP 进程路径应先确认后再加入本机配置，不要把密钥写入仓库。

使用 scripts/sync.py config --local device.json 预览，加入 --apply 应用。本机 codex_keys 选择共享字段，未选择字段和 TOML 注释保留。全局规则由 rules 命令生成受管区块。自动记忆目前仅导出到独立 ai-memory 的设备快照，全局规则引导按需读取，不回填原生记忆存储。

`mcp.json` 是跨工具的 MCP 清单，不是 Codex 当前自动读取的配置文件。Codex 的 MCP 配置应写入用户级 `config.toml`，路径和密钥使用本机环境变量。
