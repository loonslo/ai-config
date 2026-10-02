# WorkBuddy 迁移分档调研（2026-10-02）

状态：**负责人已于本次会话批准保守分档**。本轮结构调研只读目录名称、大小以及 `settings.json` 顶层／二级键名、类型和集合长度，没有打开人设、记忆、skills 内容、凭据、数据库、会话。批准后 MK-23 才对安全文本候选做只读内存预览，详见验收记录；没有运行加载实验或改动本机源数据。

## 本机目录地图

| 来源 | 已确认的候选内容 | 应排除或待查 |
|---|---|---|
| `~/.workbuddy` | `BOOTSTRAP.md`、`IDENTITY.md`、`SOUL.md`、`USER.md`、`MEMORY.md`；`memory/` 4 文件；`skills/` 5 文件，其中 3 个迁移标记 | `keyblob`、账户 UUID 目录、`security/` 等敏感及 54 个运行类顶层条目 |
| `~/.workbuddy-ai` | `IDENTITY.md`、`SOUL.md`、`USER.md`、`MEMORY.md`；`memory/` 2 文件；`skills/` 55 文件，其中 2 个迁移标记 | `keyblob`、账户 UUID 目录、敏感及 49 个运行类顶层条目；另有未分类 `scripts/` |
| 11 个核心项目（深度 ≤ 2） | 去重后发现 `.workbuddy/` 2 处、`.workbuddy-ai/` 8 处；前者项目记忆 5 文件，后者项目记忆 65 文件、项目技能 4 文件 | 旧基线称项目级 7 处；当前是 10 处，需以本次快照核对。未读取文件内容。 |

顶层人设与记忆文件的体积均在 557–2478 B；`~/.workbuddy/BOOTSTRAP.md` 为 1089 B。两个 `settings.json` 分别约 36 KB，均有 `claw`、`sandbox`、`enabledPlugins`、`autoLaunchDesired`、`officeFileAssociationsRepairMarker`；`~/.workbuddy-ai` 另有空的 `pluginConfigs`。`claw` 的二级结构含 `channels`、`users`、`legacyOwnerUid`，明显接近账户信息；`sandbox` 含 `extraAllowWrite`、`orderedRules`、`networkDenyAllMigrated`，包含机器路径或安全决定的可能性很高。`enabledPlugins` 为布尔映射，分别有 11 和 9 个名称。没有记录这些字段的值。

## 证据与加载边界

- 本机 `sync_core/agents.py` 的 WorkBuddy profile 已把人设、记忆、skills、设置、敏感、运行态分开；本轮目录结构与该分类基本吻合，新增的 `keyblob` 应明确列为敏感，`scripts/` 暂不归入可搬内容。
- [WorkBuddy 官方记忆说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Memory)描述产品对话记忆在后续任务中作为背景信息使用，并提供 UI 管理。它**没有证明** `~/.workbuddy/MEMORY.md` 或项目级 `.workbuddy/memory/` 何时加载。
- [WorkBuddy 官方系统设置说明](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Setting)明确的是代码开发时加载用户级 `.codebuddy` 配置，并与项目级配置合并；这**不能外推**为 `.workbuddy` 或 `.workbuddy-ai` 的文件加载规则。
- [官方 Skill 说明](https://open.workbuddy.cn/en/docs/skill)确认 Skill 包以 `SKILL.md` 定义并可通过市场安装，但未说明本机这两个根目录的迁移或恢复语义。
- UUID 命名顶层目录在两个实例中各有 1 个，性质未获官方依据；本期视为账户／运行态，不进入 bundle。

## 已批准的 A.WB 保守分档

| 类别 | 处理 | 依据与边界 |
|---|---|---|
| 人设 Markdown、`MEMORY.md`、`memory/**/*.md` | ①档候选，采集前做凭据扫描；还原暂列 `manual`，待无个人内容的加载实验确认后再考虑 `auto` | 文件存在且归类明确；真实加载时机未验证。 |
| 自建 `skills/**` 文本文件 | ①档候选，排除 `.*_migration.json`、非文本和符号链接；恢复暂列 `manual` | 官方支持 Skill 机制，但本机目录的自动发现尚未验证。 |
| `settings.json.autoLaunchDesired` | 只记录存在，暂不恢复 | 是布尔偏好；是否在新机适用未验证，未纳入本次批准的采集字段。 |
| `settings.json.enabledPlugins` | 只记插件**名称**到重装清单 | 插件安装状态由应用管理；复制布尔映射不能保证插件已安装。 |
| `settings.json.sandbox` | 只记存在，不复制 | 可能含绝对路径与安全规则，跨机自动恢复不安全。 |
| `claw`、`pluginConfigs`、`officeFileAssociationsRepairMarker`、`mcp-approvals.json` | 不搬 | 账户信息、未证实内部结构、应用迁移标记或安全决定。 |
| `keyblob`、UUID 目录、`security/`、`app/`、`connectors*`、`*.db*`、运行目录、`scripts/` | 永不打开或复制；`scripts/` 待单独确认归属 | 凭据／会话／运行状态或未分类。 |

## 待解决

1. 在空白测试账户和不含个人内容的隔离目录中，验证全局与项目 `.workbuddy[-ai]/` 人设、记忆、技能的加载时机；未验证前不能宣称恢复成功。
2. 确认两个实例的 UUID 账户目录用途与登录后再生成方式；本期保持排除。
3. 负责人已批准人设／记忆／技能文本的 `manual` 范围，`catalog.py` 对应项已调整。设置字段仍不批准自动恢复；加载实验与跨机核验通过前不能宣称恢复成功。
