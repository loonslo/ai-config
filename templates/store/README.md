# ai-config 配置库

这是 ai-config 的配置库，也就是各 AI agent 共同取用的「唯一真源」。本机和离线迁移可直接使用这个文件夹；克隆或发布远端 Git 配置源时才需要 Git。

| 路径 | 作用 |
| --- | --- |
| `common/*.md` | 规则主题，渲染后写入各 agent 的规则入口 |
| `common/imported.md` | `migrate` 采纳的原有规则（出现后才存在），保留原文与来源 |
| `codex/config.toml`、`claude/settings.shared.json` | Codex / Claude 的共享设置字段模板 |
| `agents.toml` | 可选：各 agent 接收哪些规则主题 |

不要在这里保存凭据、登录状态或本机路径。修改后运行 `sync --publish --apply` 发布，其他设备运行 `sync --fetch --apply` 获取。
