# 同步分类 · 接口契约（设计稿）

维护日期：2026-10-09　·　状态：**部分已实现。** 分类、现有来源覆盖、隐私处理、v2、新增 A/B 及账号技能/系统变量采集、技能来源与批准链接已接入；覆盖联动补验、完整分组/历史与真机验收仍待完成。实际范围与未验收项见 [执行记录](machine-sync-execution.md)。下面的签名是契约：落地时命名可以调整，但语义与兼容规则不得放宽，改动须同步修改本文与 [分类规范](machine-sync-classification.md)。配套：[变更方案](machine-sync-plan.md)。

## 0. 总则

- **只加不改**：`sync_core/machine` 现有函数新增参数一律带默认值；现有测试保持通过。
- **依赖方向**：沿用旧任务书 §4.4 的禁止项——`sync_core/machine/**` 不 import `sync_core.package`、`sync_core.cloud`、`sync_core.application`；`application/machine_protocol.py` 只做适配。
- **词表**：性质字母（A–H）、规则 ID、`nature`、`provenance` 等只出现在文档、代码、`--json` 与日志；默认界面使用大白话（旧任务书 §5.7 词表，禁用词扫描见 `guided.py:26`）。
- **隐私**：任何接口都不得返回或记录命中的密钥值与邮箱值，只返回类别、行号、计数。偏移量仅供脱敏内部使用。
- **错误码**：新增 E7500–E7599（现用 E7101–E7105、E7201–E7203、E7301、E7404、E7420、E7421），见 §14。

## 1. 规则表（`sync_core/machine/catalog.py`）

2026-10-09 用户新要求覆盖旧 Git 契约：完全不读取 Git 信息，助手文件按白名单携带。备份、预检、恢复、核验、撤销均不调用 Git、不枚举 `.git` 内部内容；不读取仓库根、索引、远端、HEAD、脏状态、配置、凭据或版本。新包不生成 git_root/git_root_id/git_commit 或 git_unavailable；旧包的路径字段仅兼容解释，不查询本机 Git。Git 元数据/配置/忽略文件永不携带，排除大小为 null，不统计其内部大小。

```python
Nature = Literal["A", "B", "C", "D", "E", "H", "F", "U"] # F 只登记边界，不扫描子树；U 为未定性/组合策略
Action = Literal["carry", "fields", "record", "never", "opt_in"]
Group  = Literal["rules", "memory", "skills_own", "skills_third", "approvals", "settings", "history"]

@dataclass(frozen=True)
class CatalogItem:                  # 现有字段不变
    agent: str; instance: str; kind: str; tier: int; mode: str; pattern: str; restore: str
    status: str = "approved"; scope: str = "agent"
    # 新增，均有默认值
    rule_id: str = ""               # 分类规范里的 ID，如 "CX-02"；空串只允许出现在旧测试夹具
    nature: str = ""                # Nature
    action: str = ""                # Action
    group: str = ""                 # Group，决定界面勾选项
    root: str = ""                  # SourceRoot.id；空串＝沿用 agent 根
    text_only: bool = True          # False：允许非文本文件（skills）
    opt_in: bool = False            # True：默认不选（H 类）
    patterns: tuple[str, ...] = ()  # 同一 ID 的补充路径模式，避免重复 ID
    field_keys: tuple[str, ...] = () # mode="field" 时按点分隔键名匹配
    policy_only: bool = False      # 边界/通用策略只登记，不成为文件白名单

@dataclass(frozen=True)
class DenyRule:                     # D、E 的显式拒绝，带原因
    rule_id: str
    root: str
    pattern: str                    # 与 CatalogItem.matches 同一套 glob（含 **）
    nature: Literal["D", "E"]
    reason: str                     # "credential" 或 "runtime"
    patterns: tuple[str, ...] = ()
    field_keys: tuple[str, ...] = () # 非空时为字段拒绝规则，不拒绝整个设置文件

@dataclass(frozen=True)
class Decision:
    rule_id: str | None             # None＝未定性
    nature: str                     # "A".."H"，或 "U"（未定性）
    action: str                     # Action，或 "unclassified"
    reason: str = ""

def classify(root: str, relative: str, *, scope: str = "agent", origin: str | None = None) -> Decision: ...
def classify_field(root: str, source: str, key: str) -> Decision: ... # 不接收、不返回值
def allowed_item(...)               # 现有函数保持；内部复用 classify，行为对既有夹具等价
def denied_path(relative_path: str) -> bool   # 现有；补：任意层级的 *_migration.json

CATALOG: tuple[CatalogItem, ...]
DENY: tuple[DenyRule, ...]
```

规则：

1. **优先级**：`DenyRule` ＞ `CatalogItem` ＞ 未定性。
2. 同一 `(root, relative)` 命中多条 `CatalogItem` 时取更具体的 pattern；仍并列则规则表自检测试失败。
3. `rule_id` 唯一，且与分类规范第 4 节的 ID 一一对应（§13 的 T2）。
4. skill 路径以**子目录为单位**：先 `resolve_skill()`（§5）得到 `origin`，再逐文件 `classify(..., origin=origin)`；`origin` 为 `user` 或 `unknown` 时落 SK-01，`third_party` 时落 SK-02，`vendor_builtin` 时落 SK-03；SK-05 命中的文件落 E。
5. `tier` 由规则推导：A、B 且自动或确认恢复＝1；信任类手动恢复＝2；D、E＝3。

实现说明（2026-10-09）：72 个稳定 ID 各登记一次。`SK-04` 是同名副本组合策略，性质记 U，仅记录；F 仅作边界；这两类不产出采集候选。`LEGACY_CATALOG` 保留既有采集选择，`allowed_item` 在拒绝检查后通过 `classify` 检查，再返回旧白名单项；目标规则登记不等于新路径已采集。设置文件整体判定使用第一条对应字段规则作为代表，逐键判定用 `classify_field`。WB 规则使用一个稳定 ID 覆盖两个逻辑实例。来源解析、非密钥值与设备项的进一步过滤由后续采集任务实现。

## 2. 来源根与批准链接

```python
@dataclass(frozen=True)
class ApprovedLink:
    link: str                       # 相对根的链接位置，如 "skills"
    targets: tuple[str, ...]        # 允许的目标，如 ("~/.cc-switch/skills", "~/.agents/skills")

@dataclass(frozen=True)
class SourceRoot:
    id: str
    agent: str                      # claude、codex、workbuddy、workbuddy-ai、shared、system
    instance: str                   # main、desktop 等逻辑实例
    resolve: Callable[[Path, Mapping[str, str]], Path | None]   # (home, environ) → 物理目录；不存在返回 None
    links: tuple[ApprovedLink, ...] = ()
```

| id | agent / instance | 物理位置 | 说明 |
|---|---|---|---|
| `claude_home` | claude / main | `CLAUDE_CONFIG_DIR` 或 `~/.claude` | `links`: `skills` → CC Switch 或 `~/.agents` |
| `claude_json` | claude / main | `~/.claude.json` | 只取字段；沿用 G2 |
| `claude_desktop` | claude / desktop | `%APPDATA%\Claude`；备选 `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude` | 取第一个存在且含 `local-agent-mode-sessions` 的 |
| `codex_home` | codex / main | `CODEX_HOME` 或 `~/.codex` | |
| `agents_home` | shared / main | `~/.agents` | 新增助手 id `shared`，界面名「通用技能」 |
| `workbuddy`、`workbuddy_ai` | workbuddy[-ai] / 同名 | 配置的 `instances` 或 `~/.workbuddy[-ai]` | |
| `project:<pid>` | 随所属助手 | 所选项目文件夹 | |
| `user_env` | system / main | 用户级环境变量（Windows） | 名称与值；值只用于判定 |

**`resolve_link(root, link) -> Path`**：

- `root/link` 不是链接或联接点：返回其本身。
- 是链接：`realpath` 必须落在 `targets` 内、位于用户主目录下，目标自身不是链接，目录内不含链接；否则抛 `UnsafeSource`，采集器记 E7501 并跳过该子树。
- 读取边界＝解析后的目标目录；逻辑路径仍记为 `<agent>:<instance>/<link>/…`。
- 恢复端不创建链接，也不穿过链接写入（沿用 `preflight.no_links`）。

## 3. 遍历与覆盖账本

```python
@dataclass
class Ledger:
    def seen(self, root: str, relative: str, size: int, decision: Decision) -> None: ...
    def pruned(self, root: str, relative: str, rule_id: str, entries: int) -> None: ...  # 整目录被规则剪掉，不下钻，只记直接子项数
    def field(self, source: str, key: str, decision: Decision) -> None: ...              # settings、config、.claude.json 的顶层键
    def report(self) -> dict: ...                                                        # → reports/coverage.json

@dataclass(frozen=True)
class Candidate:
    root: SourceRoot; path: Path; relative: str; size: int; decision: Decision

def walk_root(root: SourceRoot, *, home: Path, environ: Mapping[str, str],
              excluded: Callable[[Path], bool], ledger: Ledger, limits: Limits) -> Iterator[Candidate]: ...
```

`walk_root` 只对 `action` 为 `carry`、`fields`、`opt_in` 且所属分组已选的文件产出 `Candidate`，其余只入账本。

**不变量**

- **L1**：每个被访问的文件在账本里恰有一次 `seen`。
- **L2**：被剪枝的目录只出现在 `pruned`，不递归（避免遍历 `node_modules`、`.tmp`）。
- **L3**：D 类路径只做目录项枚举与 `stat`，**不 open**；哨兵测试断言零读取。
- **L4**：账本计数加剪枝子项数＝目录枚举总数。

**`reports/coverage.json`**

```json
{
  "schema": 1,
  "roots": [{
    "id": "claude_home", "present": true, "files": 120, "bytes": 912345,
    "by_nature": {"A": {"files": 3, "bytes": 8000, "carried": 3}, "B": {"files": 1},
                  "C": {"files": 40}, "D": {"files": 2}, "E": {"files": 70},
                  "H": {"files": 20, "carried": 0}, "U": {"files": 1}},
    "pruned": [{"path": "plugins/cache", "rule_id": "CC-16", "entries": 12}],
    "unclassified": {"count": 1, "samples": ["some/new/file.ext"]}
  }],
  "fields": [{"source": "claude:main/settings.json",
              "carried": ["language", "effortLevel"], "confirm": ["model"],
              "recorded": ["enabledPlugins"], "never": ["…"], "unclassified": []}],
  "totals": {"files": 0, "carried": 0, "unclassified": 0}
}
```

`samples` 最多 20 条，只含相对路径。`reports/summary.md` 在有未定性文件时增加一节「未定性文件」。

阶段 1 已实现边界：`coverage.py` 的 `walk_root` 只枚举与 stat，不 open 内容；默认观察已选择的既有助手根、Claude 登记文件、所选项目配置区域。桌面账号 skill、通用 skill、批准链接和系统环境变量在对应 SC 任务接入前不纳入当前覆盖范围。字段名从采集器已经解析的设置与登记文件取得，不额外读一遍源文件；`field_mode: classification_only` 表示字段列表是目标定性，不能据此宣称已经带上这些字段。实际文件携带数由已生成条目核对。

账本补充：每根与 totals 带 `complete`，链接、权限错误、扫描上限使其为 false；未定性计数为 0 不代表完整覆盖。`pruned_entries` 是被规则剪掉目录的直接子项数，F/排除范围/链接边界记 0 且不进入子树。L4 的枚举总数按已访问文件加剪枝直接子项计，不包含遍历过程中的目录容器；不能用此值推断被剪掉子树中的文件总量。路径/字段名含邮箱或密钥特征时仅显示名称已隐藏。

## 4. 隐私门禁与脱敏（`sync_core/machine/privacy.py`）

```python
SecretKind = Literal["token", "private_key", "bearer", "jwt", "url_userinfo", "kv_secret", "env_assign"]
Confidence = Literal["high", "heuristic"]    # 前五类为 high；kv_secret、env_assign 为 heuristic

@dataclass(frozen=True)
class SecretHit:
    kind: SecretKind; confidence: Confidence
    line: int; start: int; end: int          # 偏移仅供脱敏使用，不得出现在任何输出

def secret_hits(data: bytes | str) -> list[SecretHit]
def redact(data: bytes, hits: Sequence[SecretHit], *, only: Confidence | None = None) -> tuple[bytes, int]
def personal_text(value) -> bool             # 保留：仅用于「不回显」的输出卫生，不得再作备份或恢复门禁
def private_text(value) -> bool              # 改为 bool(secret_hits(value))；邮箱不再命中
def private_metadata(value) -> bool          # 同上，作用于 manifest 与元数据
```

专家 CLI 的公开报告与桌面协议同样使用 `public_value` 清理展示副本。JSON 在序列化前递归清理，保留报告结构；文本输出清理展示字符串。邮箱可保留在同步正文中，专家批准的原样凭据也不得通过公开报告回显。展示清理不改变包内正文、实际路径、映射或恢复选择；最小 v2 CLI 生命周期的验收范围见执行记录。

**脱敏规则**

- 占位符为 `<REDACTED>`；引号内的值只替换引号里面的部分，保留引号与行结构。
- 脱敏后须仍能被原格式解析：JSON、TOML 文件脱敏后用原解析器读一遍，失败则改为整份跳过并记 `skipped_by_policy`。
- 非文本文件不扫描（标 `nontext`）。

**门禁位置**

| 位置 | 现在 | 之后 |
|---|---|---|
| `collect_tier1._add_whole`（138 行）、`_fields`（214 行） | 邮箱或密钥命中即整份丢弃 | 仅 `secret_hits`；按策略脱敏或跳过 |
| `collect_workbuddy._add`（83 行） | `private_text` 命中即丢弃 | 同上 |
| `collect_projects`（246 行，`settings.local.json`） | `private_text` 命中即丢弃 | 同上 |
| `BundleWriter.check_privacy`（`bundle.py:176`） | 对全部内容和元数据重扫 | 内容：校验已处理标记（无命中，或条目带 `redacted:*`），不再全文重扫；元数据：`secret_hits` |
| `preflight`（`preflight.py:270`） | 邮箱或密钥命中即拒绝恢复 | 仅 `secret_hits`（脱敏后的占位符不命中） |

**策略表**（按 `origin` 与置信度；`origin` 以来源证据 `exact` 或 `derived` 为准，`guess`、`unknown` 一律当 `user`）

| origin | high | heuristic |
|---|---|---|
| user、unknown | 脱敏 | 脱敏 |
| third_party | 脱敏 | 只提示，原样带上 |
| vendor_builtin | 不带内容 | — |

**命中后的流程**

```python
FlaggedPolicy = Literal["redact", "skip"]            # 全局策略，默认 "redact"

@dataclass(frozen=True)
class Flag:
    id: str                                          # "f0001"
    rule_id: str
    logical_path: str
    kinds: tuple[SecretKind, ...]
    lines: tuple[int, ...]
    confidence: Confidence
    action: Literal["redacted", "skipped", "kept_heuristic", "kept_override"] # 最后一项仅为显式专家覆盖
    redactions: int
```

- `reports/flagged.json`：`{"policy": "redact", "items": [Flag…]}`，不含任何值。
- 条目 `flags` 里写 `redacted:<N>`；`exclusions` 里只在 `skip` 策略下出现 `secret_hit`。
- 恢复：含 `redacted:*` 的条目核验状态为「需要人工确认」（原因 `redacted`），`todo.md` 列出文件与行号。
- 专家开关：`machine.config.json` 的 `allow_secret_hit_paths` 沿用，含义为「不脱敏、原样带上」。

## 5. 技能来源记录

```python
@dataclass(frozen=True)
class Source:
    kind: Literal["github", "git", "lockfile", "package_json", "account", "license_only", "unknown"]
    url: str | None                  # 去掉用户信息与查询串（沿用旧红线 4 的 URL 处理）
    ref: str | None                  # 新记录固定 null，不查询或提取提交版本；兼容旧包
    evidence: str                    # "skill-lock"、"git-remote+HEAD"、"manifest.creatorType"、"package.json"、"tmpl-sibling"、"license"
    confidence: Literal["exact", "derived", "guess"]

@dataclass(frozen=True)
class ExcludedItem:
    path: str; reason: Literal["build_artifact", "too_large", "path_too_long", "git_metadata_excluded"]; size: int | None

@dataclass(frozen=True)
class Reinstall:
    method: Literal["source", "lockfile", "manual"]
    hint: str                        # 给人看的一句话；工具不执行任何命令

@dataclass(frozen=True)
class Provenance:
    id: str                          # "s001"
    name: str
    holder: Literal["claude-global", "claude-project", "claude-desktop-account", "codex-global",
                    "agents-shared", "workbuddy", "workbuddy-ai", "workbuddy-project"]
    via: Literal["direct", "approved-link"]
    origin: Literal["user", "third_party", "vendor_builtin", "unknown"]
    source: Source | None
    derived_from: str | None         # 仅非 Git 的明确来源提示；不扫描 Git 派生关系
    carried: Literal["verbatim", "verbatim_without_artifacts", "partial", "record_only"]
    local_changes: str               # 新记录固定 "unknown"，不查询脏状态；兼容旧包
    files: int; bytes: int
    content_sha256: str              # 按相对路径排序的 (路径, sha256) 列表的摘要，恢复后用于核对
    skill_md_sha256: str | None
    excluded: tuple[ExcludedItem, ...]
    reinstall: Reinstall | None

def resolve_skill(skill_dir: Path, *, root: SourceRoot, hints: "ProvenanceHints") -> Provenance
```

`ProvenanceHints` 由调用方一次性构造：已解析的 `.skill-lock.json` 映射、Claude 桌面端 `manifest.json` 映射与非 Git 的明确模板提示。

**解析顺序**（命中即止，并写入 `evidence` 与 `confidence`）

1. **账号清单**：Claude 桌面端 `manifest.json` 的 `creatorType`——`user`→`user`；`anthropic`→`vendor_builtin`。
2. **Codex `.system/`** → `vendor_builtin`。
3. **`.skill-lock.json`**（`~/.agents`）：已登记→`third_party`（来源取其 `source`、`sourceUrl`，`exact`）；未登记→`user`。
4. **Git 步骤已取消**：不读 `.git`、远端、HEAD 或脏状态；只有 Git 元数据而无其它来源证据时记 `unknown`。
5. **自带元数据**：`package.json` 的仓库字段→`derived`；只有许可证文件、没有可用 URL→`license_only`（`guess`）。
6. **派生**：仅接受非 Git 的明确模板来源提示；不根据 `.git` 或其子目录推导。
7. **其余**→`unknown`；备份内的副本就是唯一来源，按 SK-01 处理并在报告里标「来源不明」。

**`reports/skills.json`**（另生成给人看的 `reports/skills.md`，只用大白话）

```json
{
  "schema": 1,
  "skills": [{
    "id": "s001", "name": "<名称>", "holder": "claude-global", "via": "approved-link",
    "origin": "third_party", "carried": "verbatim_without_artifacts",
    "source": {"kind": "lockfile", "url": "https://example.com/<owner>/<repo>", "ref": null,
               "evidence": "skill-lock", "confidence": "exact"},
    "local_changes": "unknown", "derived_from": null,
    "files": 1700, "bytes": 90000000, "content_sha256": "<hex>", "skill_md_sha256": "<hex>",
    "excluded": [{"path": "browse/dist/browse.exe", "reason": "build_artifact", "size": 98519552}],
    "reinstall": {"method": "source", "hint": "按来源说明重新安装或构建"}
  }],
  "copies": [{"name": "<名称>", "members": ["s010", "s022", "s031"],
              "relation": "diverged", "skill_md_sha256": ["<hex>", "<hex>", "<hex>"]}],
  "summary": {"total": 0, "own": 0, "third_party": 0, "vendor_builtin": 0, "unknown_source": 0, "diverged_copies": 0}
}
```

`copies` 把同名 skill 分组：全部副本都有 `SKILL.md` 哈希时，`relation` 为 `identical`（哈希全同）或 `diverged`（哈希不同）；有副本未读取正文或未携带、缺少哈希时为 `unverified`，不能推断内容不同。`summary.unverified_copies` 单独计数。

## 6. 备份入口（`sync_core/machine/backup.py`）

已有 `observe_coverage: bool = True`（开发比对开关，不对桌面用户暴露），关闭时用于核对采集出的文件条目和字节一致；flagged_policy 已接入引擎，groups/history 及相应桌面参数仍待接入。

```python
def prepare_backup(*, home, config, out, name="machine-bundle", agents=None, environ=None, os_name=None,
                   now=None, software=None, git_keys=None,
                   groups: frozenset[str] | None = None,      # None＝所有非 opt_in 分组
                   flagged_policy: FlaggedPolicy = "redact",
                   history: "HistoryOptions | None" = None) -> BackupPlan
```

- `AGENTS`（`backup.py:28`）增加 `shared`（可选择）；`system` 不是可选择的助手，其条目随分组 `settings` 一起选。
- `BackupPlan.preview()` 新增字段：

```json
{
  "by_group": {"rules": {"files": 3, "bytes": 15000}, "skills_third": {"files": 2100, "bytes": 99000000}},
  "flagged": {"policy": "redact", "count": 3,
              "items": [{"id": "f0001", "logical_path": "…", "kinds": ["token"], "lines": [12], "action": "redacted"}]},
  "skills": {"total": 52, "own": 12, "third_party": 35, "vendor_builtin": 15, "unknown_source": 1, "diverged_copies": 1},
  "coverage": {"unclassified": 0, "roots": 9},
  "oversize": [{"logical_path": "…", "size": 0, "reason": "too_large"}]
}
```

- `verify_sources_unchanged()` 覆盖所有读过的源文件，包括批准链接目标内的文件。
- 报告新增：`coverage.json`、`flagged.json`、`skills.json`、`skills.md`；`login-checklist.md` 只列密钥类变量名；`summary.md` 增加「第三方技能」「同名技能」「未定性文件」小节（有才显示）。

## 7. Bundle 清单 v2（`sync_core/machine/bundle.py`）

**顶层**

- `schema_version`：2。`TOP_KEYS` 不变，`limits` 不变（单文件 64 MiB、整包 512 MiB、20,000 个成员）。
- `_check_manifest` 接受 `{1, 2}`；其余校验不变。v1 包不得含 v2 专有字段或类型。

**条目新增字段**（均可选；缺省＝旧行为；不参与 `content_id`）

| 字段 | 类型 | 含义 |
|---|---|---|
| `rule_id` | 字符串，≤16 | 分类规范 ID |
| `nature` | `A`–`H` | 性质 |
| `group` | 分组 id | 界面分组 |
| `holder` | 字符串 | 技能所在位置，取值同 `Provenance.holder` |
| `provenance_id` | 字符串 | 指向 `reports/skills.json` 的 `id` |
| `conflict_group` | 字符串，≤128 | 恢复时按组选择覆盖或保留，如 `skill:<名称>` |
| `redactions` | 整数，≥0 | 脱敏处数（同时在 `flags` 写 `redacted:<N>`） |

**新增取值**

- `agent`：`shared`、`system`。`instance`：`claude` 下增加 `desktop`。
- `kind`：
  - `skills`：任意文件，`skills_text` 保留，读取时视为同义。
  - `approvals`：Codex `rules/**`。
  - `scripts`：自写脚本。
  - `plans`：Claude 计划文档。
  - `env_fields`：用户级环境变量。
  - `history_files`：历史记录。
  - `settings_fields` 扩展到更多来源文件，见 §8.1 的 `FIELD_SOURCES`。
- `restore`：增加 `export`。
- `exclusions[].reason`：增加 `build_artifact`、`path_too_long`、`skipped_by_policy`；沿用 `secret_hit`、`non_text`、`too_large`、`excluded_by_config`、`dead_path`。D、E 类的批量统计放在覆盖报告里，不进 `exclusions`。
- `flags`：增加 `redacted:<N>`、`artifacts_excluded:<N>`、`diverged_copy`。

**条目示例**

```json
{"id": "e0042", "agent": "claude", "instance": "main", "kind": "skills", "tier": 1, "mode": "file",
 "logical_path": "claude:main/skills/<名称>/SKILL.md",
 "archive_path": "files/claude/main/skills/<名称>/SKILL.md",
 "sha256": "<hex>", "size": 1234, "restore": "auto", "project_id": null, "flags": [],
 "rule_id": "SK-02", "nature": "C", "group": "skills_third", "holder": "claude-global",
 "provenance_id": "s007", "conflict_group": "skill:<名称>"}
```

**其它写入细节**

- 单个成员路径超过 240 字符时，不再让整个备份失败：该文件记 `path_too_long` 排除并告警 E7503。
- 归档路径约定：Claude 桌面端 skill 为 `files/claude/desktop/skills/<名称>/…`；通用技能为 `files/shared/main/…`；项目级 skill 为 `files/projects/<项目 id>/claude/.claude/skills/<名称>/…`。

2026-10-09 多账号实现细化：新账号技能采用 `files/claude/desktop/accounts/<a0001 别名>/skills/<名称>/…`，导出为报告目录 `account-skills/<别名>/<名称>.zip`，ZIP 顶层仍是技能目录；两层账号/组织真实标识不进入来源报告。旧单账号路径继续可读。别名只用于同一次备份区分账号，不承诺跨备份稳定映射；manifest 支持键值和列表结构，真实应用布局尚待只读验收。

**兼容矩阵**

| | 旧客户端（0.3.x） | 新客户端 |
|---|---|---|
| 读 v1 ZIP | 可以 | 可以 |
| 读 v2 ZIP | 校验阶段拒绝，不写任何文件 | 可以 |
| 新客户端写出 | — | 一律 v2 |

## 8. 恢复侧（`preflight.py`、`apply.py`、`verify.py`）

### 8.1 目标解析（`_destination` 扩展）

`_destination` 当前对未知助手或类型直接抛错（`preflight.py:190-191`）。扩展后：未知的抛 E7502；新类型按下表解析；归档前缀按条目的 `instance` 推导，不再假定为 `main`。

| agent、kind | 目标 | 边界 | 条件与说明 |
|---|---|---|---|
| claude、`skills`（全局） | `~/.claude/skills/<相对路径>` | Claude 根 | 目录若为链接→`link_blocked` |
| claude、`skills`（项目） | `<映射后项目>/.claude/skills/…` | 项目文件夹 | 项目不存在→`project_missing` |
| claude / desktop、`skills` | `<报告文件夹>/account-skills/<名称>.zip` | 报告文件夹 | `export`；ZIP 顶层为 skill 目录；不写应用目录 |
| claude、`plans` | `~/.claude/plans/…` | Claude 根 | |
| codex、`skills` | `~/.codex/skills/…` | Codex 根 | 拒绝 `.system/` |
| codex、`approvals` | `~/.codex/rules/…` | Codex 根 | |
| shared、`skills` | `~/.agents/skills/…`、`~/.agents/.skill-lock.json` | `~/.agents` | 允许创建该目录（它不是需要先启动一次的应用）；锁文件仅目标缺失时写 |
| workbuddy*、`scripts` | `~/.workbuddy[-ai]/scripts/…` | 实例根 | 手动恢复 |
| 项目级 `rules` | `<映射后项目>/AGENTS.md` 等 | 项目文件夹 | 目标已存在且不同→另存 `.from-bundle` |
| `settings_fields` | 按 `FIELD_SOURCES` | 见表 | 含 `env.*` 新字段，确认类 |
| system、`env_fields` | `<报告文件夹>/restore-env.ps1` 与 `env-vars.md` | 报告文件夹 | `export`；不写注册表 |
| `history_files` | 映射后的原位置 | 对应根 | 无法映射→`<报告文件夹>/history-unmapped/` |

```python
FIELD_SOURCES = {          # (agent, 来源文件) → 归档里的派生文件名
    ("claude", "settings.json"):              "settings.fields.json",
    ("codex",  "config.toml"):                "config.fields.json",
    ("claude", "claude_desktop_config.json"): "desktop-config.fields.json",
    ("claude", ".claude.json"):              "claude-json.fields.json",
    ("project", ".claude.json"):             "claude-json.fields.json", # 登记文件中的项目 MCP，按 project_id 分条
    ("project", ".mcp.json"):                 "mcp.fields.json",
}
```

`allowed_fields()` 对 Claude 增加 `env.<名称>` 键（名称不含密钥特征，且值通过 `secret_hits`），对 Codex 增加 `shell_environment_policy.set.<名称>`；均归入确认类。

CC-14 项目登记 MCP 的归档位置为 `files/projects/<project_id>/claude/claude-json.fields.json`，payload 只含该项目的 `mcpServers`，不包含原账号/路径键。目标为本机 `~/.claude.json` 的 `projects[映射后的项目路径]`；Windows 已有键按路径规范化后不区分大小写匹配并沿用原键。内部 `CheckItem.field_path` 为独立路径段元组，不把项目路径中的点当作字段分隔符。预检、合并、核验共用该层级，未映射项目跳过；必须确认安全设置，修改前仍检查目标指纹、保存原件并可撤销。其它项目、未知本机字段、登录字段和信任字段不会因 MCP 恢复而变化。

`security_list` 的每项增加可兼容的 `project: str | None` 和 `instance: str`，项目是映射后的本机工作文件夹，非项目项为 null。它们进入 `security_list_hash`，映射/归属变化后原确认失效；公开协议沿用 `public_value` 隐藏路径中的邮箱。界面区分全局/工作文件夹/桌面设置。多个条目作用于同一登记文件时按已批准字段累积合并，事务仅备份/写入该文件一次；每个条目的覆盖/保留决定和核验状态仍独立。

多个来源映射到同一目标字段时，相同值或互不重叠的字段允许合并；明确保留的条目不参与写入。实际获准恢复的两个值不同时，计划必须在写入前拒绝，不能按条目顺序决定胜出者，也不能先写入后才用核验发现前一项已被改写。身份为目标文件＋完整字段层级＋叶键；Windows 项目路径层级不区分大小写，JSON 叶键仍区分大小写。未选择覆盖的初始协议预览继续显示待选择；明确选择之后发现矛盾则返回固定中文错误、不发出 plan_id，要求改工作文件夹或保留一份。

MCP 的恢复白名单精确到 `mcpServers.<服务名>.url/command/args/type` 及合法非密钥 `env.<名称>`；`mcpServers` 子树不是任意键的授权，未知子键、设备键、URL 下嵌套对象和 headers 不带且不能由伪造包恢复。服务名含点的旧限制继续保留。字段账本仍标 `classification_only`，部分逐键分类与设备偏好边界继续按执行记录补验。

### 8.2 冲突

- 沿用现有语义：目标不存在则写入；内容相同则跳过；内容不同时由用户选择覆盖或保留，默认保留并另存 `.from-bundle`。
- `conflict_group`：界面可对一组一次选择，协议仍用 `conflict_choices`（以条目 id 为键）由界面按组展开。
- 同名 skill 位于不同 `holder` 时互不覆盖。

### 8.3 核验与撤销

- 文件类沿用 sha256 一致→通过（`verify.py:157`）。
- 含 `redacted:*`→「需要人工确认」，原因 `redacted`；`export` 类→「需要人工确认」，原因 `exported`，报告列出导出位置。
- skills 增加汇总：已写入 N 个、来源不明 M 个、需要重建 K 个（`excluded` 非空）。
- 撤销：写入助手根与项目内的文件沿用事务；导出到报告文件夹的文件不纳入撤销，并在记录里说明。

新增 `RESTORE_REASON_LABELS`（`guided.py:18`）：

| 代码 | 文案 |
|---|---|
| `redacted` | 里面的密钥已被隐藏，请重新填写 |
| `exported` | 已导出到恢复报告文件夹，请自行导入 |
| `needs_rebuild` | 缺少可重新生成的程序文件，请按来源重装 |
| `link_blocked` | 目标文件夹被链接接管，已跳过 |

## 9. 桌面协议（`application/machine_protocol.py`、`schemas/machine-desktop-rpc.schema.json`）

```python
PARAMS = {
    'machine_detect': set(),
    'machine_history': set(),
    'machine_backup': {'destination', 'agents', 'projects', 'groups', 'flagged_policy'},
    'machine_restore': {'bundle', 'agents', 'groups', 'root_map', 'confirm_security', 'confirm_trust',
                        'workbuddy_files', 'conflict_choices'},
    'machine_undo': {'operation_id'},
}
```

校验新增：`groups` 为唯一的字符串数组，取值属于分组集合；`flagged_policy` 为 `redact` 或 `skip`；`agents` 的枚举增加 `shared`。Schema 保持 `additionalProperties: false`，只加这些属性。

**`machine_detect` 结果**（旧字段含义不变）

```json
{
  "agents": [{"id": "claude", "name": "Claude", "installed": true, "root": "<路径>"},
             {"id": "shared", "name": "通用技能", "installed": true, "root": "<路径>"}],
  "projects": ["<已登记且存在的文件夹，默认全选>"],
  "groups": [
    {"id": "rules",        "name": "规则",                 "default": true,  "available": true},
    {"id": "memory",       "name": "记忆与笔记",           "default": true,  "available": true},
    {"id": "skills_own",   "name": "我写的技能与脚本",     "default": true,  "available": true},
    {"id": "skills_third", "name": "第三方技能（含来源）", "default": true,  "available": true},
    {"id": "approvals",    "name": "已批准的操作",         "default": true,  "available": true},
    {"id": "settings",     "name": "设置与信任",           "default": true,  "available": true},
    {"id": "history",      "name": "历史记录（体积较大）", "default": false, "available": true}
  ]
}
```

- `projects` 由 `known_folders()` 取得，过滤掉不存在的路径和 worktrees、scratch。**检测不统计体积**，保持快速；体积在检查备份时给出。
- `available`＝存在任何能产出该分组条目的根。

**分组与规则对应**

| 分组 | 规则 ID |
|---|---|
| `rules` | CC-01、CX-01、PJ-01 |
| `memory` | CC-03、CC-04、WB-01、WB-07 中的 memory |
| `skills_own` | CC-02、CD-01、WB-03，以及 SK-01 落到的 CC-05、CW-01、CX-04、AG-01、WB-02、WB-07 中的 skills、PJ-03、PJ-04 |
| `skills_third` | SK-02、AG-02 |
| `approvals` | CX-02、PJ-02 |
| `settings` | CC-06 至 CC-08、CC-11、CC-13、CC-14、CX-05 至 CX-09、CX-12、CD-03、PJ-05、SY-01 |
| `history` | CC-18、CX-14 |

**`machine_backup` 预检结果**：增加 §6 的字段；`can_apply` 含义不变。含密钥的文件不阻止确认（默认脱敏保留）。

**`machine_restore`**：`groups` 缺省＝备份里出现的、除 `history` 外的全部分组；预检结果增加 `bundle_groups`、`by_group`、`redacted_todo`（需要重新填写的文件数）、`exports`（`[{kind, name, target}]`）、`needs_rebuild`（数量）。

**进度**：新增 `stage: "scanning"`，附 `detail`（根 id），界面映射为「正在检查 Claude…」等大白话。

**单次有效的预览**机制不变：确认时重新采集并比较输入，变化即停止。

## 10. 界面约定（`desktop/src/MachineApp.tsx`、`RestoreReport.tsx`）

备份页顺序：

1. **选择助手**（沿用；有 `~/.agents` 时多一项「通用技能」）。
2. **选择备份内容**：按 `groups` 渲染勾选框，默认值取 `default`；历史记录默认不勾，旁注「体积较大，可能需要几分钟」；`available` 为否则禁用并标「（尚未找到）」。
3. **工作文件夹**：预填 `projects`，可逐个移除；「添加工作文件夹」保留。
4. **保存位置**（沿用）。

检查结果面板增加：

- 「含密钥的文件 N 个：已把密钥部分替换为占位符后保存」，旁边单选「整份跳过这些文件」；明细可展开（路径与行号）。
- 「第三方技能 N 个：来源已记录 M 个，来源不明 K 个（已原样保存）」。
- 「同名技能 N 组内容不同（均已保留）」。
- 「未定性文件 N 个（未备份）」，可展开。

恢复页：只列备份里出现的分组，历史默认不选；冲突按技能分组显示、可整组选择；结束后「接下来要做的事」增加：需要重新填写的文件、需要重建的程序、导出的账号 skill 位置、环境变量脚本位置。

文案遵守旧任务书 §5.7：不出现字母性质、规则 ID、provenance、manifest 等词。

## 11. 历史备份包（草案，SC-11 开工前细化）

流式实现的分段大小、集合关联、正文校验和发布/恢复边界见 [历史实施契约](machine-sync-history-contract.md)。该细化不代表桌面与恢复已接通，实际状态见执行记录。

- 容器仍是 ZIP，`format` 为 `ai-machine-history`，`schema_version` 为 1；复用 `validate_bundle` 的路径与摘要校验，但上限单独设置。
- **流式写入**：边写边算摘要，`manifest.json` 最后写入（校验器按名称读取，不依赖位置）；`allowZip64` 改为允许；单包成员数设上限，超出自动拆成 `…-历史-1.zip`、`…-历史-2.zip`。
- 与主包通过 `parent_content_id` 关联；恢复页提供可选的「恢复历史记录」步骤。
- 范围：H1 为 Claude 的 `projects/*/*.jsonl` 与 `history.jsonl`；H2 为 Codex 的 `sessions/**`、`archived_sessions/**`、`session_index.jsonl`、`history.jsonl`。数据库不带。
- 恢复：只新增、不覆盖、不合并；已存在则另存；映射不到项目的放进 `history-unmapped/`。界面声明「不保证可继续对话」。

## 12. 配置（`machine.config.json`）

`_KEYS`（`config.py:22`）新增可选键：

| 键 | 类型 | 含义 |
|---|---|---|
| `env_include` | 字符串数组 | 额外纳入 SY-01 的环境变量名称（只在名称不含密钥特征时生效） |

其余键不变。`core_projects` 仍可使用，但不再是默认范围的来源（分类规范 §5.6）。

## 13. 一致性与验收测试

所有测试在合成 HOME 里运行，不触碰真实目录。

| 文件 | 内容 |
|---|---|
| `tests/test_machine_classification.py` | **T1** 规则 ID 唯一；**T2** 分类规范第 4 节与 `CATALOG`、`DENY` 双向一致（解析第 4 节表格中以两个大写字母加连字符加两位数字开头的行，如 `CC-01`）；**T3** 并列命中检测；**T4** `classify` 对旧夹具与 `allowed_item` 等价 |
| `tests/test_machine_coverage.py` | 不变量 L1–L4；未定性文件出现在报告；D 类哨兵零读取；采集结果在加账本前后逐字节一致 |
| `tests/test_machine_redaction.py` | 邮箱放行；令牌脱敏且输出不含原值；策略表三种来源；JSON、TOML 脱敏后仍可解析；含邮箱的包通过恢复预检；日志与异常不含命中值 |
| `tests/test_machine_collect_desktop_skills.py` | `user` 与 `anthropic` 分流；多账号两层目录；导出 ZIP 结构 |
| `tests/test_machine_provenance.py` | 非 Git 解析顺序各一例；`unknown` 显式；URL 去用户信息；Git 零读取；同名分组的相同与不同 |
| `tests/test_machine_skills_links.py` | 批准链接：白名单内允许、越界拒绝、目标自身是链接拒绝、目录内含链接拒绝；恢复时不穿过链接 |
| `tests/test_machine_manifest_v2.py` | v1 兼容；v2 字段类型与长度；未知助手或类型报 E7502；路径过长改为排除 |
| `tests/test_machine_restore_new_kinds.py` | 各新类型往返字节一致；冲突分组；`export` 只写报告文件夹；撤销覆盖写入的文件 |
| `tests/test_machine_history.py` | 未勾选零读取；阈值注入下超限仍完成；只新增不覆盖 |
| `tests/test_machine_env_export.py` | 密钥类只出名称；脚本转义；脚本可被 PowerShell 解析 |
| `tests/test_machine_desktop.py`（增补） | 新参数校验、schema、`machine_detect` 的 `groups` 与 `projects` |
| 界面文案扫描 | 新增文案不含禁用词 |

## 14. 错误码（E7500–E7599）

| 代码 | 含义 | 级别 |
|---|---|---|
| E7501 | 批准链接的目标不合规，已跳过该目录 | 警告 |
| E7502 | 备份来自更新的版本，或含不支持的助手、类型 | 错误 |
| E7503 | 路径过长，已排除一个文件 | 警告 |
| E7504 | 一个文件含密钥，已按策略脱敏或跳过 | 提醒 |
| E7505 | 一个技能的来源无法判定 | 提醒 |
| E7506 | 发现未定性的文件，已列出、未备份 | 提醒 |
| E7507 | 历史备份包不完整或与主备份不匹配 | 错误 |

三段式文案（发生了什么、原数据是否保留、下一步）沿用 `sync_core/messages.py` 的 `Message`。


### 2026-10-09 覆盖账本联动补验

采集器在内存中保存物理来源到逻辑位置的对应关系、已解析的技能来源及批准链接；覆盖观察复用这些事实，不为定性再次读正文。批准链接仍通过原四项边界校验，不能用调用参数扩大白名单。Claude 桌面账号根已进入观察，manifest 仅作为 CD-01 关联来源元数据（C/record），账号未知 creator 仍显式未定性。账号自建技能可再生产物按 SK-05 剪枝。

历史携带数按成功来源计数，不按分段数计数，不受主包单文件采集阈值影响；排除或未选择的 H 文件为已观察、未携带。用户环境变量只记录名称分类，非相关名称不取值；安全导出项/密钥名称/其它变量进入字段报告。字段报告仍是定性说明，不冒充所有字段已实际恢复。携带计数以原观察性质入桶，同一文件只计一次。

技能 excluded 的 size 在元数据/枚举失败时可为 null，表示无法核实大小；不能写为 0。enumeration_failed/metadata_unreadable 不等于已检查完整目录；覆盖报告 complete=false，并在预览提示。
