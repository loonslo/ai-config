# Claude Code 配置

跨工具规则源文件位于 `../common/instructions.md`。运行 `scripts/link-global.ps1 -Mode Apply` 后，Claude Code 的全局 `CLAUDE.md` 会挂载到该文件。

`settings.example.json` 只作为结构占位。设备差异和凭据不要直接写入共享 `settings.json`。
