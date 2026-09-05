# ai-config 仓库规则

- `common/` 是跨工具规范的源文件；修改通用规则时先改那里。
- `codex/` 和 `claude/` 只保存可同步的模板，不保存登录状态、缓存、插件或机器专属路径。
- 运行 `scripts/check-secrets.ps1` 后再提交。
- 运行挂载脚本前使用 `-Mode Preview`；脚本必须备份已有全局文件。
- 不要把任何 API Key、Access Token、Cookie、私钥或真实凭据写进仓库。
- 项目自身的开发规则放在对应项目根目录的 `AGENTS.md` 或 `CLAUDE.md`，不要为了方便把项目细节写进全局规则。
