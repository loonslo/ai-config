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

`--publish` 只提交并推送 `common/`、`codex/`、`claude/`；推送失败时本机提交保留，远端分叉时停止并报 E2002，不会强制覆盖。不带 `--apply` 时它只列出待发布的文件，不写任何东西。

## 目录结构

### 配置源

```text
common/                          公共规则（跨工具规范的唯一源文件）
codex/config.toml                共享模板
claude/settings.shared.json      共享模板
schemas/                         JSON Schema 定义
templates/                       新项目模板
```

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
| 默认预览，`--apply` 才写 | `setup`、`sync`、`diff`、`undo`、`memory-setup`、`rules`、`config`、`memory`、`inventory` | 不写文件 |
| 需要 `--apply` 且会发布 | `finish` | 写入并推送 |

### 传输允许范围

`git-memory.py push` 只允许 `claude/` 和 `codex/` 下的 Markdown 进入共享记忆仓库。其他路径会被拒绝，不会因为“顺手”而带上无关文件。

## 配置版本相等判断

`finish --apply` 要求配置源工作区干净、当前 commit 已在其远端分支确认，并保存共享规则、受管字段选择和模板摘要。

`start` 会核对这些配置事实。**Windows 和 macOS 的本机路径不参与相等判断**——三台设备路径本来就不同，那不是配置不一致。

`additional_sources` 可以显式登记自定义或子代理来源。未登记但在已知工具根目录发现的候选会显示为 `pending_mapping`；如果扫描发现凭据、不可读或不支持的内容，状态会**保持为阻断态**，不会被降级成“确认映射即可启用”。

## 工具链接

- [Claude 自动记忆](https://code.claude.com/docs/en/memory)
- [Codex 记忆](https://learn.chatgpt.com/zh-Hans/docs/customization/memories)
