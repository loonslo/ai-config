# 离线迁移包格式 v1

状态：DT-13～17 的格式、采集边界、目录／ZIP 导出、本机只读检查和接收端映射预览核心已实现并通过定向测试；冲突决策、事务导入与客户端操作尚未实现，不能据此宣称离线迁移闭环已可用。

## 同一内容，两种外层

目录包和扩展名 `.aiconfig` 的 ZIP 使用同一套相对文件布局：

```text
package/
  manifest.json
  objects/
    <64 位小写 SHA-256>.bin
```

每个对象的路径由自身 SHA-256 决定。清单 `objects` 列表记录路径、实际字节长度和 SHA-256；`entries` 将逻辑来源、数据类型和适配器绑定到对象。多个逻辑条目可引用同一对象，避免重复保存完全相同的字节。ZIP 不能额外包一层任意目录；清单之外的归档成员由检查器拒绝。

## manifest 字段

`schemas/package.schema.json` 定义 JSON 结构，`sync_core/package/format.py` 还执行跨字段和字节核验。所有对象键均严格；未知字段／schema 版本／数据类型不按兼容文件忽略。

| 字段 | 定义 |
| --- | --- |
| `schema_version` | 包清单格式版本，当前为整数 `1`。不等于包内数据适配器版本。 |
| `package_id` | 每次导出新生成的 32 位小写十六进制 ID；表示包实例，可随机变化。 |
| `content_id` | 对规范化后的范围、适配器版本、逻辑条目、依赖和对象字节身份计算的 SHA-256；相同可移植内容即使 package ID 或导出时间不同也一致。 |
| `parent_content_id` | 可空的上一份内容 ID。它只是版本关系声明，不是自动合并授权。 |
| `created_at` | 带时区的 ISO-8601 展示时间；不参与 `content_id`。 |
| `scope` | 用户选择的 `data_types` 与稳定逻辑 `agent_ids`，不含本机安装根目录或设备 ID。 |
| `adapters` | 被条目使用的适配器 ID 与正整数版本；目标端必须实际支持相同版本才能导入。 |
| `objects` | 唯一内容对象清单；每个 `path` 必须严格为 `objects/<sha256>.bin`。 |
| `entries` | 唯一 `logical_source`、已知 `data_type`、已声明适配器及其版本、对象引用。 |
| `dependencies` | 目标端依赖 ID、最低／指定版本字符串和是否必须。服务不得把它解释为自动安装指令。 |
| `exclusions` | 逻辑来源及排除类别（敏感、受保护、不支持、本机专用、用户排除）；不得记录本机绝对路径或被排除的正文。 |

`logical_source` 是稳定 URI，例如 `agent://codex/main/AGENTS.md`、`settings://codex/main/model`、`skill://shared/review/SKILL.md`、`memory://project-a/MEMORY.md`。URI 只允许 `agent`、`settings`、`skill`、`mcp`、`memory`、`handoff` scheme；非 ASCII 名称以 UTF-8 百分号编码。不得把 `D:/Users/alice/...`、home 目录、设备 ID 或登录状态写入共享包。

v1 已知 `data_type` 枚举为 `rule_file`、`shared_setting`、`agent_declaration`、`skill_file`、`mcp_config`、`memory_snapshot`、`handoff_record`。这只是格式能识别的类型。目标端没有登记的适配器或精确版本时，结果必须为 `unsupported_adapter` 并阻止该条目写入；schema 列表不代表这些数据类型已经实现。

## DT-14 采集范围和本机数据边界

当前本机采集策略由 `sync_core/package/policy.py` 的固定清单控制；它不递归遍历 Agent 目录或配置库。修改支持范围必须同时改策略、适配器版本、验收测试和本表。

| 数据类别 | 当前处理 | 明确边界 |
| --- | --- | --- |
| 共用规则 | 收集 `common/` 下七个登记主题 Markdown | 文件正文先做 UTF-8 与启发式凭据检查；疑似凭据主题不收集；正文检测到本机路径时不做全文替换，列来源和行号并要求人工处理 |
| Codex／Claude 共享设置 | 只读取设备配置明确选择且仍在 allowlist 的 scalar 字段 | 不收集整个 Agent 设置文件、provider、MCP、环境变量或未允许字段；`codex_overrides`、`claude_overrides` 和 state 下覆盖只留本机 |
| Agent 声明 | 可传 profile、主题选择和相对 Markdown 入口策略 | 移除 source `root` 和设备实例名；多个声明合并为逻辑清单。接收端目录需重新选择 |
| `agents.toml` 规则范围 | 可选解析并规范化只含受支持 Agent 与 `topics` 的登记 | 未知字段、路径或内容格式报告不支持；不照抄原始 TOML |
| skills、MCP、记忆、交接 | 当前不从来源目录收集 | 后续 DT-21～24 各自注册实现；不能因为格式枚举中存在类型就显示已支持 |
| Agent 认证／运行数据／缓存／私钥／设备状态 | 永不采集 | 不打开 `.codex`、`.claude`、WorkBuddy 等 Agent 根目录；不读取 auth、cookie、token、会话数据库、日志、cache、private key、设备配置、receipt 或 transaction |
| 未识别文件 | 不采集；只返回配置库顶层未分类数量 | 不递归、不读取正文、不把文件名或路径放入共享 manifest |

正文含本机路径的规则不会被程序改写。诊断只指出逻辑来源和行号，不返回正文片段；用户需在原文件中将绝对路径改成适用于接收设备的说明，或明确取消该主题。规则／设置中的凭据检测仍是启发式检查；`policy.py` 的 allowlist 和不递归读取是主要边界，扫描不能作为凭据绝不会出现的证明。

## 内容标识算法

实现先校验每个对象实际长度和 SHA-256。然后为每条 entry 生成仅含 `logical_source`、`data_type`、`adapter_id`、`adapter_version`、对象 `sha256` 和 `size` 的记录。以 Unicode 原样 UTF-8、JSON 键排序、无空白分隔符序列化以下对象，再计算 SHA-256：

```json
{
  "schema_version": 1,
  "scope": { "data_types": ["按字典序排序"], "agent_ids": ["按字典序排序"] },
  "adapters": [{ "id": "按 id 和 version 排序", "version": 1 }],
  "entries": [{ "按 logical_source 和 data_type 排序的条目记录" }],
  "dependencies": [{ "按 id、version 和 required 排序" }]
}
```

`package_id`、时间、父版本、排除报告和物理对象文件名不参与内容标识；对象哈希和大小参与。这样相同内容的重新打包保持同一 `content_id`，而版本关系或报告时间不会把内容本身伪装成变化。

## 父版本与兼容规则

- v1 客户端只接受 `schema_version: 1`。未知格式版本必须明确拒绝，不进行猜测式降级。
- 未知 `data_type`、清单外的键、重复 logical source／对象、未引用对象、缺失对象、额外对象、长度或哈希错误均拒绝。
- 清单声明了父版本时，只有接收端实际持有并验证过该 `content_id`，才能把它标为“已知共同基线”。父版本未知或缺失时可以展示差异，但不得宣称自动三方合并安全。
- 格式已知但没有对应适配器，报告“不支持该适配器／版本”；不能因为 ZIP 能解开就导入。
- package ID 只用于区分一次导出，不能作为内容版本、信任凭据或服务器授权凭据。

## 示例

`docs/package-format/examples/v1-valid/` 是不含真实凭据的可解析样例。`v1-invalid-unknown-version.json` 故意声明未知格式版本，应被拒绝。样例只证明 manifest 格式和验证器，不提供客户端导出／导入能力。

## DT-15 目录与归档导出

`sync_core/package/export.py` 只接收 DT-14 采集报告，不扫描源目录。内容对象用 SHA-256 命名，相同字节只存一份；逻辑来源中的非 ASCII 字节按 UTF-8 百分号编码，因此物理对象名无需依赖源设备文件名。导出在目标同一父目录创建唯一暂存，先写全部对象和 manifest，再重读 allowlist 来源并比较来源 SHA-256 与采集报告；发现变化则清理暂存并中止发布。

目录包在同一文件系统通过目录重命名发布；`.aiconfig` 使用 ZIP 布局，并以同目录硬链接避免替换既有文件。两种模式开始时都拒绝已经存在的目标。此阶段只支持同一台 Windows 工作区验证；跨平台目录原子发布语义和断电故障注入仍需 DT-26、27 验收。导出 API 目前属于本机核心，尚未接到 Tauri 页面。

## DT-16 只读检查与资源限制

`sync_core/package/check.py` 接受目录包或 `.aiconfig`，不信任归档路径，不解压到目标设备。只允许根目录的 `manifest.json` 与 `objects/` 下内容寻址普通文件；拒绝链接／Windows reparse point、额外文件、重复成员、大小写／Unicode NFC 碰撞、ZIP 加密成员、链接／特殊文件、未知压缩方法和越界对象路径。ZIP 内容分块读取。

当前硬上限：压缩归档 256 MiB、manifest 2 MiB、单个对象 32 MiB、所有解压内容总计 128 MiB、成员最多 10,001 个。超过限制、缺对象、多余对象、文件变化、对象长度／SHA-256 错误或重复 JSON key 均拒绝。格式与字节有效但适配器版本不支持时返回 `unsupported_adapter` 与不可导入状态；检查不代表目标路径已映射，也不执行任何包内容。

## DT-17 接收设备路径映射

`sync_core/package/mapping.py` 只消费已经 `importable` 的 `CheckedPackage`。规则 URI 只接受已登记 shared topics，并映射到接收端配置库；共享设置只接受 Codex／Claude 的明确字段 allowlist；Agent 声明必须通过设备端 Agent 校验。实际本机目录来自接收设备现有配置或只读默认位置检测，包内不给路径赋值。

唯一已安装候选可自动映射；多实例要求 UI 回传检查器给出的实例 ID，映射层不接受任意绝对路径。未安装 Agent 标为 `not_installed`，可保存受支持的配置库内容，但不生成“已应用”状态。输出的设备配置提案基于接收设备配置副本，只添加目标路径／选择；不改接收设备 ID、状态目录、记忆目录或现有覆盖。冲突项待 DT-18 决策。当前 API 仅用于预览；尚不写配置库、Agent 文件或设备配置。

## DT-18 冲突比较

`sync_core/package/conflicts.py` 只读比较包中的来源与接收端配置库、Agent 当前共享设置字段及规则受管区块。只有父包通过内容校验且其 `content_id` 与导入包声明的 `parent_content_id` 精确相同，才启用共同基线；并且每个来源各自必须存在于父包，才对该来源执行三方比较。父包不匹配、未持有父包、父包中缺少来源或包中排除／未包含的文件都不会被推断成删除。

无共同基线且本机与包不同的条目需要逐项选择；支持保留本机、采用包内版本和对 Markdown 规则提供人工合并结果。人工合并结果再次扫描疑似凭据与本机绝对路径。本机设置覆盖和 Agent 实例声明单独作为冲突处理；设备配置提案保留在本机，预览 API 不返回规则正文或设置值。此阶段不写目标文件、不做备份、不承诺可恢复，也未接入 Tauri 页面；这些由 DT-19、DT-20 实施和验收。

## DT-19 事务导入

`sync_core/package/importer.py` 将已审阅的冲突决定转换为 `PlannedChanges`，并把所有预览读取的目标哈希、设备配置文件版本和包身份带入应用边界。应用前再次检查包的 `content_id`／`package_id`；底层事务再次检查读集，获取本机锁、写入原件备份和 journal，并写回共享规则／设置、Agent 目标及接收端设备配置。每个目标写入后做回读比较；父包副本以同一事务最后一项保存，副本再次通过包检查后才提交。事务未完成由既有恢复流程处理；正式完成的 `migrate` 操作可从历史撤销，撤销会恢复目标文件、设备配置和此前父包。

本机 `package_import` 服务与 JSON Lines 操作已经存在，Tauri 页面、冲突选择 UI、过程进度、全量测试和原生窗口验收仍属未完成项。事务 journal 能恢复中断操作，但不代表多个文件具有文件系统级的断电原子性；文件回读成功也不表示 Agent 新会话已加载。

## 扩展适配器（2026-10-01）

新增 skills_v1/mcp_v1/memory_portable_v1/handoff_portable_v1，版本均为 1；数据类型与 v1 schema 原有枚举一致。逻辑来源分别为 skill/mcp/memory/handoff URI，authority 为 codex 或 claude，路径以可移植技能逻辑名或项目 ID 开始，不含根目录。选定技能限定文本资源，链接只在明确来源边界解析；MCP 仅 Codex 非敏感字段；记忆/交接源须为已登记库的验证清单。接收端先保存 portable/，技能复制与 MCP 写入都由冲突决定，管理链接默认保留。记忆重新选择本机映射后由 portable_restore 事务恢复 Claude Markdown，Codex 仅参考。未选扩展完全不采集，云端使用同一内层包。实机支持与未支持项见 [实施记录](desktop-local-implementation.md)。

交接正文首行是 `ai-config portable handoff v1` JSON 注释，明确保存 project_id、handoff_id、commit、branch、lock_files 的 SHA-256、memory_snapshot 和 ready=false，正文与元数据合计不超过 128 KiB。元数据不保存源码目录或远端凭据。接收端可在“可选能力”不使用 Git 传输而查看正文，重新映射本机项目目录后报告源码版本／锁文件缺项；依赖安装与 Agent 新会话未核验时不标记完整接续。
