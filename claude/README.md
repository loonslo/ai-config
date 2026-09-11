# Claude Code 配置

跨工具规则源文件位于 `../common/`。运行跨平台 `scripts/sync.py rules --local device.json --apply` 后，全部主题写入全局 CLAUDE.md 的受管区块，原有区块外内容保留。先不加 --apply 预览。

`settings.shared.json` 是共享字段来源；本机 device.json 中 claude_keys 选择实际应用字段。自动记忆通过 memories 项目映射同步到独立 ai-memory，具体流程见根 README。凭据不写入任何共享设置。
