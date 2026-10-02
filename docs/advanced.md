# 高级说明

日常使用只需要 [入门详解](getting-started.md)，不需要读这一页。

## 共享字段清单

只有下面这些字段参与跨设备一致性判断。其余设置始终保持本机值。

### 公共规则（总是受管）

来自 `common/` 下的 7 个主题，写入工具规则文件的受管区块：

```text
instructions  principles  engineering  python  langgraph  rag  security
```

区块标记：

```markdown
<!-- ai-config:begin -->
（共享内容）
<!-- ai-config:end -->
```

框外内容完全属于你，脚本不动它，也不会因为它变化而报漂移。

### Codex（需要显式选中）

| 字段 | 含义 |
| --- | --- |
| `approval_policy` | 命令审批策略 |
| `sandbox_mode` | 沙箱模式 |
| `web_search` | 网页搜索 |
| `model_reasoning_effort` | 推理强度 |
| `project_doc_max_bytes` | 项目说明文档上限 |

模板：`codex/config.toml`。只更新选中的键，其他键和注释原样保留。

### Claude（需要显式选中）

| 字段 | 含义 |
| --- | --- |
| `autoMemoryEnabled` | 自动记忆开关 |

模板：`claude/settings.shared.json`。同样只更新选中的键。

### 永不共享

凭据、登录状态、会话、Cookie、`mcp_servers`、`model_provider`、`providers`、`env` 等字段被硬性拒绝。即使配置文件里写了这些名字，`validate()` 也会直接报错，不会降级成“就共享一次”。

未经验证的工具参数也不默认管理：`codex_keys` / `claude_keys` 只接受上面列出的名字，写别的会报错而不是静默忽略。

### 本机覆盖

`codex_overrides` / `claude_overrides` 保存只属于这台设备的标量值，不进入共享模板，也不会被提交。`diff --choice local` 写入的是 `state_dir/local_overrides.json`。

两处覆盖会一起生效，且**覆盖值优先于共享模板**：`local_overrides.json` 是最新的一次明确选择，因此优先于 `device.json` 里的 `codex_overrides` / `claude_overrides`。

覆盖值参与三件事，缺一不可：

1. **实际写入** — `sync` 生成目标文件时用覆盖值，而不是共享值；
2. **差异比较** — `diff` 把它显示为“来自本机覆盖”的“本机值”；
3. **应用核验** — 期望值包含覆盖值，所以下一次同步不会把覆盖当成漂移，也不会把它改回共享值。

因此选择“仅此设备”之后，后续同步会保持该值；想改回共享值，用 `diff --choice restore`。

### 共享修改的发布

`--choice share` 只完成**本机保存**：它把值写进本机配置源副本的共享模板（`codex/config.toml`、`claude/settings.shared.json`）或提示你合并进 `common/`。要让其他设备拿到，必须再运行：

```text
.\ai-config.ps1 sync --publish --apply
```

`--publish` 只提交并推送 `common/`、`codex/`、`claude/` 和 `agents.toml`；推送失败时本机提交保留，远端分叉时停止并报 E2002，不会强制覆盖。不带 `--apply` 时它只列出待发布的文件，不写任何东西。

## 目录结构

### 配置源

```text
common/                          公共规则（跨工具规范的唯一源文件）
common/imported.md               migrate 采纳的原有规则（采纳后才出现），保留原文与来源
codex/config.toml                共享模板
claude/settings.shared.json      共享模板
agents.toml                      可选：各 agent 接收哪些规则主题
schemas/                         JSON Schema 定义
templates/                       新项目模板；templates/store/ 是独立配置库的起步模板
```

配置库默认保存在用户数据目录 `~/.ai-sync/store`，与程序安装目录分开。`setup --store [目录]` 可指定另一处；不指定目录时也使用这个默认位置。首次创建的是不含 Git 的普通目录，离线即可读取和应用；明确提供 `--remote` 才会克隆 Git 配置源并要求 Git。目录已存在但不是配置库时停止，不会接管。

### 本机状态（不同步）

```text
state_dir/
  applied.json            最近成功应用的版本与目标摘要
  local_overrides.json    仅本机的字段覆盖（下次同步实际生效）
  <tool>-rules.json       上次写入的规则区块哈希
  <tool>-rules-accept-shared.json  一次性“恢复共享规则”意图（成功应用后才会被清除）
  rules-share/            `--choice share` 暂存的本机规则区块，供合并进 common/
  backups/<op-id>/        每次写入前的文件备份
  transactions/           事务日志
  inventory/              来源盘点报告
  scans/                  scan --apply 保存的盘点报告
  migration/              migrate 的决定（keep / 不登记）与迁入前原件
  load_checks.json        verify-load 的核验结果（版本、是否通过、时间）
  created_dirs.json       ai-config 为独占文件新建的目录，detach 只删除这些
```

`state_dir` 与 `memory_repo` 不能互相嵌套。

### 共享记忆仓库（可选，在配置源之外）

```text
memory_repo/
  registry/projects.json
  objects/<sha256>.md                    不可变内容物
  snapshots/<device>/<uuid>.json         版本化快照清单
  heads/<device>/<scope>.json            各设备各范围的当前头
  integrated/<project>/<branch-id>/MEMORY.md
  handoffs/<project>/<uuid>.json|md
```

快照先写不可变内容物，再写带 `schema_version`、父快照、来源状态、文件哈希、删除记录和 manifest 哈希的清单。

**关于父版本基线**：`start` 使用交接快照**自身的父版本**作为三方合并基线，而不是简单取“上一个快照”。本机新增内容会保留，修改/删除冲突会停止。

## 写入安全

每次配置写入都经过同一套保护：

1. **计划哈希与来源重验** — 预览时记录来源树哈希，真正写入前重新核对；不一致就停止。
2. **操作系统级锁** — Windows 用 `msvcrt.locking`，Unix 用 `fcntl.flock`，锁对象是 `sync.guard` 这个永久 inode。同一进程内不会重复加锁（那会自锁）。
3. **可恢复事务** — 状态依次为 `PREPARED` → `APPLYING` → `COMMITTED`；异常时 `ROLLED_OUT`，进程被中断则留下 `INTERRUPTED` 或 `ROLLBACK_REQUIRED`。
4. **备份** — 每个操作独立目录，只留在本机。
5. **敏感信息扫描** — 启发式检测；命中时停止且不输出匹配内容。
6. **非强制 Git 传输** — 只允许快进，从不 `push --force`。

## 设备回执

配置源里有一个专用分支 `device-receipts`，每台设备一个文件。

- 写入和读取都在**隔离的临时工作区**里做，不切换你的工作分支。
- 回执分支的更新**不会**触发配置重新应用。
- 内容只包含：设备 ID、受管范围、内容摘要、已验证的应用版本、上报时间。
- **不含真实路径和敏感值**，写入前会做键级检查。
- 并发前进时自动重试，不强制推送。
- 上报失败时，本机已应用状态仍然保留，另报 E5001 警告。

因为回执是上次上报的快照，`status` 对离线设备只说“X 最近报告于某时刻”，不会标成在线或实时一致。

## 状态文档

`schemas/config-state.schema.json` 定义结构，`sync_core/status.py` 负责生成与校验。

- 版本不匹配时**明确拒绝**，不猜测兼容。
- 能力分为 `config`、`memory`、`handoff` 三类，各自独立报告，不用单一 `ready` 概括。
- 状态词：`not_configured`、`pending_sync`、`applied`、`local_modified`、`conflict`、`offline`、`apply_failed`、`restart_required`。
- 真实路径和实际值只存本机；共享回执另行裁剪。

## 兼容入口

- `scripts/sync.py` 的所有原有命令（`quick`、`rules`、`config`、`memory`、`finish`、`start`、`restore`、`doctor`、`inventory`）保持可用，行为不变。
- `scripts/link-global.ps1` 的 Preview / Apply 仍可用，现在是 Python 包装，**不再创建符号链接**。
- 已存在的符号链接需要先人工迁移成普通文件；脚本会拒绝跟随链接写入。

### 原命令与预览语义

原命令的 `--apply` 语义没有变化，但**不是所有新命令都默认“只预览”**——这个说法只对写入类命令成立。准确地说：

| 类别 | 命令 | 行为 |
| --- | --- | --- |
| 纯只读 | `status`、`project`、`doctor`（无 `--recover`） | 永远不写 |
| 只读，`--apply` 只保存结果 | `scan`（保存盘点报告）、`verify-load`（记录核验结果） | 不改任何 agent 文件 |
| 默认预览，`--apply` 才写 | `setup`、`sync`、`diff`、`undo`、`memory-setup`、`rules`、`config`、`memory`、`inventory`、`migrate`、`detach`、`declare` | 不写文件 |
| 需要 `--apply` 且会发布 | `finish` | 写入并推送 |

### 传输允许范围

`git-memory.py push` 只允许 `claude/` 和 `codex/` 下的 Markdown 进入共享记忆仓库。其他路径会被拒绝，不会因为“顺手”而带上无关文件。

## 配置版本相等判断

`finish --apply` 要求配置源工作区干净、当前 commit 已在其远端分支确认，并保存共享规则、受管字段选择和模板摘要。

`start` 会核对这些配置事实。**Windows 和 macOS 的本机路径不参与相等判断**——三台设备路径本来就不同，那不是配置不一致。

`additional_sources` 可以显式登记自定义或子代理来源。未登记但在已知工具根目录发现的候选会显示为 `pending_mapping`；如果扫描发现凭据、不可读或不支持的内容，状态会**保持为阻断态**，不会被降级成“确认映射即可启用”。

## 多 agent 接管

### 适配器注册表

所有 agent 的知识集中在 `sync_core/agents.py`：各平台的根目录候选、根目录环境变量、唯一允许写入的规则入口、默认规则主题、受保护与运行时文件模式。档案只是数据，不从任何用户文件加载代码。规划、写入、核验、盘点和状态报告都读同一份档案，所以新增一个 agent 只需要：写一份档案、准备一套沙箱夹具、通过 `tests/test_agent_contract.py` 的契约测试。

| 级别 | 含义 | 当前覆盖 |
| --- | --- | --- |
| L0 识别 | 只报告存在与位置，不写入 | Kiro、opencode、Gemini CLI、GitHub Copilot CLI、Kimi Code、Cursor、豆包桌面版；管理类工具 CC Switch |
| L1 规则接管 | 只写档案声明的那一个规则入口 | Codex、Claude Code、CodeBuddy、WorkBuddy、TRAE、通用声明 |
| L2 设置字段 | 白名单里的标量字段 | Codex、Claude Code |
| L3 | skills、MCP、记忆 | 暂不写入（skills 只盘点） |

Codex 和 Claude 仍使用 device.json 顶层的 `codex`/`claude` 字段；其他 agent 登记在可选字段 `agents` 下（`migrate`、`setup` 或 `declare` 会替你写，不需要手改）：

```json
"agents": {
  "workbuddy": {"root": "C:/Users/me/.workbuddy"},
  "kiro": {"profile": "generic", "root": "C:/Users/me/.kiro", "rules": {"mode": "owned_file", "path": "steering/ai-config.md"}}
}
```

### 两种写入方式

- **受管区块**：在 agent 的规则文件里维护 `<!-- ai-config:begin/end -->` 区块，区块外的内容归你。
- **独占文件**：整个文件只含受管区块，归 ai-config 所有；同名文件如果不是 ai-config 创建的，同步会停止并报 E3004，不会接管。区块旁边被加了内容，会像受管区块被手改一样需要你用 `diff` 决定。

只在 agent 自己的目录已经存在时才写入，不会替你创建 agent 的根目录；TRAE 的规则入口按本机实际形态决定（`user_rules/` 目录用独占文件，`user_rules` 或 `user_rules.md` 文件用受管区块，都没有就提示 E1003）。

### 规则主题

编程类 agent 默认接收全部 7 个主题，WorkBuddy 默认只接收 `instructions`、`principles`、`security`。优先级：device.json 里的 `agents.<id>.topics` > 配置库 `agents.toml` 里的实例或 agent 类型 > 内置默认。`agents.toml` 写错时同步会停止，而不是悄悄发错规则：

```toml
[workbuddy]
topics = ["instructions", "principles", "security"]
```

### 版本戳与加载核验

每个渲染出来的规则区块都带一行 `ai-config 规则版本：<8 位摘要>`，摘要只由规则内容计算，因此同一配置库、同一主题组合在所有设备上一致。`verify-load` 让你在 agent 的新会话里问这个版本号：摘要猜不出来，答对即证明该会话读到了规则（挑战-应答，而不是模型自述）。规则一变，旧的核验结果显示为“已过期”。回执只携带“是否已核验”这个布尔值。

### 迁入

`migrate` 只比较各 agent 规则文件里**受管区块以外**的内容，以 Markdown 标题切分成章节，逐行规范化（NFC、换行、空白、列表与标题标记、句末标点）后与配置库比对：

- 每一行都已在配置库的章节是**完全重复**，默认移除（先备份）；
- 含独有行的章节必须逐项决定：`adopt` 把独有行按原文、带来源追加到 `common/imported.md` 并从原文件移除；`keep` 保留并不再提示；`remove` 移除；`skip` 暂不处理；
- 同一条规则抄在多个 agent 里会被识别为一条，采纳一次后其他副本变成重复；
- 命中凭据规则的文件整份跳过，不输出内容；
- 全部写入走同一套事务，`undo` 可撤销；首次改动的原文件另存一份原件，供 `detach --restore-original` 使用。

### 退出接管

`detach --agent <id>` 移除 ai-config 为该 agent 写入的区块或独占文件（撤销同步时追加的空行）、删除 ai-config 为它新建且已空的目录、取消登记。加 `--restore-original` 时，迁入前的原件会放回原处，前提是迁入之后你没有再改过这个文件；改过的文件会被跳过并报告冲突。

### 与管理类工具共存

CC Switch 这类工具会接管 Claude/Codex 的提供商设置（例如 `settings.json` 的 `env`，里面可能有 API 令牌）和 skills 目录链接。ai-config 不共享、不读取这些字段，也不跟随链接写入；`scan` 会把被链接接管的 skills 目录标成“由 CC Switch 管理”。两边同时写同一个文件时，写入前的哈希重验会让本次同步停止，而不是覆盖对方。

## 工具链接

- [Claude 自动记忆](https://code.claude.com/docs/en/memory)
- [CodeBuddy 记忆与用户规则](https://www.codebuddy.ai/docs/zh/cli/memory)
- [TRAE 规则](https://docs.trae.ai/ide/rules?_lang=en)
- [Codex 记忆](https://learn.chatgpt.com/zh-Hans/docs/customization/memories)

## 桌面扩展与服务器（2026-10-01）

扩展采集严格显式选择；配置库 portable/ 下按 skills/mcp/memory/handoffs 存储，包仍采用 v1 内容对象。导入复用事务，不复制运行目录。加密协议与 head 并发规则见 [服务器架构](server-architecture.md)，构建和验收边界见 [本轮记录](desktop-local-implementation.md)。Codex 仍是参考快照；MCP 保存不代表已连接。
