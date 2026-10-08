# 换机迁移工具包 · 实施任务（MACHINE-MIGRATION-TASKS）

> 当前决策（2026-10-08）：桌面客户端恢复推进，只保留原样备份恢复 ZIP；云端继续冻结，命令向导不作为用户入口。以下旧冻结范围及旧 `.aiconfig`／终端交付任务属于历史记录，与本声明冲突处以 [桌面离线迁移任务](docs/desktop-offline-migration.md) 为准。


维护日期：2026-10-02　·　状态：**等待环境（P3 隔离验证通过；首份备份隐私遗漏已修正；负责人暂时没有净室，真实恢复与 CI 仍待验）**
负责人：仓库所有者　·　执行者：按本文件逐项实施的工程师或 AI Agent

> **取代关系**：本文件取代 `DESKTOP-TASKS.md`、`UX-TASKS.md`、`TODO.md`、`task.md` 中关于桌面客户端、服务器同步和"受管区块同步"的后续任务。这些文件保留为历史记录，由 MK-00 标注"已冻结"。

---

## 0. 先读这里（执行者须知）

1. **这是计划，不是已完成的功能。** 每个任务的"验收"全部满足才算完成。"文件存在、格式通过、Git 有改动"都不算完成（沿用仓库规则）。
2. **开工前**先看 `git status` 和 `git log -3`。工作树可能被多人或多个会话共用：**不得 `git add .` / `git add -A`，不得覆盖他人未提交的修改**，只提交本任务涉及的文件。
3. **提交**：每个任务至少一个本地提交，信息格式 `feat(machine): MK-xx 简述`。**未经负责人授权不得推送**；MK-01 是唯一预先说明的推送，且只推到 `wip/` 分支。
4. **测试**：`python -m pytest <范围> -q --basetemp tmp/run-<新编号>`（每次用新编号）。测试必须在隔离的 HOME 里运行，**不得读取或写入真实的 `~/.claude`、`~/.codex`、`~/.workbuddy*`**。
5. **红线**见 §5.6，违反即停止并报告。
6. **遇到文档与实机不一致、或本文件没覆盖的情形**：不要猜。记入 §11（附录 D），暂停该任务并询问负责人。
7. **阶段结束**：把实际执行的命令、日期、环境、结果和未验证项写入 `docs/acceptance.md`，再按 `AGENTS.md` 的契约更新 `PROJECT_STATUS.md`（未验证的保持"待验收"）。
8. 标有 **[需授权]** 的步骤必须先得到负责人明确同意（聊天或书面）。**授权只对当次有效，不沿用到其他任务。**
9. §4.3 的"本机基线数据"来自负责人机器 2026-10-01/02 的只读盘点，**只用于校准验收，不得硬编码进代码或测试**。
10. 本文件不含凭据和本机绝对路径：`<WS>` 表示负责人的工作区根目录，`~` 表示用户主目录。
11. **给人看的文字**（向导画面、错误信息，以及 `summary.md`、`preflight-report.md`、`todo.md`、`login-checklist.md`、`verify-report.md` 的正文）一律遵守 §5.7（D16）：先写大白话，内部概念只放进"详细信息"。**开工前先读 §5.7。**

---

## 1. 目标与"无差别"的口径

**目标**：更换电脑后，新电脑"开箱即有"：原有的配置、记忆、skills 等可以无差别地继续使用；并且 Claude Code / Codex / WorkBuddy 里的"项目"（对本地文件夹的信任、权限规则、项目记忆、项目列表）可以继续使用。**新电脑上的本地文件夹由负责人自行保证存在**，本工具包不搬运项目代码。

| 层 | 含义 | 要求 |
|---|---|---|
| **A 同样的助手 + 知识 + 项目状态** | 规则、设置字段、记忆、权限规则、信任、自建 skills 一致；新开会话，行为与旧机一致 | **必须做，且可验证** |
| **B 同一条会话** | 旧会话能在新机上续接（`--resume` / `codex resume`） | 只做实验（MK-42），结论出来再定，不承诺 |
| **例外**（必须写明，不可能无差别） | 登录态与 OAuth、路径不同的机器（Mac）、进行中的后台任务、模型输出的随机性、Codex 旧会话 | 列入验收报告 |

**场景**：一次性迁移 + 防丢失备份都要覆盖，先做迁移。`backup` 命令可随时手动运行，不依赖定时任务。

**易用性（D16）**：做法必须足够简单——完全不懂技术的人，只看一页说明（`docs/quickstart.md`），就能独立完成备份和恢复。§5.5 的专家命令保留，但不是默认入口。落实见 §5.7、MK-27、MK-28、MK-37，验收见 MK-44。

---

## 2. 范围

| 对象 | 根目录 | 实例 id | 本期处理 |
|---|---|---|---|
| Claude Code（含 Claude Desktop 的 Code 标签） | `CLAUDE_CONFIG_DIR`，否则 `~/.claude`；状态文件 `~/.claude.json` | `claude` / `main` | 规则、设置字段、记忆、权限规则、信任 |
| Codex（含 Codex Desktop） | `CODEX_HOME`，否则 `~/.codex` | `codex` / `main` | 规则、设置字段、自建 skills、信任 |
| WorkBuddy | `~/.workbuddy` | `workbuddy` | 人设文件、记忆、skills、少量设置字段（草案，由 MK-14 定稿） |
| WorkBuddy AI | `~/.workbuddy-ai` | `workbuddy-ai` | 同上 |

- **搬运（restore 会写入）**：规则、白名单设置字段、记忆、权限规则、Codex 信任、自建 skills、WorkBuddy 的人设/记忆/skills。
- **只出清单（不搬内容）**：第三方 skills、插件、MCP、软件环境、登录与密钥项。
- **不搬**：凭据与登录文件、数据库、日志、缓存、用量统计、远程连接、符号链接的内容。
- **会话**：只做实验（MK-42），结论出来再定是否进入 P5。
- **非目标**：workspace 里代码仓库的备份和推送（负责人自行保证）；服务器/云同步；桌面客户端（D16 的新手向导是终端里的问答加双击启动器，不属于桌面客户端）；规则文件去重（可选任务 MK-70）；CodeBuddy 与 CC Switch 的写入（只在 summary 里列出存在与体积）。
- **冻结（不删除、不再扩展）**：`desktop/`、`server/`、`deploy/`、`sync_core/cloud/`、`sync_core/application/`、`.github/workflows/desktop-build.yml`、`schemas/desktop-rpc.schema.json`，以及与它们配套的文档和测试。**新代码不得依赖这些模块，也不得修改 `sync_core/package/**`。**

---

## 3. 已确认的决策（执行中不得更改；需要变更先找负责人）

| # | 决策 |
|---|---|
| D1 | 场景：一次性迁移 + 防丢失备份都覆盖，先做迁移 |
| D2 | 层级：A 必做；B（会话续接）先实验 |
| D3 | **bundle 使用新格式**，独立于已冻结的 `sync_core/package`（原因见 §5.3） |
| D4 | **备份介质：本地压缩包（zip），不加密。** bundle 不含凭据，但含个人记忆、权限规则和 WorkBuddy 人设文件，由负责人自行保管 |
| D5 | **规则文件按源机当前内容原样备份**（字节级），含重复内容；不去重、不改源机文件。重复只在报告里提示 |
| D6 | 源机只读：备份过程不得写入任何 agent 目录或项目文件夹 |
| D7 | 还原冲突默认不覆盖（见 §5.4） |
| D8 | 信任：只对**存在的**文件夹恢复，写入前给负责人确认清单 |
| D9 | 已不存在的路径（死条目）不带 |
| D10 | 路径：Windows 机之间统一使用同一个工作区根目录；Mac 用根目录映射 |
| D11 | 会话先不承诺 |
| D12 | **核心项目 11 个**（相对 `<WS>`）：`.`（工作区根本身）、`FinUnityWorkspace`、`ImageViewer`、`Knowledge`、`PersonalCharacter`、`ai-config`、`dashboards`、`langchain-learning`、`notebook_obsidian`、`personal-site`、`worldquant` |
| D13 | 本期对象：Claude、Codex、**WorkBuddy、WorkBuddy AI（两个实例）** |
| D14 | 附录 A（分档与字段白名单）已批准；WorkBuddy 部分是草案，由 MK-14 定稿后再批准 |
| D15 | 冻结 §2 所列范围 |
| D16 | **新手可用（负责人原则，2026-10-02 增补）**：「足够的简单，让完全不懂的人也能快速上手完成内容的备份和恢复」。面向用户只有「备份」「恢复」两个动作；不写任何配置文件也能完整运行；默认界面不出现内部概念；只提供安全默认；验收以未接触过本工具的人独立完成为准。细则见 §5.7，落实见 MK-27、MK-28、MK-37，验收见 MK-44；`scripts/machine.py` 现有子命令与参数保留为「高级」入口。**不通过修补已冻结的桌面客户端来实现（D15）。** |

---

## 4. 关键事实（依据）

### 4.1 项目状态存放在哪里

| Agent | 状态 | 位置 | 说明 |
|---|---|---|---|
| Claude | 项目信任 | `~/.claude.json` → `projects[路径].hasTrustDialogAccepted` | 该文件同时含 OAuth 登录、机器 ID、个人 MCP、特性开关缓存；Claude 运行时会改写它 |
| Claude | 权限规则 | `<项目>/.claude/settings.local.json` | 本地专属，不进 git；`git clone` 不会带来 |
| Claude | 项目记忆 | `~/.claude/projects/<目录名>/memory/` | 目录名由 **git 仓库根** 推导 |
| Claude | 会话转录 | `~/.claude/projects/<目录名>/<会话id>.jsonl` | 目录名由**工作目录**推导；内部格式随版本变化 |
| Claude Desktop | 项目/会话列表 | `%APPDATA%\Claude\claude-code-sessions\*.json` | 每个文件指向 `cwd` 与 `cliSessionId`（仅实验用） |
| Codex | 信任 | `config.toml` → `[projects.'路径'] trust_level` | Windows 上路径被写成小写 |
| Codex | 项目列表 | `state_5.sqlite` 的 `projects` / `project_roots` + `.codex-global-state.json` | **应用内部库，不直接写** |
| Codex | 会话 | `state_5.sqlite` 的 `threads`（`project_id`/`cwd`）+ `thread_history_1.sqlite` + rollout 文件 | 体量大，且部分 cwd 已失效 |
| WorkBuddy(+AI) | 人设/记忆/skills | `~/.workbuddy[-ai]/{SOUL,USER,IDENTITY,BOOTSTRAP,MEMORY}.md`、`memory/`、`skills/` | 个人文件 |
| WorkBuddy(+AI) | 项目级 | `<项目>/.workbuddy[-ai]/{memory,skills}/` | 在项目文件夹内，通常被 git 忽略 |

### 4.2 官方文档语义（已核实，出处见附录 E）

- **Claude 信任**以 git 仓库根为键（worktree 沿用主检出的根）；不在仓库内时以启动目录为键并覆盖其子目录（嵌套仓库除外）。因此 worktree 条目不需要恢复。
- **Claude 的 `settings.local.json`**：未被 git 跟踪时，其 allow 规则**不需要经过信任步骤**；被 git 跟踪或 `.claude` 是符号链接时，按"仓库提供"处理，需先信任。
- **Claude 记忆目录**由 git 仓库根推导，worktree 与子目录共用一个；**会话转录目录**由工作目录路径"非字母数字→`-`"推导（超过 200 字符会截断并附哈希）。
- **Claude 续接**：`claude --resume <会话id>` 可在任意目录运行；`--resume <转录文件绝对路径>` 可恢复该文件里的会话。同一个会话 id 在多个项目目录都存在时会报 not found。默认保留 30 天（`cleanupPeriodDays`）。
- **不要使用 `CLAUDE_CODE_PROJECT_DIR_NAME`**：它会把所有项目的转录与记忆合并进一个目录，不能做逐项目映射。
- **Claude `InstructionsLoaded` hook** 在 `CLAUDE.md` 与 `.claude/rules/*.md` 加载时触发；直接读取 `AGENTS.md` 时不触发。
- **Codex 指令**：全局取 `AGENTS.override.md`，否则 `AGENTS.md`，只取第一个非空文件；合并上限 `project_doc_max_bytes`（默认 32 KiB）；每次运行/会话构建一次。
- **Codex 信任**：项目级 `.codex/config.toml`、hooks、rules 仅在项目被信任时加载，未信任则忽略。
- **CC Switch**：数据库含 providers/MCP/prompts/skills/projects，云同步走 WebDAV/S3；`~/.claude/skills` 默认以符号链接同步，失败则复制。

### 4.3 本机基线数据（2026-10-01/02，负责人机器，**仅校准验收用**）

| 对象 | 基线 |
|---|---|
| Claude 信任 | `~/.claude.json` 的 `projects`：29 条原始记录 = **21 个**不同文件夹（8 条是 `/` 与 `\` 写法不同的重复）；15 个已信任；其中 **10 个**文件夹仍存在；`allowedTools` 全为空；无项目级 `mcpServers` |
| Claude Desktop | `claude-code-sessions` 46 个 JSON，15 个不同 `cwd`，14 个存在 |
| Claude 权限规则 | `settings.local.json` **7 个文件、135 条** allow 规则；6 条含绝对路径；0 条命中凭据正则 |
| Claude 记忆 | **61 个** md（约 150 KB）分布在 7 个目录：工作区根 8、dashboards 3、Knowledge 2、langchain-learning 4、notebook_obsidian 5、PersonalCharacter 4、worldquant 35 |
| Claude 会话 | 46 条转录 / 193 MB（默认保留 30 天） |
| Claude 规则文件 | `~/.claude/CLAUDE.md` 与 `~/.codex/AGENTS.md` 字节相同，各 7,576 B；前 2,299 B 是工具首次写入前的手写原件，其后追加了受管区块；非空行 111、唯一 70；各含 1 处绝对路径 |
| Claude 设置 | `settings.json` 顶层键：`effortLevel`、`enabledPlugins`、`env`、`extraKnownMarketplaces`、`language`、`model`、`skipDangerousModePermissionPrompt`；`env` 内含 token 与网关地址（键名） |
| Claude skills | `~/.claude/skills` 是**符号链接**，指向 CC Switch 的 skills 目录：35 个，1,971 文件，约 779 MiB（不含 `.git`/`node_modules`），99.5% 是 `gstack`、`browse` 两个第三方包 |
| Codex 信任 | `config.toml` 的 `[projects.*]` 42 条，全为 `trusted`，29 个路径存在；路径为小写 |
| Codex 内部库 | `state_5.sqlite`：`projects` 13 行、`project_roots` 13 行（12 个不同路径，全部存在）、`threads` 538 行（其中 190 条 cwd 已不存在）；`thread_history_1.sqlite` 499 MB；会话 rollout 约 544 个 / 2 GB |
| Codex `config.toml` | 约 8.7 KB，顶层键：`approval_policy`、`desktop`、`features`、`history`、`hooks`、`marketplaces`、`mcp_servers`、`memories`、`model`、`model_reasoning_effort`、`notify`、`personality`、`plugins`、`projects`、`sandbox_mode`、`service_tier`、`shell_environment_policy`、`tui`、`windows`；含 token 键与 56 处绝对路径 |
| Codex skills | `skills/`：`.system` + 自建 4 个（ai-transition-diary、ai-transition-diary-v2、short-flow、worldquant-alpha-analyzer），75 个文件约 502 KiB，其中 5 个非文本 |
| Codex MCP | 6 个：`node_repl`（16 个 env 键）+ 5 个 Cloudflare 远程服务 |
| Codex 记忆 | `memories/` 为空 |
| WorkBuddy | 人设：BOOTSTRAP/IDENTITY/SOUL/USER（共约 4 KB）；`MEMORY.md` 1.9 KB + `memory/` 4 文件 18 KB；`skills/` 5 文件；`settings.json` 约 36.9 KB，顶层 `claw`、`sandbox`、`enabledPlugins`、`autoLaunchDesired` 等 |
| WorkBuddy AI | 人设 3 个文件；`MEMORY.md` 1.5 KB + `memory/` 2 文件；`skills/` 55 文件约 434 KB；`settings.json` 约 36.8 KB |
| WorkBuddy 项目级 | 7 处：ai-config、FinUnityWorkspace、FinUnityWorkspace/FinUintyWeb、langchain-learning（两个实例都有）、notebook_obsidian、worldquant（`memory` + `skills`，约 558 KB）；合计约 620 KB |
| 登记路径合计 | 两个 agent 共登记 84 个不同路径，59 个仍存在，25 个已不存在 |
| 软件 | node 22.x（nvm4w）、npm 12.x、Python 3.14.x、git 2.54（含 LFS）、uv 0.12、pnpm 10、cargo 1.98、winget 1.29、Codex CLI（npm 全局）、Claude Desktop 内置 Claude Code 2.1.281/2.1.284 |

### 4.4 可复用的现有代码（只读使用，不修改）与禁止依赖

| 复用 | 用法 |
|---|---|
| `sync_core/transaction.py`：`transaction()`、`PlannedChanges`、`SyncLock`、`write_file()` | 还原时的写前备份、锁、期望哈希、回滚。注意 `write_file` 拒绝符号链接 |
| `sync_core/restore.py`：`select_operation()`、`plan_restore()`（不要用 `restore()`，它限定 `UNDOABLE_OPERATIONS`） | `machine undo`；还原时在 `PlannedChanges.metadata` 写 `{"operation": "machine_restore", "path_agents": {路径: agent}}` |
| `sync_core/layout.py`：`data_root()`、`default_state_path()` | 状态目录与备份目录 |
| `sync_core/utils.py`：`atomic_write`、`digest`、`read_bytes`、`json_bytes`、`SECRET` | 公共工具 |
| `sync_core/messages.py`：`Message`（错误码 + 三段式文案） | 新增错误码区间 **E7000–E7499**（E1xxx 至 E6xxx 与 E9001 已被占用） |
| `sync_core/rules_text.py`：`meaningful_lines`、`key` | 统计规则文件的重复行 |
| `sync_core/agents.py`：`PROFILES`（只读） | agent 根目录解析、WorkBuddy 的 runtime/sensitive 名单 |
| `tests/_agent_homes.py`：`build_home`、`SENTINEL`、`ReadTracker` | 测试夹具基础 |
| `sync_core/package/check.py` | 仅**参考**其有界读取与 TOCTOU 复核的写法，不 import |

**禁止**：`sync_core/machine/**` 不得 import `sync_core.package`、`sync_core.cloud`、`sync_core.application`；不得新增第三方运行时依赖（只用标准库 + 已有的 `tomlkit`）。MK-15 提供静态测试守住这一点。

---

## 5. 共享规格

### 5.1 路径规范（实现于 `sync_core/machine/paths.py`）

**规范形式 `norm(path, os_name)`**：
1. 分隔符统一为 `/`；去掉 Windows 长路径前缀 `\\?\`；合并重复斜杠；去掉末尾斜杠（根除外）。
2. 盘符小写（`D:` → `d:`）。
3. 比较键：Windows 上整串转小写（Codex 本身写小写、Claude 写法不一）；Mac/Linux 区分大小写（除非 `machine.config.json` 声明文件系统不区分）。
4. **写回目标机时**使用目标文件系统上的**真实大小写**（`real_case()`）；Codex 的信任键按其惯例写小写。

**目录名推导 `derive_project_dir(native_path)`**：把**该机的原生路径字符串**（Windows 为反斜杠、保留盘符）中的每个非字母数字字符替换为 `-`。例：`D:\<WS>\ai-config` 推导为 `D--<WS>-ai-config` 的形式。推导结果超过 200 字符时返回 `None` 并标记"不支持"（官方会截断并附哈希，本工具不复现）。

**两种键**：
- **记忆目录与信任**用 **git 仓库根**：`git_root(path)` 通过 `git rev-parse --show-toplevel` 取得；worktree 用 `git rev-parse --git-common-dir` 回到主检出；不在仓库内则取文件夹本身。
- **会话转录目录**用**工作目录**。

**根映射 `RootMap`**：一组 `源根 → 目标根`，最长前缀匹配；默认恒等（Windows→Windows 同根）；Mac 必须显式映射；**未命中任何映射的路径 = 孤儿**，不恢复，列入报告。

### 5.2 分档

| 档 | 含义 | restore 行为 |
|---|---|---|
| ①档 | 有官方文档、文件级、低风险 | 自动还原（遵守 §5.4） |
| ②档 | 应用自管或内部库、行为未验证 | **本期不自动还原**；仅采集计数或字段进入 bundle；经 MK-42 实验、MK-43 决策后才可能进入 P5 |
| ③档 | 凭据、会话库、缓存、运行态等 | **永不进入 bundle**，只在报告里记录"存在/需要重新登录" |
| 记录 | 第三方 skills、插件、MCP、软件、登录项 | 只出清单（`reports/`），不搬内容 |

每个条目的 `restore` 字段取值：`auto`（自动）、`confirm`（需显式确认标志）、`manual`（只提示，不写）、`never`。

### 5.3 bundle 格式 v1（实现于 `sync_core/machine/bundle.py`）

**为什么不扩展现有包格式**：现有 `sync_core/package` 的 manifest 顶层键、`DATA_TYPES`、允许的 scheme 都是封闭集合（见 `format.py` 的 `_ALLOWED_SCHEMES`、`DATA_TYPES`）；加类型要改 schema，并牵动已冻结的桌面与云端代码。现有导入语义还是"渲染并追加受管区块"（`importer.py` 的 `_replace_rules`），与"原样还原"相反。

**载体**：单个 zip 文件，文件名 `<前缀>-<UTC yyyymmdd-hhmmss>.zip`；前缀默认 `machine-bundle`，可由 `backup --name` 改写（新手向导用 `AI备份`）。还原端**不依赖文件名**，靠 `manifest.json` 的 `format` 识别。**不加密、不使用 `os.link`**（FAT/exFAT 上的 U 盘不支持硬链接）。写入方式：先写同目录的 `<名>.partial`（独占创建），`fsync`，再 `os.rename` 为最终名；目标已存在则拒绝。

**目录结构**：
```
manifest.json
files/<agent>/<instance>/…          # 原文件镜像（字节级）或字段级派生文件
files/projects/<project_id>/…       # 项目级文件（settings.local.json、.workbuddy* 等）
reports/summary.md
reports/projects.json
reports/software.json
reports/reinstall.json  reports/reinstall.md
reports/login-checklist.md
```
`project_id` = `p-` + `sha256(规范化源路径)` 的前 8 位十六进制（不使用文件夹名，避免中文与大小写碰撞）。

**manifest.json（示例，字段含义见下）**：
```json
{
  "format": "ai-machine-bundle",
  "schema_version": 1,
  "bundle_id": "<uuid4 hex>",
  "content_id": "<sha256，按 (archive_path, sha256) 排序后计算>",
  "created_at": "2026-10-02T10:30:00Z",
  "tool": {"name": "ai-config-machine", "version": "0.1.0", "git_commit": null},
  "source": {"os": "windows", "os_version": "<版本>", "arch": "AMD64", "device_label": null},
  "root_hint": {"workspace_root": "<规范化的源工作区根>"},
  "entries": [
    {"id": "e0001", "agent": "claude", "instance": "main", "kind": "rules", "tier": 1,
     "mode": "file", "logical_path": "claude:main/CLAUDE.md",
     "archive_path": "files/claude/main/CLAUDE.md", "sha256": "<hex>", "size": 7576,
     "restore": "auto", "project_id": null, "flags": ["abs_path:1", "duplicate_lines:41/111"]},
    {"id": "e0002", "agent": "claude", "instance": "main", "kind": "settings_fields", "tier": 1,
     "mode": "fields", "logical_path": "claude:main/settings.json",
     "archive_path": "files/claude/main/settings.fields.json", "sha256": "<hex>", "size": 120,
     "fields": ["language", "effortLevel"], "confirm_fields": ["model"], "restore": "auto"}
  ],
  "projects": [
    {"project_id": "p-3f9a1c2d", "path_norm": "<规范化源路径>", "label": "ai-config",
     "git_root_norm": "<规范化源路径>", "exists_on_source": true,
     "claude": {"trusted": true, "local_rules": 0, "memory_files": 0, "sessions": 2, "registry_sessions": 3},
     "codex": {"trusted": true, "in_project_db": true, "threads": 12},
     "workbuddy": {"dirs": [".workbuddy-ai"]}}
  ],
  "exclusions": [{"logical_path": "claude:main/.credentials.json", "reason": "never"}],
  "warnings": [{"code": "E7101", "message": "<文案>"}],
  "limits": {"max_members": 20000, "max_file_bytes": 67108864, "max_total_bytes": 536870912}
}
```
- `kind` 取值：`rules`、`settings_fields`、`memory`、`permissions_local`、`skills_text`、`persona`、`trust_fields`、`report`。
- `flags` 取值：`abs_path:<N>`（含绝对路径的行数）、`secret_hit`（命中凭据正则，条目默认**不进入** bundle）、`nontext`、`duplicate_lines:<重复>/<总数>`。
- `exclusions[].reason` 取值：`never`、`non_text`、`secret_hit`、`dead_path`、`excluded_by_config`、`too_large`。
- 字段级条目的 `archive_path` 指向只含白名单字段的派生 JSON：`{"source": "<logical_path>", "fields": {...}}`。TOML 来源也派生为 JSON，由还原端用 `tomlkit` 写回。

**校验器 `validate_bundle(path)` 必须拒绝**（并为每条写单测）：
成员名为绝对路径、含 `..`、含盘符、含 NUL 或控制字符、超过 240 字符；经 NFC 归一并转小写后重名；符号链接成员；压缩方式不是 STORED/DEFLATED；成员数、单文件或解压总量超限；压缩比异常（解压炸弹）；`manifest.json` 超过 4 MiB、含重复键、含 NaN/Infinity、`schema_version` 不是 1、含未知顶层键；manifest 列出的文件缺失、或 zip 里有 manifest 之外的文件；任一文件 `sha256`/`size` 不符；zip 被截断或中央目录损坏。读取必须**有界**（不得 `read()` 无上限）。

**`content_id`**：对所有条目的 `(archive_path, sha256)` 按路径排序后计算 sha256。源机无变化时，连续两次备份的 `content_id` 必须相同（可用于"这次比上次变了什么"）。

### 5.4 还原冲突策略

| 目标状态 | 行为 |
|---|---|
| 文件不存在 | 创建（父目录按需创建） |
| 内容相同 | 跳过 |
| 内容不同 | **默认不覆盖**：在同目录写 `<名>.from-bundle`，列入报告；`--overwrite <路径>` 才覆盖，覆盖前先备份 |
| 字段级：目标字段不存在 | 写入 |
| 字段级：目标字段存在且相同 | 跳过 |
| 字段级：目标字段存在且不同 | 报告冲突，保留目标；`--prefer-bundle <字段>` 才覆盖 |
| `confirm` 类字段（见附录 A） | 只显示对比，需 `--confirm-security` 才写 |
| 目标 agent 根目录不存在 | 该 agent 的全部条目标记 `blocked: agent_not_initialized`，**不创建根目录**（提示先安装并启动一次） |
| 项目文件夹不存在 | 该项目的全部条目标记孤儿，不恢复 |
| 目标应用正在运行 | **拒绝写入**（见 MK-31；不提供"忽略运行中"选项） |

**所有写入**：目标应用已关闭 → 写前备份 → `transaction()`（锁、期望哈希、journal、失败回滚）→ 写后重读校验 → 可 `undo`。**写入目的地必须位于解析后的 agent 根目录或映射后的项目文件夹之内**，不得跟随符号链接。

### 5.5 CLI 约定（`scripts/machine.py`）

```
python scripts/machine.py backup    [--config PATH] [--out DIR] [--name 前缀] [--agents 列表] [--apply] [--json]
python scripts/machine.py preflight --bundle PATH [--config PATH] [--root-map 源根=目标根 ...] [--agents 列表] [--out-dir DIR] [--json]
python scripts/machine.py restore   --bundle PATH [--config PATH] [--root-map ...] [--apply]
                                    [--overwrite 路径 ...] [--prefer-bundle 字段 ...] [--confirm-security]
                                    [--codex-trust --confirm-trust 清单哈希] [--agents 列表]
python scripts/machine.py verify    --bundle PATH [--config PATH] [--agents 列表] [--json]
python scripts/machine.py undo      [--index N | --operation-id ID] [--apply]
python scripts/machine.py paths     --self-check
python scripts/machine.py guide     backup
python scripts/machine.py guide     restore [备份文件]
```
- **默认只预览，`--apply` 才写**（与 `scripts/sync.py` 一致）。
- **退出码**与 `scripts/sync.py` 对齐：`0` 成功/无变化，`1` 失败，`2` 输入不完整，`3` 预览有待应用的变化，`4` 冲突或需要确认。
- 错误信息使用 `sync_core/messages.py` 的 `Message`（"发生了什么 / 原数据是否保留 / 下一步怎么做" + 错误码），新增码段 **E7000–E7499**。
- 配置文件默认 `<数据根>/machine.config.json`（数据根由 `layout.data_root()` 给出）。**文件不存在不是错误**（D16，见 MK-12）。
- **`--agents 列表`**：逗号分隔，取值 `claude`、`codex`、`workbuddy`、`workbuddy-ai`（§2 表第三列）；只处理所列助手的条目（项目级条目随其所属助手），默认处理检测到的全部。`backup`、`preflight`、`restore`、`verify` 行为一致。`--name` 是文件名前缀（§5.3）。
- **`guide`**（D16）：面向新手的问答式入口，不带其他参数。它调用与上面各命令相同的库函数，不改变这些命令的参数和语义。退出码：完成或用户主动取消为 `0`，失败为 `1`（不使用 3、4）。详见 §5.7、MK-27、MK-37。
- 启动器：`ai-config.ps1` 与 `ai-config.command` 目前把所有参数转给 `scripts/sync.py`；MK-26 要让**第一个参数为 `machine` 时转给 `scripts/machine.py`**（这两个启动器负责建虚拟环境和装 `tomlkit`；Windows 新手的双击入口不走 `.ps1`，见 MK-28）。

### 5.6 红线（违反即停）

1. **源机只读**：采集器不得写入 agent 目录或项目文件夹。仅允许写入：`--out` 目录、`state` 目录里的日志、系统临时目录（符号链接能力检测，用后删除）。
2. **永不读取、不输出**：`~/.claude/.credentials.json`、Codex `auth.json`、WorkBuddy 的 `keyblob`、`security/`、`app/`、`connectors*`、`user-state.json`、`local_storage`、`device-id`、`models.json`、`*.db*`、CC Switch 数据库、`~/.ssh`、浏览器配置等（以及 `sync_core/agents.py` 里各 profile 的 `sensitive`/`runtime` 名单）。
3. `~/.claude.json` 和 Codex 的 sqlite **只在 [需授权] 后、且只取白名单字段/表**；读入内存的整份文档不得写入日志、报告或异常信息。
4. **任何输出里不得出现凭据值**（token、含用户信息的 URL、邮箱）。URL 只保留主机与路径，去掉用户信息和查询串。
5. 还原时目标应用必须关闭；写前备份；绝不跟随符号链接。
6. 不修改冻结范围，不 import 冻结模块；不新增第三方依赖。
7. 测试不触碰真实 HOME（用 `monkeypatch` 重定向 `HOME`、`USERPROFILE`、`CODEX_HOME`、`CLAUDE_CONFIG_DIR`、`AI_CONFIG_HOME`）。
8. 不推送未授权的内容；不使用 `--force`；不提交 `device.json`、`tmp/`、`release-artifacts/`。

### 5.7 新手入口规范（D16）

**适用范围**：`machine guide …` 问答式向导、它的启动器，以及所有**给人看的文字**——向导画面、错误信息，和 `reports/summary.md`、`preflight-report.md`、`todo.md`、`login-checklist.md`、`verify-report.md` 的正文。不适用于 `--json` 输出、日志和 `manifest.json`。§5.5 的专家命令不变。

**交互规则**
1. 一屏一个问题；每个问题都有安全的默认答案，直接回车即默认；任何时候输入 `q` 都能退出，并说明"没有改动任何文件"（或已改动了什么、如何撤销）。
2. 不让用户输入 ID、逻辑名或命令行参数，只问无法自动得到的（例如备份文件在哪、备份里的工作文件夹在这台电脑上的位置）。要路径时支持"把文件或文件夹拖进窗口"：去掉首尾空白和引号，macOS 还原 `\ ` 转义。
3. 向导**不提供** `--overwrite`、`--prefer-bundle`，也不提供"忽略运行中的应用"。冲突一律保留这台电脑上的版本，把备份里的版本另存为 `.from-bundle`，结果页逐条写明位置和对照办法。需要 `--confirm-security` 或 `--confirm-trust` 的项，先展示清单、默认答"不恢复"，用户明确输入 `y` 后由向导代为传入；传入的必须是**刚展示的那份清单**的哈希，不得缓存或另算一份。
4. 窗口不能一闪而过：成功、取消、失败都停在结果页，等用户按回车才结束。
5. 每次结束都说清三件事：做了什么（或没做什么）、原来的数据是否保留、下一步怎么办。失败沿用 `Message` 三段式，错误码用 **E7400–E7499**，放在最后一行，给技术支持看。未预期的异常也要被捕获：屏幕只显示三段式提示和日志位置，堆栈写入 `state` 目录的日志（不含凭据）。
6. 时间一律显示本地时间；文件名里的 UTC 时间戳不向用户解释，也不要求用户读它。
7. 备份默认保存到桌面。桌面路径用系统的已知文件夹接口取得（Windows：`SHGetKnownFolderPath`，经标准库 `ctypes`——OneDrive 会重定向桌面，直接拼 `~/Desktop` 会错；macOS：`~/Desktop`）；取不到依次退回用户主目录下的 `Desktop`、用户主目录。目标不满足 MK-26 对 `--out` 的限制（如落在 agent 根或项目文件夹内）时，改用用户主目录并说明原因。
8. 可测试：输入、输出、时钟、桌面路径、进程表都能注入；每个向导至少有"全程回车"和"中途 `q` 零写入"两条测试。
9. 不新增读取范围和写入路径：向导只调用既有库函数，受 §5.6 全部约束。
10. 本期文案只提供简体中文。

**词表**（默认画面禁用左列词；用户主动展开的"详细信息"、`--json` 和日志里可以出现。禁用词扫描的对象是向导自己写的文字，路径、文件名和用户数据原样显示，不在扫描范围）

| 内部词 | 默认画面用词 |
|---|---|
| `bundle`、迁移包 | 备份文件 |
| agent、`instance`、`profile` | AI 助手（具体写 Claude、Codex、WorkBuddy、WorkBuddy AI） |
| `preflight`、预检、`dry-run`、预览 | 检查（并说明"先检查，不会改动任何东西"） |
| `apply`、`--apply` | 开始备份／开始恢复 |
| `undo` | 撤销上一次恢复 |
| `rules`、`settings_fields`、`permissions_local`、`persona`、`skills_text`、`memory` | 规则、设置、已批准的操作、人设、技能、记忆 |
| `trust`、`trust_fields` | 信任的文件夹 |
| `orphan`、孤儿、`dead_path` | 这台电脑上找不到的文件夹（已跳过） |
| `.from-bundle` | 另存的备份版本 |
| `root-map`、映射 | 不出现；必须问时说"备份里的工作文件夹在这台电脑上的哪个位置？" |
| 设备 ID、`project_id`、`content_id`、`sha256`、`manifest`、`schema`、`tier`、档、`journal`、事务、`state`、`store` | 不出现 |

---

## 6. 任务总览

规模：S ≈ 半天内，M ≈ 1–2 天，L ≈ 2–4 天（含测试，仅供排序）。状态列由执行者更新：☐ 未开始、◐ 进行中、☑ 完成（验收通过）。

| ID | 任务 | 规模 | 依赖 | 门禁 | 状态 |
|---|---|---|---|---|---|
| **P0 前置** | | | | | |
| MK-00 | 冻结声明与文档指引 | S | — | — | ☑ |
| MK-01 | 保存现状并推送到 `wip/` 分支 | S | — | **G1 推送** | ☑ |
| MK-02 | 恢复绿灯：依赖分层、2 个测试、秘密正则、CI | M | — | — | ◐（本机通过，CI 待验） |
| **P1 规格与骨架** | | | | | |
| MK-10 | 路径层 `paths.py` | S | MK-02 | — | ☑（已授权只读 self-check） |
| MK-11 | 分档目录 `catalog.py` | S | MK-02 | — | ☑（批准范围与完整沙箱 bundle 哨兵通过） |
| MK-12 | 配置文件 `machine.config.json` 与加载器 | S | MK-10 | — | ◐（加载／排除与 11 项快照通过；历史排除基线未全核对） |
| MK-13 | bundle 格式 v1 与校验器 | M | MK-02 | — | ☑（本机格式验收；U 盘实测待后续） |
| MK-14 | WorkBuddy 结构调研（只读） | M | MK-00 | **G7 批准 WorkBuddy 分档** | ☑（保守分档已批准，加载实验仍待后续） |
| MK-15 | 测试夹具与静态守卫 | M | MK-13 | — | ☑ |
| **P2 采集与备份** | | | | | |
| MK-20 | 软件环境清单 | S | MK-13 | — | ✓（本机清单与整包报告通过；未知版本已注明） |
| MK-21 | ①档采集：规则、设置字段、记忆、Codex skills | M | MK-10,11,12,13,15 | — | ✓（沙箱与 MK-26 真机整包通过；当前快照差异已记录） |
| MK-22 | 项目档案采集（Claude/Codex） | L | MK-21 | **G2 读 `~/.claude.json`/sqlite** | ✓（沙箱与 MK-26 整包通过；加载／恢复待后续任务） |
| MK-23 | WorkBuddy 采集 | M | MK-14,13,15 | G7 | ✓（G7 保守范围与整包通过；自动加载未验证） |
| MK-24 | skills/插件/MCP 重装清单 | M | MK-21,22,23 | — | ✓（沙箱、本机清单与 MK-26 整包通过） |
| MK-25 | 登录与密钥清单 | S | MK-21,22,23 | — | ✓（沙箱、本机清单与 MK-26 整包通过） |
| MK-26 | `machine backup` 命令与启动器转发 | M | MK-20…25 | **G3 在真机运行** | ✓（首份快照已获 M1；另获 G3 修正隐私遗漏，196 条／668504 B） |
| MK-27 | 新手备份向导（问答骨架、`guide backup`） | M | MK-26 | — | ✓（隔离向导与整包测试通过，双击真机待 MK-28） |
| MK-28 | 新手启动器与快速上手页（`start.py`、双击入口） | M | MK-27 | **G3 单独授权＋G2** | ◐（14 项隔离／静态测试通过，资源管理器双击真机待授权／操作） |
| **P3 预检与还原** | | | | | |
| MK-30 | `machine preflight` | M | MK-26 | — | ✓（隔离比较与 Windows→Mac 映射通过；实机恢复待净室） |
| MK-31 | `machine restore` ①档引擎 | L | MK-30 | G4 目标机写入 | ◐（完整引擎／CLI／向导沙箱通过；真实恢复待 G4／净室） |
| MK-32 | Codex 信任还原 | S | MK-31 | **G5 信任清单确认** | ✓（哈希门禁、注释保留、冲突与幂等沙箱通过；真机待 G5） |
| MK-33 | Claude 记忆映射还原 | M | MK-31 | — | ✓（目标 Git 根重推导、大小写复用与索引冲突沙箱通过） |
| MK-34 | WorkBuddy 还原 | M | MK-31,23 | G7 | ◐（显式候选文本恢复沙箱通过；加载仍需人工核验） |
| MK-35 | `machine verify` | M | MK-31…34 | G6（可选项） | ✓（文件／字段核对及破坏检出沙箱通过；人工与 G6 不计自动通过） |
| MK-36 | `machine undo` 与回滚演练 | S | MK-31 | — | ◐（完整沙箱撤销及共用接口回归通过；净室待 MK-41） |
| MK-37 | 新手恢复向导与启动器 | M | MK-28,30…36 | — | ✓（两类启动器与向导／专家等价沙箱通过；真实新手待 MK-44） |
| **P4 净室演练** | | | | | |
| MK-40 | 准备净室环境 | — | — | **G8 负责人提供环境** | ☐（负责人明确暂时没有净室） |
| MK-41 | 端到端演练 | M | MK-31…36,40 | — | ☐ |
| MK-42 | ②档实验矩阵（只记结论） | M | MK-41 | — | ☐ |
| MK-43 | ②档落地决策 | S | MK-42 | 负责人签字 | ☐ |
| MK-44 | 新手试用（零基础可用性验收） | M | MK-28,37,41 | **G9 安排试用者** | ☐ |
| **P5 ②档落地（有条件）** | | | | | |
| MK-50 | Claude 信任字段合并 | M | MK-43 | G4 | ☐ |
| MK-51 | Claude 会话选择性迁移 | M | MK-43 | G4 | ☐ |
| MK-52 | Codex 项目与会话 | M | MK-43 | G4 | ☐ |
| **P6 真机与 Mac** | | | | | |
| MK-60 | 第二台 Windows 真机 | M | MK-41 | G8 | ☐ |
| MK-61 | Mac | L | MK-41 | G8 | ☐ |
| MK-62 | 签收 | S | 全部（含 MK-44） | 负责人签字 | ☐ |
| **P7 可选（默认不做）** | | | | | |
| MK-70 | 规则文件去重（会改源机原文件） | S | MK-62 | 负责人逐条批准 | ☐ |
| MK-71 | 定时备份 | S | MK-62 | 负责人批准 | ☐ |
| MK-73 | CodeBuddy / CC Switch 识别实验 | M | MK-62 | 负责人批准 | ☐ |
| MK-74 | 免安装分发（视 MK-44 结果） | M | MK-44 | 负责人批准 | ☐ |
| MK-75 | 图形外壳（视 MK-44 结果） | M | MK-44 | 负责人批准 | ☐ |

**里程碑**：M1 = MK-26 产出第一份真实 bundle 与报告，由负责人过目；M2 = MK-41 净室通过；M3 = MK-62 签收（须含 MK-44 新手试用通过）。

---

## 7. 任务详述

### P0 前置

#### MK-00　冻结声明与文档指引　［S］
- **目的**：让后来者不再沿旧方向投入，且从 README 一次点击就能找到本文件。
- **步骤**：
  1. `README.md` 顶部新增"当前方向"小节（不超过 10 行）：指向本文件；说明桌面客户端、服务器/云同步、受管区块同步处于冻结，及原因。**不删除**原有内容。
  2. 在 `DESKTOP-TASKS.md`、`UX-TASKS.md`、`TODO.md`、`task.md`、`docs/desktop-client-plan.md`、`docs/server-architecture.md`、`docs/server-deployment.md` 顶部各加一段"状态：已冻结，被 MACHINE-MIGRATION-TASKS.md 取代（日期）；其中的验收记录是历史记录"。不改正文。
  3. 更新 `PROJECT_STATUS.md`（该文件被多个会话共同编辑，**改前先 `git diff` 确认没有他人未提交的修改**）：按仓库契约更新 `overview`/`progress`/`next`/`evidence`/`updated`。`progress` 如实写"方向调整，旧桌面/服务器工作冻结，原有未验收项保持未验收"；`next` 指向本文件的 P0；`evidence` 增加本文件。**不得写"已完成"。**
- **验收**：README 一步可达本文件；`PROJECT_STATUS.md` 自检通过（frontmatter 无重复键；`updated` 是未加引号的真实日期；`status` 取值合规；`evidence` 每项都是存在的项目内相对路径，不含绝对路径、隐藏路径、自引用）。
- **回退**：`git revert`。

#### MK-01　保存现状并推送到 `wip/` 分支　［S］　**[G1 需授权]**
- **目的**：ai-config 当前有 4 个只在本机的提交和约 150 个未提交条目，没有任何远端备份（截至 2026-10-02）。
- **步骤**：
  1. 请负责人确认 `origin` 仓库为**私有**。未确认前停止。
  2. 记录 `git status` 与 `git log origin/main..HEAD --oneline`。
  3. 运行 `python scripts/check-secrets.py`。**已知 2 处误报**（`tests/test_application_protocol.py`、`tests/test_package_policy.py` 的测试样例）。出现其他命中则停止并报告。
  4. 按主题拆成 3–4 个提交，**不要一个巨型提交**：(a) 核心 `sync_core` 与脚本；(b) 桌面/服务器/云/部署（冻结代码）；(c) 文档；(d) 测试。注意包含 `claude/CLAUDE.md` → `claude/AGENTS.md`、`templates/project/CLAUDE.md` 删除这两处已存在的改动。
  5. 推送到新分支 `wip/machine-kit-baseline`（**不推 main**）。
- **验收**：`git rev-list --count origin/wip/machine-kit-baseline..HEAD` 为 0；`git status` 干净或只剩有意排除的文件（`device.json`、`tmp/`、`release-artifacts/`、`desktop/.build-venv`）。
- **红线**：不 `--force`；不提交 `device.json`、`tmp/`、`release-artifacts/`。
- **回退**：删除远端分支；提交可 `git revert`。
- 此后新工作在 `feat/machine-kit`（以该 wip 分支为基）上进行。

#### MK-02　恢复绿灯　［M］
- **目的**：当前完整测试在仅装核心依赖的环境里连收集都过不了（缺 `fastapi`），CI 一推就红；另有 2 个失败测试和一个覆盖面太窄的秘密正则。
- **步骤**：
  1. **依赖分层**：`requirements.txt` 保持只含核心依赖；新增 `requirements-test.txt`（`-r requirements.txt` + `pytest`）和 `requirements-frozen-test.txt`（核心测试依赖 + 冻结部分所需的 `fastapi`、`httpx`、`sqlalchemy`、`pyjwt`、`cryptography` 等，版本取自 `server/requirements.lock.txt`）。依赖冻结部分的测试模块文件头加 `pytest.importorskip(...)`，使核心环境**跳过**而不是收集失败。
  2. **CI**（`.github/workflows/check.yml`）：拆成 `core`（`pip install -r requirements-test.txt`；pytest；`check-secrets.py`）与 `frozen`（装 `requirements-frozen-test.txt`，只在冻结路径变更时触发）。
  3. 修 `tests/test_package_export.py` 中 `test_application_service_previews_then_exports_without_exposing_source_paths` 的最后一条断言：代码实际产出的排除类别是 `user_excluded`（见 `sync_core/package/policy.py` 的 `select_portable_sources`），不是 `not_selected`。**产品行为正确，是测试过期，只改测试。**
  4. 修 `tests/test_config_consistency.py::test_single_tool_installation_reports_the_other_as_absent`：设置了 `CODEX_HOME`、`CLAUDE_CONFIG_DIR`、`AI_CONFIG_HOME` 时失败。新增 `tests/conftest.py` 的 autouse fixture：清除这三个变量，并把 `HOME`、`USERPROFILE` 指向 `tmp` 下的新目录。
  5. **秘密正则**：扩展 `sync_core/utils.py` 的 `SECRET`，覆盖 GitHub PAT（`gh[pousr]_…`、`github_pat_…`）、AWS Access Key（`AKIA…`）、`Authorization: Bearer …`、JWT（三段式）、**无引号**的 `api key: 值` / `password: 值`、中文"密码/口令/密钥/令牌：值"。同时让 `scripts/check-secrets.py` 改为复用 `sync_core.utils.SECRET`（消除两套重复的正则）。
  6. 新增 `tests/test_secret_patterns.py`：10 个应命中的样例形态 + 若干不应命中的普通文本（如句子里单独出现的 "token" 一词）。**样例值一律在运行时拼接**（如 `"gh" + "p_" + "a" * 36`），仓库里不留完整命中。
  7. 为 `tests/test_application_protocol.py`、`tests/test_package_policy.py` 里已有的样例也改为运行时拼接，使 `check-secrets.py` 不再命中。**不要用目录级白名单。**
- **验收**：
  - 仅装核心依赖的干净 venv：`python -m pytest -q --basetemp tmp/run-<n>` 全绿；
  - 设置 `CODEX_HOME` 等环境变量后重跑，仍全绿；
  - `python scripts/check-secrets.py` 命中 0；
  - `tests/test_secret_patterns.py` 通过；
  - CI 的 `core` job 在 Windows 与 macOS 上通过。
- **回退**：`git revert`。

### P1 规格与骨架

#### MK-10　路径层　［S］
- **做什么**：实现 `sync_core/machine/paths.py`，规格见 §5.1：`norm()`、`same_path()`、`derive_project_dir()`、`git_root()`、`RootMap`、`real_case()`。
- **测试** `tests/test_machine_paths.py`，必须覆盖本机实测的写法：`/` 与 `\` 混用、`\\?\` 前缀、小写盘符、末尾斜杠、已搬迁的目录；Windows→Mac 的根映射样例；`derive_project_dir` 对已知样例的结果（如 `D:\x\ai-config` → `D--x-ai-config`，全小写盘符的写法推导出小写开头的名字）；长度超过 200 返回 `None`。
- **手工核验**（只读，由 `python scripts/machine.py paths --self-check` 提供，在负责人机器上运行一次）：对 `~/.claude.json` 里每个**存在转录目录**的路径，推导结果与 `~/.claude/projects/` 里的实际目录名一致。**[需授权：读取 `~/.claude.json`，只取路径键]**
- **验收**：单测全绿；self-check 在负责人机器上一致率 100%（对存在转录目录的路径）。

#### MK-11　分档目录 `catalog.py`　［S］
- **做什么**：把附录 A 落成数据模块：每一项含 `agent`、`instance`、`kind`、`tier`、`mode`（file/fields）、匹配规则（相对 agent 根的 glob，或字段路径）、`restore`（auto/confirm/manual/never）、`status`（approved/draft）。WorkBuddy 的项标 `draft`，**未经 MK-14 定稿前，采集器默认跳过 draft 项**。
- **要求**：**默认拒绝**（allowlist）：不在目录里的文件或字段一律不采集。
- **验收**：负责人逐行批准附录 A；对每个"never / 不搬"项写哨兵测试：沙箱里放入哨兵串，断言产出的 bundle 的**所有字节**（含 reports）里没有该串（通用断言 `assert_no_sentinel(zip_path)` 由 MK-15 提供）。

#### MK-12　配置文件与加载器　［S］
- **做什么**：`sync_core/machine/config.py` 加载 `machine.config.json`：
  - `core_projects`（原生路径写法即可，内部规范化）；
  - `exclude_patterns`（默认含 `.claude/worktrees/**`、`**/scratch-workspaces/**`、用户主目录本身、`.chatgpt-projects/**`）；
  - `root_map`（`[{"from","to"}]`，默认恒等）；
  - `instances`（默认 `workbuddy` → `~/.workbuddy`，`workbuddy-ai` → `~/.workbuddy-ai`）；
  - `include_desktop_fields`（默认空；只允许外观/语言类：`codeFontSize`、`sansFontSize`、`localeOverride`、`conversationDetailMode`，设备类键一律拒绝）；
  - `allow_secret_hit_paths`（默认空；负责人逐文件人工确认后才可加入）；
  - `running_process_names`（目标应用的进程名，带默认值）。
- **文件不存在不是错误（D16）**：全部取默认值；项目文件夹由 MK-22 的 `known_folders()` 发现、MK-27 过滤后交给用户勾选。
- 校验：路径必须为绝对路径或 `~` 开头；拒绝未知键。
- 提供**占位示例** `docs/machine-migration-config.example.json`（占位路径，**不得写真实绝对路径**）。负责人本机的真实配置放在数据根目录，不进仓库。
- **验收**：对 §3 D12 的 11 个项目，在负责人机器上做只读预览：11 个全部命中；排除项数量与盘点一致（Claude 只登记的 7 个路径、1 个 ChatGPT 项目、Codex 信任里 21 个 `c:\users\…` 下的目录）。

#### MK-13　bundle 格式 v1 与校验器　［M］
- **做什么**：实现 `sync_core/machine/bundle.py`，严格按 §5.3：`BundleWriter`（`add_file`、`add_report`、`finalize` 无覆盖写入）、`read_bundle()`（有界、逐文件校验 sha256）、`validate_bundle()`、`content_id`。
- **测试** `tests/test_machine_bundle.py`，至少覆盖 §5.3 列出的**每一种**拒绝情形，另加：无覆盖发布（目标已存在则拒绝）、`content_id` 在无变化时稳定、中文文件名正常往返。
- **验收**：全部拒绝用例通过；往返后字节完全一致；不使用 `os.link`（`grep` 为 0）。

#### MK-14　WorkBuddy 结构调研（只读）　［M］　**[G7 负责人批准]**
- **目的**：WorkBuddy 的加载机制与 `settings.json` 内部结构我们没有验证。本任务只调研，不写代码，**产出的是定稿的附录 A.WB**。
- **步骤**：
  1. 对 `~/.workbuddy` 与 `~/.workbuddy-ai` 列出顶层条目，按 `sync_core/agents.py` 中 `workbuddy` profile 的 `persona`/`memory`/`skills`/`settings`/`sensitive`/`runtime` 名单分类，**列出未分类项**（本机已知：`keyblob`，应视为敏感）。
  2. **不要打开**人设与记忆文件的内容（`SOUL/USER/IDENTITY/BOOTSTRAP/MEMORY.md`、`memory/*`）：只记录名称与大小。
  3. `settings.json`（约 36 KB，顶层键很少，说明值很大）：**只记录顶层与二级键名和值类型/大小**，不得输出任何值；重点弄清 `claw`（疑含用户信息）、`enabledPlugins`、`sandbox`、`autoLaunchDesired` 各自是什么、哪些可移植。
  4. 项目级目录 `<项目>/.workbuddy[-ai]/` 的结构（`memory/`、`skills/`），以及 `skills/` 里哪些是应用写入的迁移标记（如 `.*_migration.json`，不搬）。
  5. 查 WorkBuddy 官方文档或做一次**不含个人内容的加载实验**，回答：人设与记忆文件在全局目录和项目目录里分别在什么时候被加载？本机两个实例各自的账户目录（UUID 命名的目录）是什么性质？
  6. 产出 `docs/machine-migration-workbuddy.md`：目录地图、分档表（整文件/字段级/只记录/never）、识别证据（官方文档或实测，标注"已验证/未验证"）、待解问题；并把定稿的 A.WB 提交负责人批准。
- **验收**：文档完成；A.WB 的每一行都有依据；负责人批准后 `catalog.py` 里 WorkBuddy 项由 `draft` 改为 `approved`。
- **红线**：不得打开 §5.6 第 2 条列出的文件。

#### MK-15　测试夹具与静态守卫　［M］
- **做什么**：
  1. 新增 `tests/_machine_fixtures.py`（**不要大改** `tests/_agent_homes.py`，在其上扩展）：`build_machine_home(home, ...)` 创建沙箱：
     - Claude：`~/.claude.json`（含若干 `projects`，混用 `/` 与 `\`、重复写法，以及 `oauthAccount`、`machineID`、`mcpServers` 的**哨兵值**）、`projects/<推导名>/memory/*.md` 与 `<id>.jsonl`、若干项目文件夹含 `.claude/settings.local.json`；
     - Codex：`config.toml`（含 `[projects.'…']`、`shell_environment_policy.set` 的哨兵 token、`notify`、`hooks`、注释与特殊排序）、`state_5.sqlite`（用标准库 `sqlite3` 建 `projects`/`project_roots`/`threads` 表）、`skills/`（含一个非文本文件）；
     - WorkBuddy 两个实例：人设、`MEMORY.md`、`memory/`、`skills/`、`settings.json`（`claw.users` 放哨兵）、`keyblob` 等诱饵，及项目级 `.workbuddy[-ai]/memory`。
  2. 通用断言：`assert_no_sentinel(zip_path)`；`snapshot_tree(root)` 与 `assert_tree_unchanged(before, root)`（用于"源机零写入"）。
  3. `tests/test_machine_import_direction.py`：静态检查 `sync_core/machine/**` 不 import 冻结模块、不 import 第三方包（除 `tomlkit`）。
- **验收**：夹具能被 MK-21 之后各任务直接复用；静态守卫在人为加入一条违规 import 时失败。

### P2 采集与备份（源机零写入）

#### MK-20　软件环境清单　［S］
- **做什么**：`sync_core/machine/collect_records.py` 里的软件采集，产出 `reports/software.json`：
  - OS 与版本、架构；
  - `node`、`npm`、`python`、`git`（及 `git lfs`）、`uv`、`pnpm`、`cargo`、`rustc`、Windows 的 `winget` / macOS 的 `brew` 的版本；
  - `npm ls -g --depth=0 --json` 的包名与版本；
  - `codex --version`；Claude Desktop 内置的 Claude Code 版本（列其 `claude-code` 目录下的版本目录名）；Codex Desktop 与 CC Switch 的版本（**获取方式未验证**：取不到则记 `null` 并在 summary 标注）；
  - 能否创建符号链接（在系统临时目录试建并删除）；
  - 目标应用的进程名（供目标机预检使用）。
- **要求**：命令执行注入 `run(cmd) -> (rc, out)` 以便测试；每个命令 10 秒超时；**不联网**。
- **验收**：测试用假 `run` 覆盖；在负责人机器上与 §4.3 的软件基线一致。

#### MK-21　①档采集：规则、设置字段、记忆、Codex skills　［M］
- **步骤**：
  1. 解析 agent 根：Claude 取 `CLAUDE_CONFIG_DIR` 否则 `~/.claude`；Codex 取 `CODEX_HOME` 否则 `~/.codex`（可参考 `sync_core/agents.py` 的 `root_env`/`locations`，**只读使用**）。
  2. **整文件**（附录 A.1）：字节级复制。同时算：`abs_path:<N>`、`secret_hit`、`nontext`；对规则文件用 `sync_core/rules_text.py` 统计 `duplicate_lines:<重复>/<总数>`。
  3. **字段级**（附录 A.2）：Claude `settings.json` 与 Codex `config.toml`（TOML 用标准库 `tomllib` 读取）按白名单取字段，写成派生 JSON；`restore` 为 `confirm` 的字段单独标在 `confirm_fields`。
  4. **Claude 记忆**：对每个核心项目先算 `git_root`，再定位 `projects/<derive(git_root)>/memory/`，复制 `**/*.md`（含 `MEMORY.md`）。条目带 `project_id`，供还原端重新推导目录名。按 git 根去重。
  5. **Codex 自建 skills**：`skills/<名>/**`（排除 `.system/`）的文本文件原样复制；**非文本文件不进 bundle**，写入 `exclusions`（`non_text`，附大小与 sha256），并在 summary 提示由负责人决定。
  6. 命中凭据正则的条目：**不进入 bundle**，记入 `exclusions`（`secret_hit`）；除非该路径已在 `allow_secret_hit_paths` 里。
- **验收**：
  - 哨兵测试通过；
  - 采集前后被读文件的 hash 与 mtime 不变（`assert_tree_unchanged`）；
  - 在负责人机器上：Claude 记忆 **61 个文件、7 个目录**；规则文件 2 个、各 7,576 B、`duplicate_lines` 为 41/111；Codex 自建 skills 4 个，其中 5 个非文本文件列入 exclusions。

#### MK-22　项目档案采集　［L］　**[G2 需授权：只读 `~/.claude.json` 与 Codex sqlite]**
- **步骤**：
  1. 对每个核心项目：规范化路径、是否存在、`git_root`；生成 `project_id`。
  2. **Claude**：
     - 把 `~/.claude.json` 读入内存，**只**取 `projects` 里对应 git 根的 `hasTrustDialogAccepted` 与 `hasClaudeMdExternalIncludesApproved`（附录 A.2）；规范化键后合并重复写法（任一为 `true` 则取 `true`）。读入的整份文档**在提取后立即丢弃**，不得进入日志或异常。
     - 各核心项目下（深度 ≤ 2，排除 `node_modules`、`.git`、`.claude/worktrees/**`）的 `.claude/settings.local.json` 原样复制（`permissions_local`），统计 `permissions.allow` 条数、含绝对路径的条数。
     - 会话只记**计数**：`projects/<derive(cwd)>/` 下 `*.jsonl` 的数量；Desktop `claude-code-sessions/*.json` 中 `cwd` 落在该项目之下的数量。
  3. **Codex**：
     - `config.toml` 的 `[projects]` 里属于核心项目的信任条目，写为 `trust_fields` 派生文件（路径规范化后存放）；
     - `state_5.sqlite` 用 `file:…?mode=ro`（URI）只读打开，仅读 `project_roots.path` 与按 `cwd` 统计的 `threads` 计数；打不开则记警告，不中断。
  4. 汇总写入 `reports/projects.json` 与 manifest 的 `projects[]`；同时统计"死条目"（登记过但路径已不存在）数量，写进 summary。
  5. **对外提供 `known_folders()`**（D16）：只返回规范化后的路径列表（不含其他字段），来源仅限本任务已获授权读取的几处，供 MK-27 在没有 `machine.config.json` 时发现项目文件夹。
- **验收**（对照 §4.3，允许日常使用带来的小幅漂移，需说明）：
  - 11 个核心项目；
  - Claude 信任：规范化后 21 个、15 个已信任、10 个存在；
  - `settings.local.json` 7 个文件、135 条规则、6 条含绝对路径；
  - Codex `project_roots` 12 个不同路径且全部存在；
  - `~/.claude.json` 中**不在白名单**的键（`oauthAccount`、`machineID`、`userID`、`mcpServers`、缓存、用量等）在 bundle 与日志里**零出现**（哨兵）；
  - `known_folders()` 在夹具上返回预期集合，且不读取白名单之外的键。

#### MK-23　WorkBuddy 采集　［M］　（依赖 MK-14 定稿与 G7）
- **做什么**：按定稿的 A.WB 采集两个实例的人设、`MEMORY.md`、`memory/**`、`skills/**`（排除应用写入的迁移标记）、白名单设置字段；以及各核心项目下（深度 ≤ 2）的 `.workbuddy/`、`.workbuddy-ai/` 的 `memory`、`skills`。
- **要求**：§5.6 第 2 条列出的文件**一律不得打开**；用 `ReadTracker` 断言诱饵（`keyblob`、`security/…`、`app/connector-keys/…`、`*.db`）从未被读。**不得新建 `AGENTS.md`。**
- **验收**：哨兵与"零写入"测试通过；在负责人机器上，条目数与 §4.3 的 WorkBuddy 基线一致（两个实例的人设与记忆；`.workbuddy-ai/skills` 约 55 个文件；项目级 7 处）。

#### MK-24　skills / 插件 / MCP 重装清单　［M］
- **做什么**：产出 `reports/reinstall.json` 与 `reinstall.md`：
  - **CC Switch skills**：只记名称、是否 git 仓库、远端 URL（去掉用户信息与查询串）、HEAD commit、体积。`~/.claude/skills` 记为"符号链接 → CC Switch"，**不跟随、不复制内容**。
  - **Claude 插件与 marketplaces**：来自 `settings.json` 的 `enabledPlugins`/`extraKnownMarketplaces`（名称）以及 `~/.claude/plugins` 里的安装记录（名称、版本、来源）。
  - **Codex**：`mcp_servers`（名称、传输类型、命令程序名或 URL 的主机+路径、参数个数、env **键名**，不带值）、`plugins`、`marketplaces`、`hooks`、`notify`（只记"存在"）。
- **验收**：清单中**没有任何值**（哨兵）；体积小于 1 MB；本机应列出 35 个 CC Switch skills、6 个 Codex MCP 服务器。

#### MK-25　登录与密钥清单　［S］
- **做什么**：生成 `reports/login-checklist.md`：**只列"要重新登录/重填什么、去哪里取"**，不含任何值。根据检测结果自动填项：Claude 登录；Claude `settings.json` 的 `env` 键名（如网关地址与令牌）；Codex 登录；Codex `shell_environment_policy.set` 的变量名；CC Switch providers；Git 凭据管理器及 `credential.*` 的主机名；SSH 私钥（只提示"由你用安全方式自行转移"，**不进 bundle**）；各 MCP 的 OAuth 授权（列主机）；WorkBuddy 账号登录。
- **验收**：不含任何值；每个被检测到的凭据类文件/键在清单里都有对应一行。

#### MK-26　`machine backup` 命令与启动器转发　［M］　**[G3 需授权在真机运行]**
- **做什么**：实现 `scripts/machine.py backup` 与 `sync_core/machine/backup.py`：
  1. 默认**预览**：按档、按 agent 汇总条目数，列出 flags、exclusions、会写入的 zip 路径；`--apply --out <目录>` 才写。
  2. `--out` 必须是已存在的目录，且**不得位于任何 agent 根或核心项目文件夹之内**（防止递归与污染）。
  3. 汇总调用 MK-20…25；组装并写 zip；写完立即 `validate_bundle` 并打印 zip 的 sha256。
  4. `reports/summary.md`：各档条目数；**未备份清单**（含 `secret_hit` 与 `non_text`，要醒目）；规则文件重复提示（"非空行 111，唯一 70"）；含绝对路径的文件；死条目数；"如何在新机还原"的说明（用 §5.7 的词：MK-37 完成前写专家命令版并标注"新手入口待提供"，完成后改为"双击「恢复」"）。
  5. 同步修改 `ai-config.ps1`（保持 CRLF）与 `ai-config.command`：第一个参数为 `machine` 时转给 `scripts/machine.py`；其余行为不变，`tests/test_launchers.py` 保持通过。
  6. 实现 `--agents`（§5.5）：只备份所列助手，项目级条目随其所属助手过滤；`--name` 作为文件名前缀（§5.3）。MK-27 的"勾选助手"就是传这个参数。
- **验收**：
  - 沙箱测试：产出的 zip 通过校验、哨兵零出现、源机零变化、`content_id` 稳定；
  - **在负责人机器上真跑一次**（G3）：zip 小于 5 MiB（预期约 1–2 MiB）；条目数与盘点一致；运行前后被采集文件 hash 全部不变；`validate_bundle` 通过。
- **里程碑 M1**：把 `summary.md` 与 zip 交负责人过目，再继续 P3。

#### MK-27　新手备份向导　［M］
- **目的**：落实 D16 的"备份"一半：把 `machine backup` 包成一次问答，用户只做选择，不需要填写任何东西。
- **依赖**：MK-26。
- **步骤**：
  1. `sync_core/machine/guided.py`：问答原语（提问、确认、多选、等待回车的结束页；输入输出可注入）、词表渲染与"禁用词扫描"函数、拖入路径清洗、桌面路径解析、本地时间格式化，均按 §5.7。`sync_core/machine/guide_backup.py`：备份流程。`scripts/machine.py` 新增 `guide backup`。
  2. **流程**（每屏一个问题；括号里是示例文案，可调整，但须满足 §5.7）：
     - **欢迎**：一句话讲清楚"把 Claude、Codex、WorkBuddy 的规则、记忆和设置打包成一个文件放到桌面；不会改动任何现有文件，也不会上传到网上"。
     - **选 AI 助手**：列出检测到的助手并默认全选，回车即全选；输入编号可取消或恢复勾选；没检测到的显示"未找到，已跳过"；一个都没找到则说明原因并结束。选择结果以 `--agents` 传给引擎。
     - **选项目文件夹**：有 `machine.config.json` 的 `core_projects` 就用它（并说明"已使用你的配置文件"）；没有就用 MK-22 的 `known_folders()`，去掉不存在的和命中 `exclude_patterns` 的，默认全选、可取消。**不得要求用户写任何配置文件。**
     - **检查**（只读）：调用与 `backup` 预览相同的函数，用大白话汇总，如"规则 N 个、记忆 N 个、已批准的操作 N 条、技能 N 个"；"有 N 个文件因为可能含密码或不是文本，没有放进备份"（列出位置，要醒目）。
     - **确认**：只问一次"开始备份吗？"（回车＝开始，`q`＝退出）。
     - **写入并结束**：用 `--name AI备份` 写到桌面；结束页写明文件的完整位置、大小和本地时间，并提醒"请把它复制到新电脑；文件里有你的个人记忆，请妥善保管"。
  3. **测试** `tests/test_machine_guided_backup.py`（隔离 HOME，用 MK-15 的夹具）：脚本化"全程回车"产出的 bundle，其 `content_id` 与等价参数的 `machine backup --apply` 相同；中途输入 `q` 零写入；没有 `machine.config.json` 也能跑完；桌面路径的各级回退；拖入的带引号或含空格路径可用；整段屏幕输出通过禁用词扫描；少选一个助手时 bundle 里没有它的任何条目。
- **验收**：测试全绿；产出的 zip 通过 `validate_bundle`、哨兵零出现、源机零写入（沿用 MK-15 的断言）。真机双击验收在 MK-28。
- **红线**：沿用 §5.6；向导只调用既有库函数，不新增读取范围。
- **回退**：`git revert`。

#### MK-28　新手启动器与快速上手页　［M］　**[G3 单独授权；真机运行另需 G2]**
- **目的**：让不会用命令行的人双击一个图标就进入向导，并且在**没改过任何设置的新电脑**上也能跑起来。
- **依赖**：MK-27。
- **步骤**：
  1. `scripts/start.py`（只用标准库，不得 import `sync_core`）：Python 低于 3.11 时报错；与 `ai-config.ps1` 共用同一个 `.venv` 和 `.venv/.requirements.sha256` 戳记（比较时忽略大小写），已就绪则不重装；缺 Python、版本过低、建环境失败、装依赖失败，都按"发生了什么／原有数据／下一步"三段式给出中文提示并以退出码 2 结束；成功后用 `.venv` 的 Python 运行 `scripts/machine.py`，参数原样转发。
  2. **Windows 入口** `备份.cmd`（仓库根目录）：**不调用** `ai-config.ps1`。Windows 客户端版默认的执行策略会拒绝运行 `.ps1`（据微软文档，本仓库未实测，见 §11），而且 `tests/test_launchers.py` 禁止在 `ai-config.ps1` 中出现 `ExecutionPolicy`；本任务同样**不使用 `-ExecutionPolicy`、不修改策略**。流程：`cd /d "%~dp0"` → 有 `.venv\Scripts\python.exe` 就用它，否则找系统 Python（先 `py -3`，再 `python`；`python` 必须真能执行 `-c` 并返回 0，以免命中应用商店的占位程序）→ 运行 `scripts/start.py guide backup` → 结尾 `pause`。文件只含 ASCII，用 CRLF。找不到 Python 时的中文说明怎么显示（例如用记事本打开带 BOM 的说明文件；或 `powershell -Command` 内联输出，它不是脚本文件），由执行者在 `cmd.exe` 与 Windows Terminal 上实测后选定，记入 §11。
  3. **macOS 入口** `备份.command`：调用 `ai-config.command machine guide backup`（依赖 MK-26 的转发）。**在 git 里把 `ai-config.command` 和新增的 `.command` 设为可执行**（`git update-index --chmod=+x`）：`ai-config.command` 目前是 100644，Finder 双击会因没有执行权限而失败。
  4. `.gitattributes` 追加 `*.cmd text eol=crlf` 与 `*.command text eol=lf`（现有规则里只有 `*.ps1` 固定了行尾）。
  5. **`docs/quickstart.md`**（一屏以内，遵守词表）：写"准备（只需一次）"和"备份"；"恢复"一节由 MK-37 补全。下载的文件被系统拦截（SmartScreen、macOS 的"无法验证开发者"）时怎么放行，**按实机所见写，不凭记忆**。README 顶部的"当前方向"小节（MK-00）增加一行指向它。
  6. **测试**：扩充 `tests/test_launchers.py`（原有断言不改）：新启动器只含 ASCII、行尾正确、含 `pause`、不含 `ExecutionPolicy`、Windows 版不调用 `.ps1`、`.command` 在 git 里是 100755（找不到 git 或不在仓库内则跳过）；新增 `tests/test_start_bootstrap.py`（注入假的进程调用：已就绪不重装、缺 Python、版本过低、建环境失败、装依赖失败各一条）。
- **验收**：
  - 测试全绿，`tests/test_launchers.py` 的原有用例仍通过。
  - **在负责人机器上**（G3＋G2；G2 是因为发现项目文件夹要读 `~/.claude.json` 和 Codex sqlite 里的路径），在**没有 `machine.config.json`** 的情况下（机器上已有该文件的，验收时临时改名，结束后改回），从资源管理器**双击** `备份.cmd`（不是从终端运行）：全程只按回车（不超过 5 次：欢迎、助手、项目文件夹、确认、结果页）、不输入任何文字；桌面出现备份文件，窗口停在结果页；运行前后被采集文件的 hash 全部不变；`validate_bundle` 通过。
  - 把仓库分别放进含空格和含中文的目录，各双击一次。
  - "未改过执行策略的 Windows 环境"和"macOS"两项并入 MK-44、MK-61 验证，在此之前记为"未验证"，不得写成通过。
- **红线**：引导（建 `.venv`）发生在采集器运行之前，只能写项目目录下的 `.venv`；其余沿用 §5.6。不新增第三方依赖；不自动提权，不修改 PATH 和系统设置。
- **回退**：`git revert`；删除 `.venv` 和桌面上生成的备份文件。

### P3 预检与还原（目标机）

#### MK-30　`machine preflight`　［M］
- **做什么**（**只读**）：
  1. 校验 bundle；读取目标机 agent 根（不存在则标 `agent_not_initialized`）；
  2. 对比软件版本（主版本不同则警告，缺失则列"需安装"）；检测目标应用是否在运行；
  3. 路径映射：核心项目逐个判定"可恢复 / 文件夹不存在（孤儿）"；
  4. 逐条判定 `new / same / differs / blocked(原因)`；字段级逐字段判定；
  5. 生成 `preflight-report.md` 与 `todo.md`（安装软件、重新登录、重装清单、待确认项），正文遵守 §5.7；`--agents` 只检查所列助手；
  6. 生成**信任清单**及其哈希 `trust_list_hash`（供 MK-32 使用）。
- **验收**：沙箱两种情形输出正确（空 HOME 全部 `new`；已有不同文件则 `differs`）；文件夹不存在被列为孤儿；Mac 根映射样例可用；目标 agent 目录前后无任何变化。

#### MK-31　`machine restore` ①档引擎　［L］　**[G4 目标机写入]**
- **做什么**：`sync_core/machine/apply.py` + `procs.py`。
  1. 复用 MK-30 的判定。目标应用在运行（按 `running_process_names` 检测）则**拒绝**，**不提供"忽略"开关**。
  2. 生成 `PlannedChanges`：对整文件按 §5.4；对 JSON 字段级合并（Claude `settings.json`，只设白名单字段）；`metadata = {"operation": "machine_restore", "path_agents": {...}}`；`expected` 记录预览时各目标文件的哈希。
  3. 目的地解析：只允许位于解析后的 agent 根或映射后的项目文件夹之内（`safe_destination`）；符号链接一律拒绝。
  4. 用 `transaction(plan, state/backups, state_root=state, ...)` 写入；写后重读并核对哈希。
  5. 范围：规则文件、白名单设置字段、`settings.local.json`、Codex 自建 skills；记忆交给 MK-33，WorkBuddy 交给 MK-34，Codex 信任交给 MK-32（共用本引擎的备份与回滚）。
  6. `settings.local.json` 的目标文件夹若是 git 仓库且该文件已被**跟踪**：只警告（Claude 会把被跟踪的文件当作仓库提供）。
  7. 输出：写入/跳过/冲突/孤儿的汇总；退出码 0/3/4。
  8. 支持 `--agents`（§5.5）：只处理所列助手的条目。新手恢复向导（MK-37）依赖这个行为。
- **验收**（沙箱 HOME）：
  - 空目标 → 全部还原且哈希一致；
  - 相同 → 无操作（退出 0）；
  - 不同 → 不覆盖，产出 `.from-bundle`；`--overwrite` 能覆盖并有备份；
  - 应用在运行（注入假进程表）→ 拒绝；
  - 制造中途失败 → 回滚；
  - 恶意 manifest（`../`、绝对路径）在校验阶段即被拒；
  - 目标 agent 根不存在 → `blocked`，不创建目录。

#### MK-32　Codex 信任还原　［S］　**[G5 需负责人确认清单]**
- **做什么**：`restore --codex-trust --confirm-trust <哈希>`。
  1. 取 bundle 的 `trust_fields` 中核心项目的条目，映射到目标路径；**仅对文件夹存在者**恢复。
  2. 先打印清单并说明："将信任这些文件夹——Codex 会加载其 `.codex/` 配置、hooks、rules。"需 `--confirm-trust` 的值等于预检算出的 `trust_list_hash`，否则拒绝。
  3. 用 `tomlkit` 解析目标 `config.toml`，追加 `[projects.'<路径>'] trust_level = "trusted"`（Windows 上路径小写；保持注释与顺序）；已存在但级别不同的条目保留目标、报告冲突。
  4. **不得**为不在核心项目清单内的路径写入信任，即使 bundle 里有。
- **验收**：沙箱：注释与顺序不变、仅新增预期条目；重复运行幂等；哈希不符则拒绝；孤儿不写。

#### MK-33　Claude 记忆映射还原　［M］
- **做什么**：把 bundle 里的记忆条目写到目标机 `<claude 根>/projects/<derive(git_root(目标路径))>/memory/`。
  - 目标路径由 `RootMap` 从源 `path_norm` 映射得到；
  - 若目标 `projects/` 下已有同名目录的**大小写变体**（Windows 不区分大小写），复用已有目录，不新建重复目录；
  - 同名文件不同内容按 §5.4；`MEMORY.md` 索引**不自动合并**，冲突时写 `.from-bundle` 并提示人工合并。
- **验收**：Windows→Windows 同根时目标路径与源一致；Windows→Mac 样例（映射到 Mac 的路径）推导出的目录名正确；已有大小写变体目录被复用。

#### MK-34　WorkBuddy 还原　［M］　（依赖 G7）
- **做什么**：把两个实例的人设、记忆、skills、白名单字段，以及项目级 `.workbuddy[-ai]/` 的内容，按**原相对路径**写回 `~/.workbuddy[-ai]/…` 与映射后的项目文件夹。**不创建 `AGENTS.md`，不写应用标记文件**（`workspace-state.json` 等）；要求 WorkBuddy 已关闭。
- **识别核验**（没有官方依据，需人工）：`todo.md` 里写明"打开 WorkBuddy，确认人设与记忆可见"，并把结果记入 `docs/acceptance.md`。
- **验收**：沙箱中人设/记忆/skills 被还原；诱饵文件前后哈希不变、从未被读（`ReadTracker`）。

#### MK-35　`machine verify`　［M］　**[G6 可选项需授权]**
- **自动项**：
  - V1 规则文件哈希；
  - V2 白名单设置字段；
  - V3 记忆哈希；
  - V4 `settings.local.json` 哈希；
  - V5 Codex 信任条目；
  - V6 软件版本；
  - V7 重装清单勾选状态；
  - V8 WorkBuddy 文件哈希。
- **人工项**：登录完成；规则"加载核验"。纯镜像模式下没有版本戳，改为生成**问答模板**：从规则文件里随机挑一句不少于 12 字的唯一句子，让负责人在新会话问"请复述你全局规则里以「…」开头的那一整行"，并与原句比对。
- **可选项（需授权）**：(a) 读取 Codex 最新会话记录的开头事件，核对规则文件是否被注入（只取事件类型与是否含某句，不取正文）；(b) 输出一段 Claude `InstructionsLoaded` hook 配置片段，**由负责人手动加入，工具不写 settings**。
- 输出 `verify-report.md`，状态为 PASS / FAIL / MANUAL / SKIP；有 FAIL 则退出码 4。`--agents` 只核验所列助手（用户只恢复了部分助手时，其余项记 SKIP，不算 FAIL）；正文遵守 §5.7。
- **验收**：沙箱中完整还原后全部 PASS；故意破坏一个文件，对应检查必须 FAIL。

#### MK-36　`machine undo` 与回滚演练　［S］
- **做什么**：`undo.py`：用 `restore.recent_operations(state, operation_filter="machine_restore")` 列出；用 `select_operation` + `plan_restore` + `transaction` 回滚（不要调用 `restore.restore()`，它限定 `UNDOABLE_OPERATIONS`）。`--apply` 才写。
- **验收**：在沙箱与（MK-41 时的）净室各做一次完整 undo，目标文件逐字节恢复到还原之前；撤销后再次预检，状态回到还原前。

#### MK-37　新手恢复向导与启动器　［M］
- **目的**：落实 D16 的"恢复"一半：在新电脑上，不懂技术的人把备份文件拖到「恢复」上（或双击后按提示选），看懂检查结果，确认一次，完成恢复；后悔了能撤销。
- **依赖**：MK-28、MK-30…36。
- **步骤**：
  1. `sync_core/machine/guide_restore.py` 与 `scripts/machine.py guide restore [备份文件]`：只**调用** MK-30…36 的库函数，不复制它们的判定逻辑。
  2. **找备份文件**：命令行或拖放传入的路径优先；否则只看桌面、下载目录、启动器所在目录及其上一级、可移动磁盘的根目录（Windows 用 `GetDriveType`，macOS 取 `/Volumes/*`）的**顶层** `*.zip`，不递归扫盘。是不是备份文件看 `manifest.json` 的 `format`（有界读取，沿用 §5.3 的上限；大于 `max_total_bytes` 上限的 zip 直接跳过），不看文件名。恰好一个就直接用；多个按时间倒序列出（本地时间和大小）让用户选；没有就请用户把文件拖进窗口。选定后先 `validate_bundle`，不通过就说"这个文件不完整或不是备份文件"并停止。
  3. **入口菜单**：仅当本机状态里有可撤销的 `machine_restore` 记录时出现——"1 从备份文件恢复（默认）／2 撤销上一次恢复"。撤销走 MK-36，同样先展示将改动的文件，再确认。
  4. **检查**（只读，MK-30）：改写成大白话——"备份于 <本地时间>，来自 <Windows／Mac> 电脑，包含…"；"这台电脑上：N 项是新的，会直接恢复；N 项已有但内容不同，会保留现有的，并把备份里的版本另存在原文件旁边（文件名末尾多一个 .from-bundle）供你对照；N 个文件夹在这台电脑上找不到，已跳过"。只有备份里的工作文件夹整体找不到、或系统不同时，才多问一句"备份里的工作文件夹在这台电脑上的哪个位置？"（拖入文件夹），内部转成 `--root-map`。
  5. **应用在运行**：点名列出正在运行的 Claude、Codex、WorkBuddy，请用户关闭后按回车重新检查，直到全部关闭或用户退出；**不提供跳过**（MK-31）。
  6. **需要额外确认的项**：Codex 信任的文件夹清单、涉及安全或模型选择的设置（`confirm` 类字段）。各自单独展示清单，默认答案是"不恢复"（§5.7 第 3 条）。
  7. **总确认**：一句话概括"将新建 N 个文件，跳过 N 个，不会覆盖任何现有内容"，只问一次。
  8. **恢复与自动核验**：调用 MK-31（含 MK-32、33、34 被选中的部分），随后自动运行 MK-35 的自动项；结果页只给"全部正常"或"有 N 项需要你看一下"，细节收在"按 d 查看详细信息"里。
  9. **接下来要做的事**：把 `todo.md` 改写成不超过 5 条——重新登录哪几个、哪些第三方技能需要重装、怎样在新会话里确认规则已生效（用 MK-35 的问答模板）；并写明"觉得不对，可再次运行「恢复」选择撤销"。
  10. **启动器**：`恢复.cmd`、`恢复.command`，规则同 MK-28。`恢复.cmd` 支持把文件拖到图标上（`%1` 传给向导；路径含空格时带引号）；macOS 的 `.command` 接收不了拖放，向导改为提示"把备份文件拖进这个窗口，然后按回车"。补全 `docs/quickstart.md` 的"恢复"一节。
  11. **测试** `tests/test_machine_guided_restore.py`（隔离 HOME）：空目标全程回车→全部恢复且哈希一致；冲突→保留现有、产出 `.from-bundle`、画面里没有"覆盖"选项；应用在运行→拒绝并循环等待（注入进程表）；信任清单的哈希来自刚展示的清单（清单被改动则拒绝）；撤销后逐字节还原；拖入带引号或含空格的路径可用；坏文件被拒；屏幕输出通过禁用词扫描；向导恢复的结果与等价的 `machine restore --apply` 逐文件一致。
- **验收**：测试全绿；沙箱里向导恢复的文件与专家命令逐字节一致。净室实机验收并入 MK-44。
- **红线**：沿用 §5.6 与 MK-31 的全部限制；向导不得新增写入路径或读取范围。**严禁对真实工作区运行**（同 MK-40）。
- **回退**：`git revert`；已恢复的内容用 `machine undo`。

### P4 净室演练（决定性）

#### MK-40　准备净室环境　**[G8 负责人提供]**
- 新建**干净的 Windows 用户账户或虚拟机**；安装 Claude Desktop、Codex Desktop、WorkBuddy 与 WorkBuddy AI、CC Switch（版本按 `software.json`）；各自登录并**启动一次**（创建数据目录）。
- 把 11 个核心项目文件夹的**副本**放到映射后的路径。**严禁对真实工作区运行 `restore --apply`**：它会写入各项目的 `.claude/settings.local.json` 与 `.workbuddy*`。
- 把 bundle zip 复制进来。
- 建议在"各应用已装好、**尚未安装 Python**、未做迁移"时做一个可回退的快照（虚拟机快照；账户方案则再备一个同样干净的账户）。MK-41 与 MK-44 都要从这个起点开始；保持 Windows 默认的执行策略，不得为方便而修改。
- 产出：净室就绪清单（负责人勾选）。

#### MK-41　端到端演练　［M］
- 在净室运行 `preflight → restore → verify`，人工完成 `todo.md`（安装、登录、重装清单、信任确认）。
- 产出差异报告 `docs/machine-cleanroom-report-<日期>.md`：每个验收项（附录 B）的结果、与源机的差异、例外清单、遇到的问题与修正。
- **验收**：附录 B 的 1–9 项全部通过，例外全部列出。**里程碑 M2。**

#### MK-42　②档实验矩阵（只记结论，不自动化）　［M］
- **前置**：只在净室；应用关闭；每次实验前备份将要改动的文件。每项记录"步骤 / 预期 / 实际 / 结论 / 回退"，产出 `docs/machine-experiments.md`，并记录各应用的版本。
- **实验**：
  - **(a) Claude 信任**：应用关闭时，对 `~/.claude.json` 做 `projects.<某核心项目的 git 根>.hasTrustDialogAccepted` 的**单字段**合并（原子写，先备份）。启动 Claude Desktop/CLI：是否不再弹信任框？登录态是否完好？其余键是否原封不动（前后 diff）？
  - **(b) Claude 会话**：把 1 个小会话的 `<id>.jsonl` 放进 `projects/<derive(目标 cwd)>/`；分别试 `claude --resume <id>` 与 `claude --resume <转录绝对路径>`；再把对应的 Desktop 登记 JSON 放入 `claude-code-sessions/`，看 Desktop 的会话列表是否出现；记录 cwd 与原机不同时的表现。
  - **(c) Codex**：还原信任后，在 Codex Desktop"添加文件夹"，是否识别 `config.toml` 的信任；项目列表能否由此重建；旧线程是否可迁（预期不可）。
  - **(d) WorkBuddy**：还原后打开某个工作区，确认人设、记忆、项目级 memory 可见。
- **验收**：每项都有完整记录和明确结论。

#### MK-43　②档落地决策　**[负责人签字]**
- 依据 MK-42，逐项定为"自动化 / 只生成清单 / 不做"，并据此修订 P5 任务。不通过实验的项保持 `manual`。

#### MK-44　新手试用（零基础可用性验收）　［M］　**[G9 负责人安排试用者]**
- **目的**：D16 的验收。"简单"要由没见过它的人来证明，而不是开发者自己判断。
- **依赖**：MK-28、MK-37、MK-41；需要 MK-40 的可重置净室。
- **准备**：负责人提供试用者（至少 1 位，建议 3 位；不熟悉命令行、没参与过本项目）和 1 位只观察、不帮忙、不提示的观察者。每位试用者从**同一个起点**开始：净室恢复到"各应用已装好、未装 Python、未做迁移"，保持 Windows 默认的执行策略；一份刚生成的备份文件；只给 `docs/quickstart.md`（屏幕或纸面），试用者不得提问，但鼓励边做边说出想法。G9 同时覆盖试用者在净室内的写入操作，不覆盖任何真实机器。
- **任务**：0. 按说明准备环境（安装 Python）；A. 在净室里备份（测的是操作体验，备份内容多少无所谓）；B. 恢复准备好的那份备份文件，并说出"哪些已经恢复、接下来还要自己做什么"；C. 撤销一次。
- **记录**（观察者填，匿名）写入 `docs/machine-novice-trial-<日期>.md`：每项任务是否独立完成、用时、每次停顿的位置和时长、被误解的词或画面（含文件名）、是否需要任何口头帮助、是否发生误操作及后果、试用者的原话。任务 0 单独计时。记录项沿用 `docs/acceptance.md` 第三节（卡点、误解、是否需要口头帮助），把"是否误改 JSON"换成"是否误操作"；该节原有的、基于 README 与 getting-started 的版本属于冻结方向，原样保留。
- **通过标准**：每位试用者都独立完成 A 与 B，且各自用时不超过 **10 分钟**（任务 0 不计入；时限是建议值，由负责人在 G9 确认）；没有文件被误覆盖或丢失；试用者能用自己的话说清"备份文件在哪、恢复了什么、还要手动做什么"；所有"看不懂的词或画面"已修改，并由一位试用者复测一次。任务 C 只要求记录。
- **失败处理**：按停顿位置改文案或流程（回到 MK-27、28、37），重做受影响的试用。若多数停顿来自终端本身（不知道怎么输入、不敢按回车、被系统拦截提示吓到）或来自安装 Python，记入 §11，由负责人决定是否启动 MK-75、MK-74。
- **验收**：试用记录完成；通过标准全部满足；结论写入 `docs/acceptance.md`，作为附录 B 第 11 项的依据；"未改过执行策略的 Windows 环境"下的双击入口（MK-28 遗留）在此验证。
- **红线**：试用只在净室进行，**严禁对真实工作区运行**；记录不得含试用者的姓名、账号或个人文件内容。

### P5 ②档落地（有条件，按 MK-43）

#### MK-50 / MK-51 / MK-52
- **MK-50 Claude 信任字段合并**（若 MK-42a 通过）：`restore --claude-trust`；要求应用已关闭、原子写、写前备份、信任清单确认；只写白名单键。
- **MK-51 Claude 会话选择性迁移**（若 MK-42b 通过）：按"最近 N 天或指定项目"选择；转录与 Desktop 登记**成对**放置；注意同一会话 id 只能出现在一个项目目录；先 `validate`，目标应用关闭。
- **MK-52 Codex 项目与会话**：若没有可行且受支持的路径，则**不做**，把"手动添加文件夹"的步骤写进 `todo.md`。
- 每项的验收：在净室复现 MK-42 的实验结果；可 `undo`。

### P6 真机与 Mac

- **MK-60 第二台 Windows 真机** **[G8]**：在真实第二台机器上重做 MK-41。
- **MK-61 Mac** **[G8]**：根目录映射；文件系统大小写；OS 专属字段（`windows.sandbox` 不带；命令与路径类字段不带）；目录名推导在 Mac 路径上的验证；**未验证项**：Claude Desktop、Codex Desktop、WorkBuddy 在 Mac 上的数据目录。
- **MK-62 签收**：更新 `docs/acceptance.md` 与 `PROJECT_STATUS.md`；列出例外清单；附录 B 全部通过（含第 11 项）。**里程碑 M3。**

### P7 可选（默认不做）

- **MK-70 规则文件去重**：**会修改源机原文件**，需负责人逐条批准。展示三个候选：(A) 首次写入前的 2,299 B 手写原件（在 `~/.ai-sync/state/backups/` 下 ID 以 `b5312e97` 开头的备份里，由其 manifest 指向）；(B) 现状 7,576 B；(C) 去重版（按 `rules_text.key` 去重并保持顺序与标题）。负责人选定后用 `transaction()` 写入，写前备份。
- **MK-71 定时备份**：Windows 任务计划或 macOS launchd 定期运行 `machine backup --apply`，保留最近 N 份。需负责人批准。
- **MK-73 CodeBuddy / CC Switch**：本期只在 summary 里列出存在与体积。若要纳入，先做识别实验（新会话问答），再决定。
- **MK-74 免安装分发**：目前新电脑要先装 Python，再联网安装 tomlkit，这对新手仍可能是门槛（以 MK-44 的记录为准）。候选：(A) 随备份文件夹携带 Windows 嵌入式 Python 和 tomlkit 的 wheel，不用安装也不用联网；(B) 用打包工具生成单个可执行文件（会引入新的构建依赖，且未签名的可执行文件容易被 SmartScreen 或杀毒软件拦截）。评估项：是否要管理员权限、是否要联网、体积、被拦截的概率。仅在 MK-44 证明该步骤是主要障碍、且负责人批准后才做。
- **MK-75 图形外壳**：若 MK-44 证明终端问答本身是障碍，用标准库 `tkinter` 为同一流程做窗口（勾选框、选文件、确认按钮），复用 `guide` 的流程函数，不引入第三方依赖，不属于桌面客户端（D15、§2）。先确认目标系统的 Python 带 tkinter（有些发行版不带）。需负责人批准。

---

## 8. 附录 A：分档与字段白名单

### A.1 整文件（①档，`restore = auto`）

| agent | 路径（相对 agent 根或项目） | 说明 |
|---|---|---|
| claude | `CLAUDE.md`；`rules/**/*.md`（若存在） | 原样 |
| codex | `AGENTS.md`；`AGENTS.override.md`（若存在） | 原样 |
| claude | `projects/<由 git 根推导>/memory/**` | 仅核心项目；目录名在目标机重新推导 |
| claude | `<核心项目>/.claude/settings.local.json` | 深度 ≤ 2；排除 `.claude/worktrees/**`、`node_modules` |
| codex | `skills/<名>/**`（排除 `.system/`） | 自建 skills 的文本文件；非文本不进 bundle，记入 exclusions |

### A.2 字段级

| 来源 | 直接带（auto） | 需确认（confirm：只显示，需 `--confirm-security`） | 不带 |
|---|---|---|---|
| Claude `settings.json` | `language`、`effortLevel` | `model`（依赖 provider）、`skipDangerousModePermissionPrompt`（安全） | `env`（含令牌与网关）、`enabledPlugins`、`extraKnownMarketplaces`（进重装清单）、其余所有键 |
| Codex `config.toml` | `model_reasoning_effort`、`personality`、`features.*`、`memories.*`、`history.persistence`；`windows.sandbox`（仅 Windows 目标） | `model`、`service_tier`、`approval_policy`、`sandbox_mode`（安全） | `notify`、`hooks`、`plugins`、`marketplaces`、`mcp_servers`（只记录）、`shell_environment_policy.*`、`projects`（走 MK-32）、`tui`、其余所有键 |
| Codex `desktop.*` | 默认全不带；负责人可在配置里从 `codeFontSize`、`sansFontSize`、`localeOverride`、`conversationDetailMode` 中勾选 | — | 设备类（`microphoneInputDeviceId`、`hotkey-window-*`、`open-in-target-preferences` 等） |
| Claude `~/.claude.json`（②档，仅采集，不自动还原） | `projects[核心项目 git 根].hasTrustDialogAccepted` | `hasClaudeMdExternalIncludesApproved` | 其余全部（`oauthAccount`、`machineID`、`userID`、`mcpServers`、缓存、用量、`lastSessionId` 等） |
| Codex 信任（①档，但走 MK-32 单独门禁） | `config.toml` 的 `projects.<路径>.trust_level`（仅核心项目、仅存在的文件夹） | — | 非核心项目的条目 |

### A.3 只记录（进 `reports/`，不搬内容）

第三方 skills（CC Switch 的 35 个）、Claude 插件与 marketplaces、Codex 的 MCP/插件/marketplaces/hooks/notify、软件环境、登录与密钥项。

### A.4 不搬（永不进入 bundle）

登录凭据文件（Claude `.credentials.json`、Codex `auth.json` 等）、CC Switch 数据库与设置、会话数据库与转录（②档实验除外）、日志、缓存、用量统计、远程连接、`~/.claude/skills` 符号链接的内容、WorkBuddy 的 `keyblob`/`security/`/`app/`/`connectors*`/`user-state.json`/`local_storage`/`device-id`/`models.json`/`*.db*`/UUID 命名的账户目录/应用标记文件（`workspace-state.json`、`workspace-display-names.json`、`.*_migration.json`）。

### A.WB WorkBuddy（**2026-10-02 经负责人 G7 批准的保守分档**）

| 类别 | 内容 |
|---|---|
| 整文件（manual） | `BOOTSTRAP.md`（若存在）、`IDENTITY.md`、`SOUL.md`、`USER.md`、`MEMORY.md`、`memory/**/*.md`、自建 `skills/**` 文本（排除凭据命中、非文本、应用迁移标记及 VCS）；项目级 `<核心项目>/.workbuddy/{memory,skills}/**` 与 `.workbuddy-ai/…` 同理。自动加载未验证，本期只做手动还原候选。 |
| 只记录 | `settings.json.enabledPlugins` 的插件名称进入重装清单；`autoLaunchDesired` 与 `sandbox` 当前只记录存在，暂不恢复。 |
| 不带 | `claw`、`pluginConfigs`、`officeFileAssociationsRepairMarker`、`mcp-approvals.json`、账户 UUID 目录、未知 `scripts/`、`settings.json` 其余键及 §A.4 所列。 |
| 备注 | **不新建 `AGENTS.md`**；两个实例各自独立（`workbuddy`、`workbuddy-ai`）。官方资料仅证明产品记忆与 `.codebuddy` 代码配置的部分加载，不证明 `.workbuddy` 文件何时加载；见 `docs/machine-migration-workbuddy.md`。 |

---

## 9. 附录 B：验收清单（完成定义）与例外

以下全部通过，且例外已列出，才算本工作完成（MK-62）：

1. **规则**：新会话里加载核验通过（问答模板），文件哈希与源机一致。
2. **设置**：白名单字段一致；`confirm` 类字段已显示对比并由负责人确认。
3. **记忆**：Claude 记忆哈希一致、新会话可见；WorkBuddy 的记忆与人设可见。
4. **权限规则**：135 条（7 个文件）不用重新批准。
5. **信任**：核心项目中文件夹存在者，Codex 已恢复；Claude 已恢复，或在清单里由负责人确认（取决于 MK-43）。
6. **项目列表**：11 个核心项目出现在 Claude Desktop 与 Codex Desktop（Codex 可为手动添加）。
7. **skills / MCP**：自建 skills 哈希一致；第三方按重装清单重装后版本一致；MCP 能连接（Cloudflare 等需重新授权）。
8. **软件版本**在允许范围内。
9. **登录**全部完成。
10. （可选，取决于 MK-43）抽样旧会话可续接。
11. **新手可用（D16）**：MK-44 通过——未接触过本工具的试用者，只看 `docs/quickstart.md`，独立完成一次备份和一次恢复，无文件被误覆盖或丢失。

**例外（必须在报告中列出，不算失败）**：登录态与 OAuth；路径不同的机器（Mac）上的路径差异；进行中的后台任务；模型输出的随机性；Codex 旧会话；已不存在的文件夹对应的死条目。

---

## 10. 附录 C：门禁与授权

| 编号 | 门禁 | 对应任务 |
|---|---|---|
| G1 | 推送到 `origin` 的 `wip/` 分支，且已确认远端私有 | MK-01 |
| G2 | 只读 `~/.claude.json` 与 Codex sqlite（只取白名单字段/表） | MK-22、MK-10 的 self-check、MK-28 的真机运行 |
| G3 | 在真机运行 `machine backup --apply`（含双击向导） | MK-26、MK-28（各自单独授权） |
| G4 | 在目标机写入（每次 `--apply` 前确认） | MK-31、MK-50…52 |
| G5 | 信任清单确认（`--confirm-trust`） | MK-32 |
| G6 | 读取 Codex 会话记录开头事件（可选核验） | MK-35 |
| G7 | 批准 WorkBuddy 分档（A.WB 定稿） | MK-14、MK-23、MK-34 |
| G8 | 负责人提供净室/第二台真机/Mac | MK-40、MK-60、MK-61 |
| G9 | 安排未接触过本工具的试用者（至少 1 位，建议 3 位）和 1 位只观察不帮忙的观察者；确认匿名试用记录可以保存；确认通过标准里的时限 | MK-44 |

**回退总则**：源机只读，无需回退；目标机用 `machine undo`；仓库每任务一提交，可 `git revert`；bundle 目录只增不改。

---

## 11. 附录 D：未验证事项与已知风险（出现新情况请追加到这里）

**未验证**：
- 2026-10-02 交付复查修正：专家采集器原先未统一执行配置排除，现已在目录遍历前剪枝并在读取前过滤，排除哨兵零读取；93 项合并隔离测试通过。随后发现首份 ZIP 的 4 个文本文件命中邮箱格式（1 个项目权限文件、1 个 WorkBuddy 记忆、1 个 WorkBuddy AI 人设、1 个项目 WorkBuddy AI 技能），违反 §5.6 的输出要求；旧 M1 仅保留历史范围核对，旧 ZIP 不作为隐私通过的交付包。补入邮箱／含用户信息 URL／转义写法检测，以及预览、发布和恢复前的整体隐私门禁，合并 101 passed；不会输出匹配值。
- 2026-10-02 负责人过目修正摘要及排除范围并单独授权本次 G3：从原 ZIP 既有快照另存 `AI备份-修正版-20261002-211502.zip`，196 条、11 项目、668504 B、总排除 7。完整性和整体隐私检查通过，命中文件与元数据均为 0；原 ZIP 哈希不变。未重新读取助手目录，不称为当前机器刷新快照；项目权限统计按实际保留文件重算。SHA-256 与过程见 `docs/acceptance.md`。
- 2026-10-02 负责人回复“暂时没有净室”，MK-40／41／42／44 保持等待环境；没有在日常工作区恢复或撤销，没有新推送。MK-12 历史排除基线、CI、真实双击、U 盘及跨设备加载仍未完成。
- 2026-10-02 P3 实现与合并隔离测试：备份／恢复／核验／撤销、向导及启动器共 91 passed。专家 CLI 的 preview→apply→verify→undo 只在合成 HOME 验证；受保护目标诱饵零读取，真实目标尚未写入。MK-40 仍需负责人提供独立 Windows 用户或虚拟机，准备项见 `docs/machine-cleanroom-checklist.md`；MK-41／42／44、真实加载、默认策略与跨机均未验收。WorkBuddy 候选文本默认跳过，显式同意后才复制，加载保持人工项。
- 2026-10-02 MK-28 已实现 ASCII／CRLF 的 Windows 双击入口、LF／可执行位的 Mac 入口和共享 .venv 引导，14 项测试通过。本机 cmd.exe 执行缺 Python 提示片段可显示中文；Windows Terminal、资源管理器双击、含空格／中文目录的真实双击、默认策略、系统拦截和 Mac 尚未实测。成功／取消／向导失败由结果页等待回车，准备失败由启动器 pause，避免额外第六次按键。未在真实助手上运行新双击入口。
- 2026-10-02 MK-26 经本次 G3 授权生成首份真实 zip：200 条、11 项目、723584 B，完整性／SHA-256 校验通过，采集文件前后哈希及 mtime 一致；排除 2 个疑似凭据文本及 1 个非文本。负责人已过目摘要并确认范围，M1 通过。后续恢复、U 盘、跨机加载和新手试用尚未验收。具体校验值见 `docs/acceptance.md`。此前只读预览段落保留为历史过程。
- 2026-10-02 MK-14 只读结构调研与 MK-23 保守采集：负责人本次会话批准 `manual` 的人设／记忆／文本技能分档，明确排除 `claw`、`sandbox` 和账户状态。真实机仅内存预览 76 条（人设 9、记忆 40、技能文本 27；项目级 38），疑似凭据排除 1、警告 0；读过的文件二次哈希／mtime 一致。没有写 zip，没有读凭据或数据库。`~/.workbuddy-ai/skills` 当前元数据共有 55 文件，含 VCS 与迁移标记，本期可纳入文本少于 55。具体结构与官方证据见 `docs/machine-migration-workbuddy.md`；真实加载与自动恢复仍未验证。
- 2026-10-02 MK-22 经本次会话两次 G2 授权后只读预览：11 个核心文件夹均存在，归属于 8 个不同 Git 根；`.claude.json` 规范化项目 21 个、存在 12 个、已信任 16 个（旧基线为 10／15）；Codex sqlite 的项目根 12 个且均存在，线程 cwd 行 545。权限文件去重后 7 个、allow 规则 135 条，与基线一致；当前绝对路径规则 9 条（旧基线 6）。Claude Desktop 登记目录当前 0 个 JSON（旧基线 46），原因未核实。采集器在内存中生成 11 个项目画像和 27 个条目，未写 zip 或更改本机数据；整包验收仍待 MK-26。
- 2026-10-02 MK-21 只读内存预览与 §4.3 基线不一致：规则 2 个、各 7,576 B，`duplicate_lines:41/111` 与基线一致；Claude 记忆当前可纳入 62 个、分布于 8 个 git 根目录，另有 1 个命中凭据检测而排除（基线为 61 个／7 目录）；Codex 自建 skills 仍为 4 个，但当前可纳入文本文件 25 个、非文本排除 1 个（基线称 75 文件／5 非文本）。未生成 zip、未读取信任文件或会话库、未输出内容。负责人本次会话已确认以当前快照继续核对；原基线保留为历史参照，整包验收仍待 MK-26。
- Claude Desktop 的会话登记缺失时，列表能否恢复（MK-42b）。
- Claude 信任写入 `~/.claude.json` 后的实际行为与登录态完整性（MK-42a）。
- Codex 是否有受支持的"添加项目"接口；旧线程能否迁移（MK-42c）。
- 跨机 `claude --resume` 的实际表现；转录格式随版本变化的兼容性。
- Mac 上 Claude Desktop / Codex Desktop / WorkBuddy 的数据目录。
- WorkBuddy 的加载机制与 `settings.json` 内部结构（MK-14）。
- Codex Desktop 与 CC Switch 版本的获取方式（MK-20）。
- zip 的 `.partial` + `os.rename` 在 FAT/exFAT 的 U 盘上的行为（MK-13 完成后需在真实 U 盘上实测一次）。
- Windows 客户端版默认的执行策略会拒绝运行 `.ps1`（据微软文档，未实测）：新手入口因此不走 PowerShell 脚本。`.cmd` → `scripts/start.py` 这条路径须在**未改过策略**的机器上实测（MK-28、MK-44）。
- `cmd.exe` 与 Windows Terminal 里中文显示是否正常、是否需要 `chcp 65001`（MK-28）。
- 安装路径含空格或中文时 `.cmd` 的行为（`%~dp0` 在非中文系统代码页下可能出错）（MK-28）。
- 未装 Python 时，应用商店的 `python.exe` 占位程序会弹出商店窗口；`py -3` 与 `python` 的探测顺序（MK-28）。
- 从网络下载的 `.cmd`、`.command` 会被 Windows SmartScreen／macOS 拦截，新手看不看得懂、能不能放行（MK-44 观察；放行步骤按实机所见写进 `docs/quickstart.md`）。
- macOS：`.command` 需要可执行位（`ai-config.command` 在 git 里目前是 100644）、首次打开的"无法验证开发者"提示、拖进终端的路径转义（MK-28、MK-61）。
- 终端问答本身对完全不懂的人是不是障碍（MK-44 结论决定是否做 MK-75）；新电脑上安装 Python 并联网安装 tomlkit 是不是主要障碍（决定是否做 MK-74）。

**已知风险**：
- 应用运行时会改写自己的状态文件：还原必须在应用关闭时进行（MK-31 强制）。
- 版本差异：Claude Code 转录的内部格式随版本变化；预检会比较软件版本并警告。
- CC Switch 用符号链接接管 `~/.claude/skills`：本工具不跟随、不复制其内容。
- 信任是安全决定：Codex 对已信任项目会加载项目内的配置、hooks、rules；只对核心项目且文件夹存在者恢复，并先让负责人确认。
- 路径写法不一致（`/` 与 `\`、大小写）会造成重复或漏匹配：一律先规范化再比较。
- 规则文件本身会被 agent 当作受信指令执行：bundle 来源只能是负责人自己的备份；`preflight` 对规则内容变化会显示差异。
- 新手向导只给安全默认（不覆盖、不忽略运行中的应用），可能让新手觉得"没恢复成功"：结果页必须逐条写清冲突项另存在哪里、怎么对照处理。
- 向导文案与真实新手理解之间的差距，开发者自己发现不了，只能靠 MK-44。

---

## 12. 附录 E：官方文档出处（均于 2026-10-01/02 读取，版本会变，执行前请复核）

- Claude Code：记忆 https://code.claude.com/docs/en/memory ；会话 https://code.claude.com/docs/en/sessions ；权限与工作区信任 https://code.claude.com/docs/en/permissions ；设置 https://code.claude.com/docs/en/settings ；目录说明 https://code.claude.com/docs/en/claude-directory ；hooks https://code.claude.com/docs/en/hooks
- Codex：AGENTS.md 指南 https://developers.openai.com/codex/guides/agents-md ；高级配置（含项目信任） https://developers.openai.com/codex/config-advanced ；CLI 功能（`codex resume`） https://developers.openai.com/codex/cli/features
- CC Switch：README https://github.com/farion1231/cc-switch
