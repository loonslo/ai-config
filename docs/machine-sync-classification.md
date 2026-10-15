# AI 配置同步分类（定性）规范

维护日期：2026-10-09　·　状态：**规范已确认，分阶段实施中。** D17–D22 与方案 T-2/T-3/T-6 已确认；分类与现有来源的覆盖观察已实现，完整采集及恢复能力未验收。实际进度见 [执行记录](machine-sync-execution.md)。

本文是「换机备份里哪些该带、哪些不该带」的唯一依据。配套文档：[变更方案](machine-sync-plan.md) · [接口契约](machine-sync-interfaces.md)。

2026-10-09 用户追加要求：**完全不读取 Git 信息，助手文件按白名单携带**。本要求取代原先按 Git 跟踪状态筛选、查询 Git 根目录及技能远端/HEAD/脏状态的规则；不查询 Git 版本、配置或凭据。Git 元数据目录/文件不进入备份，也不枚举其内部内容或计算大小。公开来源可来自账号清单、技能锁文件或技能自带元数据，不查询 Git。

- 适用范围：桌面客户端的 ZIP 原样备份与恢复（见 [桌面原样备份与恢复](desktop-offline-migration.md)）。
- 约定：`~` 为用户主目录；`<WS>` 为工作区根目录；`<项目>` 为所选工作文件夹；表中 ID 是稳定编号，规则表代码与本文第 4 节必须一一对应（接口契约 §13 有一致性测试）。
- 隐私：本文不含凭据、邮箱、账号标识和本机绝对路径。本文数字来自 2026-10-09 在负责人机器上的只读核对（目录名、大小、键名、哈希、计数），没有读取任何凭据的值。

## 1. 已确认决定（2026-10-09，负责人）

| 编号 | 决定 | 落点 |
|---|---|---|
| D17 | 邮箱等个人信息不再阻止备份；仍拦截凭据 | §5.1 |
| D18 | 第三方 skill 原样带上，并记录来源 | SK-02、SK-05、§5.2 |
| D19 | 同名多份 skill 全部保留 | SK-04、§5.3 |
| D20 | 会话历史默认不带，可勾选带上 | H 类、§5.4 |
| D21 | 其它工具（CodeBuddy、Pi、Copilot、Ollama 等）暂不纳入 | OT-01 |
| D22 | Claude 桌面端账号里自建的 skill 仍备份 | CD-01 |

## 2. 七种性质

| 性质 | 名称 | 一句话 | 默认动作 |
|---|---|---|---|
| A | 自建内容 | 你写的，或 AI 为你积累的：规则、记忆、自建 skill、自写脚本、命令授权规则、人设 | 带上（字节级原样） |
| B | 偏好配置 | 设置文件里你做的「选择」：模型、语言、权限模式、项目信任、远程 MCP 地址 | 只取白名单字段；安全相关项恢复前确认 |
| C | 第三方 | 从别处装来、能重新获得的内容 | 第三方 skill 带上并记来源；插件、MCP、软件只记录；随应用或账号下发的只记录 |
| D | 凭据与身份 | 登录态、令牌、密钥、账号与设备标识 | 永不带；只在登录清单里记名字 |
| E | 运行产物 | 缓存、日志、数据库、统计、可重新生成的文件 | 不带 |
| H | 历史记录 | 会话与提示历史 | 默认不带；勾选后带上 |
| F | 工作成果（范围外） | 源码、AI 生成的图片或文档、任务目录 | 不属于本工具，不扫描 |

动作用词：**带上**＝原样放入备份；**取字段**＝只带白名单字段；**记录**＝不带内容，只在报告里记名称、来源、版本；**不带**＝不进入备份；**可选**＝默认不带，勾选后带上。

恢复用词：**自动**＝目标不存在就写入，已有不同内容时按文件由你选覆盖或保留；**确认**＝先展示内容，你明确同意才写；**手动**＝仅在你明确选择后写；**导出**＝不写进应用目录，导出到恢复报告文件夹由你导入；**—**＝不恢复。

## 3. 判定顺序

遇到任何新文件，按顺序回答，命中即止：

1. 含登录态、令牌、密钥、账号或设备标识，或**无法确认是否含**？→ **D**（未核实一律按 D）。
2. 应用自己生成、可重新生成，或是缓存、日志、数据库、统计？→ **E**。
3. 是会话或提示历史？→ **H**。
4. 是设置文件里的「选择」？→ **B**，并逐个字段定性。
5. 是你写的，或 AI 为你积累的？→ **A**。
6. 是从别处安装的？→ **C**（用户自行安装的是第三方；随应用或账号下发的只记录）。
7. 以上都不是？→ **未定性**：不带，但必须在覆盖报告里列出（§5.8），定性后再补进本表。

## 4. 清单

### 4.1 Claude Code（`~/.claude/`、`~/.claude.json`；环境变量 `CLAUDE_CONFIG_DIR` 可改根）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| CC-01 | `CLAUDE.md`、`rules/**/*.md` | A | 带上 | 自动 | 全局规则，字节级原样（沿用 D5） |
| CC-02 | `commands/**`、`agents/**`、`output-styles/**`、`keybindings.json` | A | 带上 | 自动 | 本机暂无，先登记，避免将来新增被漏 |
| CC-03 | `projects/<目录>/memory/**/*.md` | A | 带上 | 自动 | 自动记忆；目录由所选工作文件夹路径推导；默认含全部已登记且存在的项目（§5.6） |
| CC-04 | `plans/*.md` | A | 带上 | 自动 | 计划模式产出的文档，本机 4 个共约 60 KB |
| CC-05 | `skills/**`（常为指向 CC Switch 的链接） | A、C | 带上 | 自动 | 按 SK 规则分流；链接按 §5.5 处理；恢复到 `~/.claude/skills/` |
| CC-06 | `settings.json`：`language`、`effortLevel` | B | 取字段 | 自动 | |
| CC-07 | `settings.json`：`model`、`skipDangerousModePermissionPrompt` | B | 取字段 | 确认 | 与供应商或安全相关 |
| CC-08 | `settings.json` → `env` 中的非密钥项 | B | 取字段 | 确认 | 网关地址、模型映射、功能开关；会改变请求去向，必须确认。可能由 CC Switch 切换供应商时改写（§7） |
| CC-09 | `settings.json` → `env` 中的密钥项（名称含 TOKEN、KEY、SECRET、PASSWORD、AUTH） | D | 不带 | — | 只在登录清单里记变量名 |
| CC-10 | `settings.json`：`enabledPlugins`、`extraKnownMarketplaces` | C | 记录 | — | 进重装清单 |
| CC-11 | `settings.json`：`permissions`、`hooks`、`statusLine`、`mcpServers`、`outputStyle` 等其余选择 | B | 取字段 | 确认 | 本机暂无；会执行命令的项一律确认 |
| CC-12 | `settings.json`：`apiKeyHelper`、`awsAuthRefresh`、`awsCredentialExport` 等取凭据的命令 | D | 不带 | — | 本机暂无 |
| CC-13 | `~/.claude.json` → `projects[].hasTrustDialogAccepted`、`hasClaudeMdExternalIncludesApproved` | B | 取字段 | 手动 | 信任是安全决定；沿用现有门禁 |
| CC-14 | `~/.claude.json` → `mcpServers`、`projects[].mcpServers`、`enabledMcpjsonServers`、`disabledMcpjsonServers`、`allowedTools` | B | 取字段 | 确认 | 本机均为空；env 里的密钥值不带 |
| CC-15 | `~/.claude.json` 其余键：账号、用户与设备标识为 D；缓存、使用统计、提示历史、`skillUsage`、`pluginUsage` 为 E | D、E | 不带 | — | |
| CC-16 | `plugins/**` | C | 记录 | — | 已安装插件与 marketplace 来源进重装清单；缓存与市场副本不带 |
| CC-17 | `.credentials.json`、`config.json`（含 API Key 字段） | D | 不带 | — | |
| CC-18 | `projects/*/*.jsonl`（会话转录）、`history.jsonl`（提示历史） | H | 可选 | 自动 | 只新增不覆盖；§5.4 |
| CC-19 | `cache/`、`backups/`、`daemon*`、`downloads/`、`file-history/`、`ide/`、`jobs/`、`paste-cache/`、`session-env/`、`sessions/`、`shell-snapshots/`、`teams/`、`stats-cache.json`、`policy-limits.json`、`remote-settings.json`、`mcp-needs-auth-cache.json`、`skills_backup_*`、`.last-*` | E | 不带 | — | |

### 4.2 Claude 桌面端（`%APPDATA%\Claude\`）

账号 skill 位于 `local-agent-mode-sessions\skills-plugin\<账号>\<组织>\`（两层标识目录），其中 `manifest.json` 登记每个 skill 的 `creatorType`。

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| CD-01 | 上述 `skills/<名称>/`，且 `creatorType` 为 `user` 的 skill | A | 带上 | 导出 | 本机 5 个，合计不到 70 KB；D22。关联 `manifest.json` 仅作为来源元数据记录（C），不携带；自建技能仍按 SK-05 排除可再生产物。账号是否登录后自动同步到新电脑**未验证**（§7） |
| CD-02 | 同目录 `creatorType` 为 `anthropic` 的 skill；`rpm/plugin_*`（Cowork 插件） | C | 记录 | — | 随应用或账号下发（vendor_builtin） |
| CD-03 | `claude_desktop_config.json`：`mcpServers`、非设备类 `preferences` | B | 取字段 | 确认 | 本机无 MCP；设备路径类键不带 |
| CD-04 | `claude-code-sessions/*.json` | E | 不带 | — | 仅只读用于发现已登记的项目文件夹 |
| CD-05 | `config.json`（含加密令牌缓存）、`Local Storage`、`IndexedDB`、`Network`（含 Cookie）、`Partitions`、`Session Storage`、`SharedStorage`、`WebStorage`、`ant-did`、`ant-device-registry.json`、`buddy-tokens.json`、`ccd-ids.json`、`lockfile` | D | 不带 | — | 登录态与设备标识 |
| CD-06 | `Cache`、`Code Cache`、`GPUCache`、`Dawn*`、`DIPS*`、`Crashpad`、`sentry`、`logs`、`claude-code/<版本>/`、`git-worktrees.json`、`mcp-user-tool-toggles.json`、`window-state.json`、`plan-usage-history.json`、`scratch-workspaces/` 等 | E | 不带 | — | |

### 4.3 Codex（`~/.codex/`；环境变量 `CODEX_HOME` 可改根）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| CX-01 | `AGENTS.md`、`AGENTS.override.md` | A | 带上 | 自动 | |
| CX-02 | `rules/**`（命令授权规则，如 `default.rules`） | A | 带上 | 自动 | 本机 25 KB，现有备份未包含 |
| CX-03 | `prompts/**`、`memories/**` | A | 带上 | 自动 | 本机暂无或为空，先登记 |
| CX-04 | `skills/**`（`.system/` 除外） | A、C | 带上 | 自动 | 按 SK 规则分流 |
| CX-05 | `config.toml`：`model_reasoning_effort`、`personality`、`features.*`、`memories.*`、`history.persistence`、`windows.sandbox` | B | 取字段 | 自动 | 沿用现有白名单 |
| CX-06 | `config.toml`：`model`、`service_tier`、`approval_policy`、`sandbox_mode` | B | 取字段 | 确认 | |
| CX-07 | `config.toml` → `shell_environment_policy.set` 中的非密钥、非设备项 | B | 取字段 | 确认 | 设备相关变量（如受信浏览器客户端哈希）不带 |
| CX-08 | `config.toml` → `[projects.*].trust_level` | B | 取字段 | 确认 | 仅存在的文件夹；沿用现有信任门禁 |
| CX-09 | `config.toml` → `mcp_servers.*` 中只含 `url` 的远程服务 | B | 取字段 | 确认 | 恢复后仍需重新授权 |
| CX-10 | `config.toml` → `mcp_servers.*` 中含 `command`、`args`、`env` 的本地服务 | C | 记录 | — | 内置运行时随插件提供；记录名称与环境变量名 |
| CX-11 | `config.toml`：`plugins`、`marketplaces`、`hooks.state`、`notify` | C | 记录 | — | 由插件或内置程序生成，重装插件即再生 |
| CX-12 | `config.toml` → `desktop.*` | B | 取字段 | 自动 | 默认全不带；仅 4 个界面项可在配置中勾选；设备类不带 |
| CX-13 | `auth.json`、`cap_sid`、`installation_id`、`secrets/`、`.sandbox-secrets/`、`mcp-oauth-locks/`、`chrome-native-hosts*.json`；配置环境变量中的密钥名称 | D | 不带 | — | `shell_environment_policy.set` 下名称含 TOKEN、KEY、SECRET、PASSWORD、AUTH 的键只记录名称 |
| CX-14 | `sessions/**`、`archived_sessions/**`、`session_index.jsonl`、`history.jsonl` | H | 可选 | 自动 | 仅文件；不保证续接；§5.4 |
| CX-15 | `*.sqlite*`（`state_5`、`thread_history_1`、`logs_2`、`queue_1`、`goals_1`、`memories_1`）、`.codex-global-state.json*` | E | 不带 | — | 应用内部库，不直接读写 |
| CX-16 | `cache/`、`plugins/`、`vendor_imports/`、`.tmp/`、`tmp/`、`log/`、`sandbox*.log`、`.sandbox*/`、`models_cache.json`、`cc-switch-model-catalog.json`、`ambient-suggestions/`、`browser/`、`computer-use/`、`pets/`、`sites/`、`worktrees/`、`version.json`、`config.toml.bak-*` 等 | E | 不带 | — | |
| CX-17 | `generated_images/`、`attachments/`、`visualizations/`、`dictation-history/` | F | 不带 | — | 工作成果或个人记录，不是配置 |

### 4.4 通用技能目录（`~/.agents/`）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| AG-01 | `skills/**` | A、C | 带上 | 自动 | 按 SK 规则分流：在 `.skill-lock.json` 登记的是第三方，未登记的是自建。界面里归入「通用技能」 |
| AG-02 | `.skill-lock.json` | C | 带上 | 自动 | 约 5 KB，记录来源与哈希；仅目标缺失时写入，不合并 |

### 4.5 CC Switch（`~/.cc-switch/`）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| CW-01 | `skills/**`（`~/.claude/skills` 的链接目标） | A、C | 带上 | 自动 | 逻辑位置记为 Claude 的 `skills/…`，恢复到 `~/.claude/skills/`，不写 `~/.cc-switch/` |
| CW-02 | `cc-switch.db`、`settings.json`、`backups/`、`skill-backups/`、`logs/`、`crash.log`、`model-pricing.json` | D | 不带 | — | 数据库含供应商密钥；其余内容未核实，按凭据对待 |

### 4.6 WorkBuddy 与 WorkBuddy AI（`~/.workbuddy/`、`~/.workbuddy-ai/`）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| WB-01 | `BOOTSTRAP.md`、`IDENTITY.md`、`SOUL.md`、`USER.md`、`MEMORY.md`、`memory/**/*.md` | A | 带上 | 手动 | 人设与记忆；加载机制未验证，恢复只做手动候选（沿用 G7） |
| WB-02 | `skills/**` | A、C | 带上 | 手动 | 按 SK 规则分流；应用迁移标记（任意层级的 `*_migration.json`）不带 |
| WB-03 | `scripts/**` | A | 带上 | 手动 | 自写脚本；取代旧「未知 scripts 不带」 |
| WB-04 | `settings.json` → `enabledPlugins` 名称 | C | 记录 | — | 其余键不带（`claw`、`sandbox`、`pluginConfigs` 等） |
| WB-05 | `keyblob`、`security/`、`app/`、`user-state.json`、`device-id`、`local_storage/`、`connectors*`、`mcp-approvals.json`、`models.json`、`workspace-state.json`、`workspace-display-names.json`、`*.db*`、`user-<标识>-personal/`、`.workbuddy-key-fallback/` | D | 不带 | — | 沿用旧 A.4 |
| WB-06 | `sessions/`、`traces/`、`blobs/`、`changes-*`、`artifact-index/`、`audit-log/`、`file-history/`、`shell-snapshots/`、`clipboard-images/`、`logs/`、`tasks/`、`plans/`、`cache/`、`plugins/`、`pending-telemetry/` 等 | E | 不带 | — | |
| WB-07 | `<项目>/.workbuddy/{memory,skills}/**`、`<项目>/.workbuddy-ai/{memory,skills}/**` | A | 带上 | 手动 | 项目级，只处理所选项目 |
| WB-08 | `~/WorkBuddy*/` 下按日期命名的任务目录 | F | 不带 | — | 工作成果 |

### 4.7 项目内（`<项目>/`）

只处理所选项目；默认范围见 §5.6。助手文件按白名单携带，不读取 Git 跟踪或忽略状态。

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| PJ-01 | `AGENTS.md`、`AGENTS.override.md`、`CLAUDE.md`、`CLAUDE.local.md` | A | 带上 | 自动 | 所选项目内均携带，不检查 Git |
| PJ-02 | `.claude/settings.local.json` | A | 带上 | 自动 | 项目权限规则；沿用现有行为（深度不超过 2 层） |
| PJ-03 | `.claude/{skills,commands,agents,output-styles}/**`、`.claude/launch.json`、`.claude/*.md` | A | 带上 | 自动 | skills 按 SK 规则分流；现有备份只取了 PJ-02 |
| PJ-04 | `.agents/skills/**`、`.codex/{config.toml,rules/**,prompts/**,skills/**}` | A | 带上 | 自动 | 本机暂无内容；Codex 项目配置只在项目被信任后才生效 |
| PJ-05 | `.mcp.json` | B | 取字段 | 确认 | env 里的密钥值不带 |
| PJ-06 | `.claude/worktrees/**`、`.claude/shots/**`、`**/scratch-workspaces/**` | E | 不带 | — | 运行产物与截图输出 |
| PJ-07 | 项目源码、依赖、构建产物 | F | 不带 | — | 靠各项目 Git |

### 4.8 系统层

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| SY-01 | 用户级环境变量中非密钥且与 AI 相关的：`ANTHROPIC_*`、`CLAUDE_*`、`CODEX_*`、`OPENAI_*` 的非密钥项、代理变量、`API_TIMEOUT_MS`、`AI_*`，以及配置 `env_include` 指定的名称 | B | 取字段 | 导出 | 只生成脚本与清单，不直接写注册表 |
| SY-02 | 用户级环境变量中名称含 KEY、SECRET、PASSWORD、TOKEN 的，或值含账号信息的代理地址 | D | 不带 | — | 只在登录清单里记名称 |
| SY-03 | 其余用户级环境变量（`Path`、`TEMP`、IDE 与运行时目录等） | E | 不带 | — | 不属于 AI 配置 |
| SY-04 | `~/.ssh`、`~/.npmrc`、Windows 凭据管理器、Git 凭据 | D | 不带 | — | Git 配置/凭据不查询、不列主机；其它沿用登录清单 |
| SY-05 | 软件版本与全局包清单（Node、npm、Python、Codex CLI、Claude 桌面端等） | C | 记录 | — | 已有 `software.json`；不查询 Git 或 Git LFS 版本 |

### 4.9 技能通用规则（跨位置）

「按 SK 规则分流」的判定顺序见接口契约 §5。

| ID | 对象 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| SK-01 | 自建 skill（无来源证据；或账号清单标 `user`；或不在 `.skill-lock.json`） | A | 带上（含非文本文件） | 自动 | 来源不明的也先按此处理，并在报告里标「来源不明」 |
| SK-02 | 第三方 skill（用户自行安装，且有来源证据） | C | 带上并记录来源 | 自动 | D18：原样带上；去掉 SK-05 的可再生产物 |
| SK-03 | 随应用或账号下发的 skill | C | 记录 | — | Codex 的 `.system/`、Claude 桌面端 `creatorType` 为 `anthropic` 的、Cowork 插件 |
| SK-04 | 同名多份 skill | — | 全部保留 | 各回原处 | D19：不去重、不合并；报告标明相同或不同 |
| SK-05 | 可再生产物 | E | 不带 | — | 所有来源：`.git` 目录/指针、`.gitconfig`、`.gitignore`、`.gitattributes`、`.gitmodules` 不读、不带、不计算大小（Git 凭据见 SY-04）；所有 skill：`node_modules/`、`__pycache__/`、`.venv/`、`*.pyc`；任意层级 `*_migration.json` 为应用迁移标记。仅第三方 skill：`*.exe`、`*.dll`、`*.so`、`*.dylib`、`*.node`、`*.pyd`。路径与大小记入来源记录；自建 skill 里的可执行文件按 A 带上，单文件超过 64 MiB 的仍排除并告知 |

### 4.10 暂不纳入（D21）

| ID | 内容 | 性质 | 动作 | 恢复 | 备注 |
|---|---|---|---|---|---|
| OT-01 | `~/.codebuddy/`、`%APPDATA%\CodeBuddy CN\`、`~/.pi/`、`~/.copilot/`、`~/.ollama/`、`~/Doubao/`、`~/.opencli/`、`~/.sheetagent/`、`~/.dsh/` | — | 不扫描、不记录 | — | 本期范围外；将来纳入先在本表补行 |

## 5. 专门规则

### 5.1 邮箱与密钥（D17）

- 邮箱、姓名等个人信息**不拦**。备份由你自己保管，ZIP 不加密（沿用 D4）。
- 拦截对象只有**凭据**：已知令牌格式（`sk-…`、`ghp_…` 等 GitHub 令牌、`github_pat_…`、`AKIA…`、私钥块、`Authorization: Bearer …`、JWT）、`密码或密钥: 值` 与 `.env` 式 `*_PASSWORD=值` 的赋值、含用户名密码的 URL。
- 命中后**不再整份丢弃**：默认「脱敏后保留」——只把值替换为占位符，文件其余内容原样保存；备份前列出文件与行号（不含值），你可以改选「整份跳过」。脱敏过的文件恢复后会提示「需要重新填写」。
- 第三方 skill（来源证据为 `exact` 或 `derived` 的）只对高置信度令牌格式脱敏；赋值样式的命中只提示、不改动（公开内容里常见示例值）。
- 日志、错误提示和界面不回显任何命中值，邮箱同样不回显。
- 2026-10-09 实测：现有备份整份丢弃的 5 个文件里，4 个只因含邮箱，1 个命中密钥规则。

### 5.2 第三方 skill 原样带上（D18）

- 目的：新电脑离线就能用、版本固定、不依赖上游仍然存在。
- 带上的是 skill 目录里**除 SK-05 以外的全部文件**（脚本、模板、测试夹具、非文本资源），字节级一致。
- SK-05 是**物理限制下的唯一折中**：备份格式单文件上限 64 MiB、整包 512 MiB，而本机 gstack 与 browse 内有 7 个约 98–115 MB 的可执行文件（合计约 690 MiB），装不下；它们是构建产物，不是 skill 内容。去掉后，CC Switch 里的 35 个第三方 skill 约 90–100 MiB（未压缩，按目录大小估算）。此处与 D18 的字面意思有出入，**负责人已于 2026-10-09 接受**（方案 §9）。
- 每个 skill 都有来源记录（`reports/skills.json`）：来源不明标 `unknown`，此时备份内的原样副本就是唯一来源。
- 恢复写入 `~/.claude/skills/<名称>/` 等；被 SK-05 排除的程序文件按来源记录里的重装提示重建，并列入「接下来要做的事」。

### 5.3 同名多份（D19）

- 同名 skill 可能同时存在于多个位置，内容相同或不同；**一律全部保留、各回原处**，互不覆盖。
- 报告列出每一组及其关系。2026-10-09 实测：`ai-transition-diary` 在 Claude 桌面端、Codex、一个项目目录三处，内容已不同；另有一个 skill 三处完全相同。
- 哪一份当正本由你以后决定；本工具不替你合并。

### 5.4 历史记录（D20）

- 默认不带，界面上有一个「历史记录（体积较大）」勾选项。
- 范围：Claude 的会话转录与提示历史；Codex 的会话文件与索引（仅文件，数据库不带，见 CX-15）。
- 因体积可达数 GB，超出主备份的包大小上限，勾选后另生成独立的历史备份包（接口契约 §11）。
- 恢复：只新增、不覆盖、不合并；已存在的另存为备份版本；映射不到项目的放入单独文件夹。**不保证 `--resume` 一类续接可用**（未验证）。

### 5.5 符号链接

- 默认规则不变：采集和恢复都不跟随符号链接或联接点。
- 唯一例外：**批准链接**。`~/.claude/skills` 若是链接，且目标在白名单（`~/.cc-switch/skills`、`~/.agents/skills`）内、目标自身不是链接、目录内不含链接，则从目标目录读取；逻辑位置仍记为 Claude 的 `skills/…`。
- 恢复永不创建链接，也不穿过链接写入；新电脑上若该目录已被链接接管，相关条目标记「路径含链接」并给出提示。

### 5.6 项目范围与白名单携带

- 默认范围＝Claude 与 Codex 已登记、且在这台电脑上存在的全部文件夹，排除 `.claude/worktrees/**` 与 scratch 目录；界面可逐个取消。**取代旧 D12（11 个核心项目）**。
- 项目内的助手文件（PJ-01 至 PJ-05）按白名单携带，包括已跟踪、被忽略和未跟踪的文件；不调用 Git、不判断其可用性、不生成 git_unavailable 标记。项目源码仍不携带。
- 任意来源下的 `.git` 目录或 worktree 指针文件、`.gitconfig`、`.git-credentials`、`.gitignore`、`.gitattributes`、`.gitmodules` 不读、不带。新包项目记录不写 Git 根目录/ID，工具元数据不写 Git 提交字段。
- 信任类（Claude、Codex）仍然默认不恢复，需逐次确认；清单会随项目增多而变长（本机 Codex 登记 42 条）。

### 5.7 字段级定性

设置类文件逐键定性，范围见 CC-06 至 CC-15、CX-05 至 CX-12、CD-03。**文件里任何未在本表出现的键视为未定性**：不带，列入覆盖报告的 `fields` 部分，不能无声消失。

### 5.8 未定性文件

- 对已纳入的根目录，每个被访问的文件都必须落在某条规则上；落不上的叫「未定性」。
- 未定性文件**不带**，但在 `reports/coverage.json` 和备份摘要里列出（每个根目录最多列 20 个路径，不含内容）。
- 工具升级后新增的文件会在这里出现；你确认性质后，在本表补一行，规则表随之更新。

## 6. 取代关系

| 旧条款 | 位置 | 处理 |
|---|---|---|
| 红线 4：任何输出里不得出现邮箱 | [MACHINE-MIGRATION-TASKS.md](../MACHINE-MIGRATION-TASKS.md) §5.6 | 邮箱不再拦截备份内容；日志与界面仍不回显 |
| 「只出清单：第三方 skills」 | 同上 §2 | 第三方 skill 改为带上并记来源；插件、MCP 仍只记录 |
| 「会话只做实验」 | 同上 §2 | 改为可勾选的 H 类 |
| Codex skills 排除非文本与 `.system/` | 同上 A.1 | 非文本一并带上（SK-05 除外）；`.system/` 仍不带 |
| 「`~/.claude/skills` 符号链接的内容不搬」 | 同上 A.4 | 批准链接内可搬（§5.5） |
| 「未知 `scripts/` 不带」 | 同上 A.WB | WB-03 自写脚本带上 |
| 核心项目 11 个 | 同上 D12 | 默认全部已登记且存在的文件夹（§5.6） |
| 邮箱、含用户信息 URL 与转义写法检测 | 同上 附录 D（2026-10-02） | 邮箱检测移除；含用户信息 URL 的检测保留 |

## 7. 未核实与假设

1. Claude 桌面端账号 skill 登录后是否自动出现在新电脑：**推测会**（`skillId` 是服务端分配的格式），需第二台电脑实测。
2. Claude 桌面端导入 skill 的 ZIP 结构与入口名称：未核实，导出包按「顶层为 skill 目录」生成。
3. `settings.json` 的 `env` 是否由 CC Switch 切换供应商时改写：推测，未读取 CC Switch 数据库。
4. CC Switch 自带的 skill 记录是否含仓库来源：未读取数据库；如需使用，须另行授权（方案 §6）。
5. Claude 桌面端若以 MSIX 方式安装，数据目录可能被重定向；本机 `%APPDATA%\Claude` 有效，其它机器未知。
6. gstack 等需要构建的 skill，新机重建步骤以其自带说明为准。
7. 「第三方」「随应用下发」的边界是本文的解释：用户自行安装的算第三方；应用或账号自动提供的只记录。
