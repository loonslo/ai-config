# 三机验收记录

本文记录跨设备配置一致性的功能验收与零基础可用性验收。

**当前状态：部分完成。** 自动化部分已在单机完成并可复现；三台真实设备的验收需要用户提供硬件与私有远端，尚未执行。

## 一、自动化验收（已完成）

### 复现方式

```text
python -m pip install -r requirements.txt
python -m pytest -q --basetemp=tmp/run-<新编号>
```

必须为每次运行使用**全新的** `--basetemp` 目录。复用同一个目录会与上次运行留下的 `tmp_path` 内容冲突，产生大批与本改动无关的失败。

### 结果

| 项目 | 结果 |
| --- | --- |
| 全量测试 | 145 通过 / 0 失败 |
| 运行时长 | 约 70 秒 |
| 平台 | Windows 11，Python 3.13.14 |
| 敏感信息扫描 | `scripts/check-secrets.py` → 0 findings |

### 覆盖范围

| 需求 | 覆盖方式 |
| --- | --- |
| 结构版本可验证、未知版本拒绝 | `tests/test_config_consistency.py` |
| 受管字段来自设备实际选择 | `tests/test_config_consistency.py` |
| 凭据/会话字段被拒绝共享 | `tests/test_config_consistency.py` |
| 目标文件缺失不判为已应用 | `tests/test_config_consistency.py` |
| 只改未受管内容不误报漂移 | `tests/test_config_consistency.py` |
| 环境检测无写入、缺依赖有中文指引 | `tests/test_config_consistency.py` |
| 启动脚本不依赖当前目录、不重复安装 | `tests/test_ux_flows.py` |
| 首次设置与加入流程幂等 | `tests/test_ux_flows.py` |
| 预览零写入、重复执行无多余写入 | `tests/test_ux_flows.py` |
| 配置同步不要求存在记忆仓库 | `tests/test_ux_flows.py` |
| 状态可读且只配置用户不见记忆错误 | `tests/test_ux_flows.py` |
| 回执分支隔离、并发上报不覆盖 | `tests/test_ux_flows.py` |
| 回执不含真实路径与敏感值 | `tests/test_ux_flows.py` |
| 差异展示遮蔽敏感字段 | `tests/test_ux_flows.py` |
| share / local / restore 三种归属 | `tests/test_ux_flows.py` |
| 手改规则区块后 diff 必须列出该行 | `tests/test_ux_flows.py` |
| 恢复闭环可走完（restore 后 sync 成功） | `tests/test_ux_flows.py` |
| 规则区块拒绝 `local`、提示不列被拒选项 | `tests/test_ux_flows.py` |
| restore 意图一次性，不掩盖后续手改 | `tests/test_ux_flows.py` |
| 敏感值不可共享也不可覆盖 | `tests/test_ux_flows.py` |
| 按操作恢复、备份损坏拒绝 | `tests/test_ux_flows.py` |
| 错误不抛 traceback、JSON 与退出码一致 | `tests/test_config_consistency.py` |
| 记忆不启用时配置独立成功 | `tests/test_onboarding.py` |
| 含凭据来源保持阻断态 | `tests/test_onboarding.py` |
| 新项目自动推导 ID | `tests/test_onboarding.py` |
| 历史交接与当前交接不混淆 | `tests/test_onboarding.py` |

### 端到端手工验证（单机）

在隔离目录中用真实 `device.json` 走完整流程：

| 步骤 | 命令 | 观察结果 |
| --- | --- | --- |
| 1 | `sync.py status --local <dev>` | 中文输出，四个目标均为“未设置” |
| 2 | `sync.py sync --local <dev>` | 列出 5 个将要写入的路径，目录仍为空 |
| 3 | `sync.py sync --local <dev> --apply` | “已应用 5 处共享配置变更” + 需要新会话提示 |
| 4 | `sync.py status --local <dev>` | 三个目标“已应用”，一个无受管字段“未设置” |
| 5 | 手工改受管区块 | 状态变为“存在本机修改” |
| 6 | `sync.py sync --local <dev>` | 退出码 4，E3001，说明运行 diff |
| 7 | `sync.py diff --local <dev>` | 列出“公共规则（rules）”一行，只提供 share / restore |
| 8 | `sync.py diff --local <dev> --choice restore --apply` | 打印“已保存”；此时尚未改目标文件 |
| 9 | `sync.py sync --local <dev> --apply` | 退出码 0；手改内容被共享区块覆盖，区块外原文保留 |
| 10 | `sync.py sync --local <dev> --apply`（再跑一次） | 退出码 0 且零变更，闭环不再报冲突 |
| 11 | `sync.py undo --local <dev> --index 1` | 预览列出 `AGENTS.md`，可找回被覆盖的内容 |

以上第 5–11 步是**回归重点**：修复前第 7 步会打印“没有需要处理的字段差异”，用户按提示操作后第 9 步仍然失败，文档承诺的恢复路径实际走不通。

## 二、三机功能验收（待执行）

需要用户提供以下条件后才能进行。**不能用 Windows 目录模拟 Mac。**

| 条件 | 说明 |
| --- | --- |
| 两台 Windows 设备 | 例如 windows-a、windows-b |
| 一台 Mac | 真实 macOS 实机 |
| 一个配置源远端 | Git 地址，三台设备共同克隆 |
| Python 3.11+ | 三台设备均需满足 |

### 验收清单

每一项需分别记录 Windows A、Windows B、Mac 的版本与结果。

| # | 场景 | 通过标准 |
| --- | --- | --- |
| 1 | 首次安装（A） | 只读检测正确；`--apply` 后配置生成；A 状态为已应用 |
| 2 | 加入（B、Mac） | 复用共享选择，不要求重选全部参数；ID 不冲突 |
| 3 | 重复加入 | 幂等，不产生半套配置 |
| 4 | A 修改 → B 获取 | B 同步后状态为已应用；A 与 B 受管字段一致 |
| 5 | A 修改 → Mac 获取 | 同上，且路径差异不被判为冲突 |
| 6 | 三机回执核对 | 每台能看到另外两台“最近报告于”；无设备被标为在线 |
| 7 | 离线重试 | 断网时退出码 3 且本机状态不变；恢复后重试成功 |
| 8 | 本机覆盖 | `--choice local` 后不影响其他两台 |
| 9 | 远端冲突 | 双方都改同一字段时停止并保留双方内容 |
| 10 | 目标文件被工具改写 | `status` 识别为存在本机修改 |
| 11 | 撤销上次应用 | `undo --apply` 后受管字段回到当时值 |
| 12 | 回执上传失败 | 本机已应用状态保留，另报 E5001 |
| 13 | 单工具设备 | 只装一个工具时正常工作 |
| 14 | 未启用记忆 | 全流程无记忆相关错误 |
| 15 | Mac 执行权限 | `chmod +x ai-config.command` 后可运行 |

### 记录表（填写用）

```text
设备 A：windows-a   版本：          日期：
设备 B：windows-b   版本：          日期：
设备 C：mac         版本：          日期：
配置源提交：
```

## 三、零基础可用性验收（待执行）

需要一位**未参与开发**的使用者，只按 `README.md` 与 `docs/getting-started.md` 操作。

### 记录要求

| 项目 | 记录内容 |
| --- | --- |
| 卡点 | 在哪个步骤停下、停了多久 |
| 误解 | 把什么理解成了什么 |
| 是否需要口头帮助 | 是 / 否；如果需要，帮的是什么 |
| 是否误改 JSON | 是 / 否 |

### 通过标准

- 全程**无需手工编辑 JSON**。
- 日常同步只用**一个入口**。
- 用户能用自己的话准确说明：
  1. 本机是否已应用；
  2. 哪些设备待更新；
  3. 失败后如何继续。
- 三台设备的测试报告完整。

## 四、多 agent 扩展验收（2026-10-01）

范围：识别迁入（`scan`、`migrate`、`detach`）、适配器注册表、新 agent 接管（CodeBuddy、WorkBuddy、TRAE、通用声明）、版本戳与 `verify-load`、配置库 `agents.toml`、`setup --store`。

### 隔离测试（已执行）

| 项目 | 结果 |
| --- | --- |
| 日期与环境 | 2026-10-01，Windows 10 Pro，项目 `.venv` 的 Python 3.13.14（系统 Python 3.14 未安装 tomlkit/pytest） |
| 全量测试 | 260 通过 / 0 失败（提交 `69262fc`，`--basetemp=tmp/run-mag-p4e`） |
| 敏感信息扫描 | `scripts/check-secrets.ps1` → 0 findings |
| 原有测试 | 原有 164 项在整个扩展过程中未作修改，全部通过 |

| 需求 | 覆盖 |
| --- | --- |
| Codex/Claude 行为不变，其他 agent 走同一规划与核验 | `tests/test_agent_registry.py` |
| 只读盘点，受保护诱饵文件从未被打开，沙箱不变 | `tests/test_scan.py` |
| 迁入去重、独有内容需明确选择、凭据阻止、幂等、可撤销；迁入→同步→退出后沙箱逐字节还原 | `tests/test_migrate.py` |
| 每个可写适配器同一套生命周期：识别、渲染、写入、核验、幂等、漂移、撤销、退出 | `tests/test_agent_contract.py`（10 个用例） |
| 版本号问答核验、过期、回执只带布尔值 | `tests/test_verify_load.py` |
| `agents.toml`、`declare`、setup 识别、未解析入口提示 | `tests/test_takeover.py` |

### 未执行的检查

- 在本次 DT 执行开始前，`tests/test_store.py` 尚未运行；其后单文件 5 项结果见第五节。Phase 5/6 的全量测试仍未重新运行。复现命令：`.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/run-<新编号>`。
- 真实 agent 的加载核验尚未执行。必须在干净的虚拟机或独立系统账户中安装各 agent 后进行，不在开发者日常账户上做：

| agent | 规则入口 | 依据 | 加载核验 |
| --- | --- | --- | --- |
| Codex | `~/.codex/AGENTS.md` 受管区块 | 现有实现 | 待执行 |
| Claude Code | `~/.claude/CLAUDE.md` 受管区块 | 现有实现 | 待执行 |
| CodeBuddy CLI / IDE | `~/.codebuddy/rules/ai-config.md` | 官方文档 | 待执行（CLI 与 IDE 分别核验） |
| WorkBuddy / WorkBuddy AI | `AGENTS.md` 受管区块 | 仅社区资料 | 待执行；不通过则改用 `USER.md` 受管区块 |
| TRAE / TRAE CN | `user_rules/` 目录或 `user_rules.md` | 官方文档与论坛 | 待执行；需确认实际形态 |
| WorkBuddy 云同步 | 是否跨设备复制受管区块 | — | 待核对 |

### 开发机只读观察（不作为验收）

2026-09-30 至 2026-10-01 在开发机上只运行了只读的 `scan` 与 `migrate` 预览，用来检验对真实目录结构的识别；没有执行任何 `--apply`，`device.json` 预览前后哈希一致。观察到：两个 WorkBuddy 实例、CodeBuddy、指向 CC Switch 的 `~/.claude/skills` 链接均被正确识别；Codex/Claude 规则文件中的旧手写副本按章节切分后，8 个章节里 7 个已完全在配置库中，1 句旧说明为独有且同时出现在两个 agent 中。

## 五、桌面客户端与迁移方案记录（2026-10-01）

本节起初记录于方案拆分阶段，随后按用户要求逐项实施并更新。环境为 Windows 工作区；方案见 `docs/desktop-client-plan.md`，40 项工作及范围边界见 `DESKTOP-TASKS.md`。DT-01～04 已分别通过其记录的本机范围；DT-05／06 当前有 Windows 构建和客户端原型证据，但不代表干净账户安装或全功能客户端已验收。

当前执行边界：DT-04／DT-06 当前协议与状态服务定向回归 88 passed；DT-05 Windows Tauri/NSIS 与 Python 3.14 sidecar 已构建，sidecar 受限 PATH 只读冒烟通过。干净账户安装启动尚未验收，静默安装尝试被工具执行策略拦截。DT-06 导航和真实状态页为原型，尚未进行原生窗口交互／无冻结验收。未生成或导入迁移包、连接服务器、做跨设备迁移或验证真实 agent 新会话；历史的 260、273、278 项测试分别对应较早代码状态，完整 pytest 未在当前改动后重跑。

### DT-06～08 客户端本机流程增量（2026-10-01）

DT-06 总览按服务返回的配置状态和会话加载核验状态设置提示等级；`stale` 明确提示用户开启新会话并重新核验。上传／下载仍显示“尚未支持”。没有做原生窗口状态逐项人工验收或冻结验收。

DT-07 在 `desktop/src/App.tsx` 接入 setup 预览与应用：用户可选择识别出的 Agent、编辑其绝对目录、确认默认 `.ai-sync/store` 或指定其他目录，先查看设备 ID 与将保存的本机路径，再明确确认。应用后刷新真实 status。设置完成后可声明通用 agent 的根目录、相对 Markdown 入口和 managed-block／owned-file 管理方式。已有设备配置时 setup 只允许识别、不提供可应用计划，避免重复设置覆盖旧配置。RPC 对自定义 Agent 根目录、配置库目录及 setup Agent 目录做绝对路径校验；核心继续校验相对 Markdown 入口不可越界。

DT-08 在客户端接入迁入清单和逐项预览／执行。页面显示来源、规则行数、有限的独有行预览和受保护跳过原因；调用核心读取文件前已执行凭据启发式扫描，命中时不返回内容。客户端协议要求提供具体 `item` 与 `choice` 才会生成可应用计划，避免无选择执行 CLI 的默认动作。执行后返回事务备份目录并重新读取清单。备份与底层事务的集成由现有核心负责。

定向验证（Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_migrate.py tests/test_scan.py tests/test_takeover.py --basetemp=tmp/run-dt07-08-recheck-20261001-a` → **65 passed，0 failed，7.72 秒**。覆盖 setup 自定义目录传递、绝对路径约束、已有配置防覆盖、无选择迁入预览不可应用、迁入／扫描／接管回归及 schema 与运行时白名单一致。前端 `npm run build`（TypeScript + Vite）通过；`npm run lint`（oxlint）通过且无告警。

未验收：原生 Tauri 窗口手工交互和冻结情况、多实例／无 Agent 的客户端端到端路径、凭据诱饵在实际页面的隐藏效果、迁入重复应用后的 UI 状态、UI 中撤销原件，以及干净账户安装。此项未运行当前全量 pytest；不得把构建或定向测试记为客户端任务完成。尚未实现共享规则编辑与应用（DT-09）、退出／加载核验（DT-10）、历史／撤销页面（DT-11）或离线迁移包（DT-13～20）。

待验收：桌面全功能操作及内置运行环境、离线完整导出／导入、Windows／macOS 目录适配和加载、已有文件冲突与恢复、skills／MCP 支持范围、云端身份与用户隔离、加密及密钥恢复、上传／下载和并发冲突。

### 同日详细任务拆分与后续实施

用户进一步要求明确说明每步究竟做什么。已在 `DESKTOP-TASKS.md` 建立 DT-01～40；每项列具体工作、拟改位置、依赖、交付物及可观察验收。TODO.md 增加全部任务索引，task.md 增加阶段门槛，UX-TASKS.md 标明旧 CLI 范围为历史记录，详细方案补齐操作映射、接口和服务器职责。

| 新功能待验收范围 | 对应任务 | 当前状态 |
| --- | --- | --- |
| 当前核心基线、数据目录、无 Git 离线配置库 | DT-01～02 | 已验收各自记录范围；不包含桌面打包或真实迁移 |
| 可直接调用的应用服务 | DT-03 | 已验收本机服务与 CLI 共用范围；不包含桌面 UI、跨平台、迁移包和服务器 |
| 结构化接口 | DT-04 | 本机协议已定向验收；Tauri 集成／UI 冻结未验收 |
| 独立安装与内置运行时 | DT-05 | Windows sidecar、Tauri release 与 NSIS 包构建通过；安装器／干净账户启动未验收 |
| 全部现有功能的真实客户端入口 | DT-06～12 | DT-06～12 操作原型已接入并通过各自定向测试／构建；原生窗口交互、无冻结、真实 Agent 和远端流程仍未验收 |
| 规则／共享设置的完整离线包、路径映射、冲突与恢复 | DT-13～20 | DT-13～17 核心已定向验证；DT-18 只读冲突比较核心和 DT-19 可恢复事务导入已定向验证；DT-18 冲突 UI、DT-20 客户端迁移流程未完成 |
| skills、非敏感 MCP、记忆／交接的迁移适配及范围展示 | DT-21～25 | 未实现／未验收；原有记忆能力不代表包适配已完成 |
| Windows、macOS、三机及普通用户纯客户端流程 | DT-26～29 | 待真实安装包、设备及用户 |
| 服务器身份、加密／解锁、上传／下载、并发、联调、部署及恢复 | DT-30～38 | 未实现／未验收；真实服务器条件未提供 |
| 可追溯构建与对应发布文档 | DT-39～40 | 未完成；计划文档不代表发布文档已验收 |

方案拆分当时没有运行 pytest；随后用户授权逐项执行。DT-01／02 的基线与实现回归及 DT-03／04 的服务和本机 RPC 验收记录在下文，DT-05／06 当前原型证据见本节后文。离线迁移包、服务器、跨平台和真实 agent 加载仍未实施或验收。历史全量 260、273、274 和 278 项分别对应不同代码状态，不能当作当前完整回归结果。

DT-03 之前的文档核对（2026-10-01，Windows／PowerShell，本工作区）：DT-01～40 编号连续且唯一，任务字段、TODO 索引和 PROJECT_STATUS 路径自检通过；敏感扫描 0 findings。此记录为当时检查，不代表后续改动已重新扫描。

DT-01 基线测试（2026-10-01，Windows 工作区，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_store.py --basetemp=tmp/run-dt01-store-20261001-b` → 5 passed。该测试验证当时的 Git 配置库模板、创建／重复使用／克隆、不接管无关目录和 setup 预览。此后 DT-02 将本机建库改为无需 Git，并重跑 store 及相关回归。

DT-02 定向测试（2026-10-01，Windows 工作区，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_store.py tests/test_layout.py tests/test_config_consistency.py tests/test_ux_flows.py tests/test_onboarding.py tests/test_takeover.py tests/test_launchers.py --basetemp=tmp/run-dt02-target-20261001-c` → 133 passed。

DT-02 完成后的全量回归（同一工作区与环境）：`.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/run-dt02-full-20261001-a` → 273 passed，0 failed，116.05 秒。结果覆盖当时的未提交工作区代码；没有验证桌面 UI、macOS、真实 agent 会话、三机迁移或服务器。

DT-03 首轮规划抽取（2026-10-01）：新增 `sync_core/planning.py`，将规则渲染及 rules/config 规划放在核心层；`config_sync` 不再反向导入 CLI。相关 67 项通过；当时全量 274 项通过。这是部分阶段记录，不是最终验收。

DT-03 最终验收（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：新增 `sync_core/application/` 的 `ApplicationService` 与 `ApplicationResult`，为 setup、quick、scan、migrate、declare、sync、status、diff、detach、verify-load、undo、doctor、inventory、memory-setup、rules/config/memory、project、restore、start、finish 提供本机调用；CLI 入口复用这些服务，finish/start 工作流位于 `application/continuation.py`。具体服务到客户端页面映射见 `docs/desktop-client-plan.md` 第 8 节。无 CLI 反向导入；独立子进程验证 import／构造不启动向导、不创建文件。定向服务与回归命令 `.venv/Scripts/python.exe -m pytest -q tests/test_sync.py tests/test_scan.py tests/test_migrate.py tests/test_takeover.py tests/test_onboarding.py tests/test_git_memory.py tests/test_reliability_core.py tests/test_launchers.py tests/test_sync_integrity.py tests/test_four_sync_fixes.py tests/test_core_import_direction.py --basetemp=tmp/run-dt03-service-verify-20261001-a` → 121 passed。最新全量命令 `.venv/Scripts/python.exe -m pytest -q --basetemp=tmp/run-dt03-final-20261001-a` → 278 passed，0 failed，134.53 秒；另对新增的 memory service 默认配置调用验收 1 passed。`py_compile` 和 `git diff --check` 通过。未验证 Tauri、macOS、真实 agent 会话、迁移包或服务器。

DT-04 本机协议验收（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：新增 `schemas/desktop-rpc.schema.json`、`sync_core/application/protocol.py` 和 `scripts/desktop_rpc.py`。JSON Lines v1 只开放应用服务白名单操作；preview 生成一次性 20 分钟计划 ID 和内容版本摘要，apply 前重算并核对计划输入，陈旧计划返回 `E_PLAN_STALE`。辅助程序将作业串行化并输出 accepted／progress／result／cancel_result；排队任务可取消，进入写入边界后明确拒绝取消。`sync(fetch=true)`／`sync(publish=true)` 在 preview 阶段返回 `E_PREVIEW_SIDE_EFFECT`，桌面传输流程仍未实现。

验证命令：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_core_import_direction.py tests/test_sync.py tests/test_sync_integrity.py tests/test_takeover.py tests/test_layout.py tests/test_launchers.py tests/test_reliability_core.py --basetemp=tmp/run-dt04-acceptance-20261001-c` → 85 passed，42.76 秒。覆盖未知版本／操作／参数、schema 与运行时操作表一致、预览后输入变化阻止应用、信息型流程没有空应用计划、作业串行与排队取消、进度事件、有效／无效请求 ID 隔离和 UTF-8 子进程协议预览不写入目标。schema JSON 解析通过；环境未安装独立 JSON Schema 校验器，未宣称经该校验器验证。DT-03 的全量 278 passed 是 DT-04 之前代码状态；DT-04 后尚未重跑全量测试。

本项只验收本机协议层，不含 Tauri UI，因此无法据此断言界面实际不会冻结；UI 调用方式与进度消费在 DT-06 集成验证。进程异常终止后的事务状态由核心日志和 `doctor` 检查，自动启动检查与恢复 UI 属 DT-11。未验证 Python 3.14 打包、Mac、Git fetch／publish、云端服务或真实 agent 新会话。

DT-05 Windows 原型构建与 sidecar 验证（2026-10-01）：新增 `desktop/` Tauri 2 + React 19 + TypeScript + Vite 客户端，锁定 npm/Cargo 依赖；Python 构建环境为 3.14.0，PyInstaller 6.22.3、pyinstaller-hooks-contrib 2026.8、tomlkit 0.13.3。`scripts/build-desktop-sidecar.ps1` 生成 one-file 控制台辅助程序；PyInstaller archive viewer 核实包内有 `schemas/desktop-rpc.schema.json`、common 与 templates 目录、tomlkit 及 Python 3.14 DLL。使用 Windows 系统目录作为子进程 PATH（不包含 Git 或 Python 命令）启动冻结 sidecar，`status` 首次运行预览返回 `configured: false`，没有创建目标 `device.json`；随后 `shutdown` 后子进程正常退出。也在同类受限 PATH 下执行过 `setup` 只读识别，报告 Git 可选。

验证：`npm run build`（TypeScript + Vite）通过；`npm run lint`（oxlint）通过；Rust 1.98.1／Cargo 1.98.1、Tauri CLI 2.12.1 下 `npx tauri build --no-bundle` 与 `npx tauri build` 均成功，生成 NSIS x64 安装包 `desktop/src-tauri/target/release/bundle/nsis/AI Config_0.1.0_x64-setup.exe`，大小 12.45 MiB。Shell 插件的显式 spawn 权限只开放 `binaries/ai-config-rpc` sidecar 且不允许附带命令行参数，没有开放通用 shell 执行。实际安装器静默安装调用被工具执行策略拒绝（工具未提供更具体原因），没有安装或启动该安装包；因此不宣称干净 Windows 账户通过，也未直接验证真实 Tauri 窗口退出是否等待 sidecar。协议层 shutdown 子进程测试在当前 88 项定向回归内通过。NSIS 构建成功也不能代替干净账户验收。

DT-06 状态与导航原型（2026-10-01）：`desktop/src/App.tsx` 实现总览、Agent 与规则、设备迁移、云端同步、历史恢复、记忆接续六个本地导航入口。总览只发 `status` preview；目标文件应用与 load-check 状态分开呈现，服务器上传／下载明确显示尚未支持，不显示远端在线推测。Agent 页面可运行 `setup` 只读识别。`ApplicationService.status()` 在设备配置缺失时返回 `not_configured`，不创建目录或文件；`tests/test_application_protocol.py` 覆盖该行为。前端生产构建与 oxlint 已通过。对应核心／协议／接管／路径回归：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_core_import_direction.py tests/test_sync.py tests/test_sync_integrity.py tests/test_takeover.py tests/test_layout.py tests/test_launchers.py tests/test_reliability_core.py --basetemp=tmp/run-dt06-status-20261001-a` → 88 passed，41.64 秒。没有运行当前工作区全量 pytest，也没有原生 Tauri 窗口自动化、冻结、失败／本机修改／重新开会话等界面状态端到端验收；其他页面是明确标记未实现的边界页。

### DT-09 共享规则编辑与配置差异（2026-10-01）

Agent 与规则页提供共享 Markdown 规则的编辑流程：读取受支持规则文件，先预览保存到本机配置库，再单独确认保存；需要应用到 Agent 时另行生成预览并确认应用。读取时发现可疑敏感内容的规则不会把正文返回界面，可由用户以新正文整文件替换；保存前仍执行敏感内容检查。配置库写入经事务备份。

共享设置差异页展示每项来源和受掩码的值，用户可对当前兼容条目选择共享、本机保留或恢复；保存该选择后，还需独立预览并应用到 Agent。协议层去除传给界面的原始值字段。当前界面以一个选择作用于所有显示且支持该选择的差异项；不同目标分别选择、复杂键值逐项编辑与人工合并尚未实现。

验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_sync.py tests/test_ux_flows.py --basetemp=tmp/run-dt09-diff-20261001-a` → **79 passed，0 failed，14.44 秒**。覆盖 RPC 规则读写、保存预览失效、事务备份、敏感内容隐藏／拒绝以及共享设置归属／配置流程。`desktop/` 中 `npm run build`（TypeScript + Vite）与 `npm run lint`（oxlint）通过。

边界：没有在原生 Tauri 窗口手工验收；没有验证不同 Agent 实例独立决策、UI 端目标外部修改后的提示效果、逐项设置编辑／人工合并或真实 Agent 新会话加载。因而 DT-09 仍为实施中，不能据此宣称客户端闭环完成。未运行全量 pytest。

### DT-10 退出接管与会话加载核验（2026-10-01）

客户端在 Agent 与规则页列出本机已登记的 Agent 实例。会话核验先由核心返回问题和“磁盘规则是否为当前版本”的结果；用户需要自行打开 Agent 的新会话、提问并粘贴回答。客户端将回答送入只读预览，再单独确认记录；只有版本回答匹配且目标文件仍是当前版本时才通过，旧版本／错误回答可被记录为失败。退出接管可以选择一个实例，预览要移除的 ai-config 受管文件区块、尝试恢复的迁入原件及冲突；确认后经事务写入备份并刷新状态。服务端响应不替用户启动、关闭或控制 Agent。

验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_verify_load.py tests/test_migrate.py tests/test_takeover.py --basetemp=tmp/run-dt10-agent-20261001-b` → **63 passed，0 failed，13.18 秒**。`desktop/` 中 `npm run build`（TypeScript + Vite）与 `npm run lint`（oxlint）通过。首轮定向运行发现未配置状态新增 `agents: []` 会更改既有协议返回结构；已移除该字段并以新的 basetemp 重跑，最终结果为 63 passed。

边界：未在 Tauri 原生窗口手动验收；没有实际打开 Codex／Claude 等 Agent 的新会话或验证回答是否来自真实会话；多 Agent 实例的交互、退出后的 Agent 自身行为和备份 UI 尚未验收。因此 DT-10 仍为实施中。未运行全量 pytest。

### DT-11 操作历史、撤销与中断事务恢复（2026-10-01）

本机已设置的设备启动后会执行只读 `doctor`，历史页也可重新检查。诊断显示事务 ID／状态、问题和警告；只有状态为 PREPARED、APPLYING、INTERRUPTED 或 ROLLBACK_REQUIRED 的事务会提供恢复预览，日志无效时禁用自动恢复。确认恢复后由核心依据事务日志和备份执行回滚。历史列表只包括已提交的配置应用、规则迁入、退出接管和登记操作，显示时间、Agent、变更数量、受影响的本机路径与备份位置，不读取或展示文件正文。选择记录后先预览回滚路径，再确认；底层核心校验备份哈希和目标现状，目标后来有改动时拒绝覆盖。

验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_ux_flows.py --basetemp=tmp/run-dt11-history-20261001-b` → **70 passed，0 failed，14.59 秒**。`desktop/` 中 `npm run build`（TypeScript + Vite）与 `npm run lint`（oxlint）通过。

边界：未在 Tauri 原生窗口手工验收；未模拟桌面端真实断电或操作系统强制终止；损坏备份、无效日志和后续外部修改的界面提示未进行手动实测。自动恢复结果只由现有核心事务测试支撑，不能据此声称桌面端所有故障恢复交互已验收。未运行全量 pytest。

### DT-12 记忆与项目接续客户端入口（2026-10-01）

可选能力页已接入本机记忆来源查看、明确选择与映射启用／关闭、来源盘点及可选保存、快照清单和单快照恢复预览／确认、项目路径映射、交接模板／文本、finish 与 start 检查。记忆保持可选，不阻塞规则配置。快照清单只返回元数据；Codex 项目快照仅供参考，界面不提供回填 Codex 原生记忆数据库的操作。交接文本通过 RPC 限制在 128 KiB 内；用户确认 finish 后，核心可能写入快照并向已配置的 Git 远端推送。start 应用也可能快进读取 Git 远端；当前界面有提示，但尚无独立的下载确认步骤。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_application_protocol.py tests/test_onboarding.py tests/test_takeover.py tests/test_reliability_core.py --basetemp=tmp/run-dt12-opt-20261001-b` → **70 passed，0 failed，37.19 秒**。`desktop/` 中 `npm run build`（TypeScript + Vite）及 `npm run lint`（oxlint）通过。协议 schema JSON 解析由 `test_application_protocol.py` 覆盖。

边界：未在 Tauri 原生窗口操作；未验证 Mac、第二台 Windows、真实远端变化、多设备记忆往返或真实 Agent 新会话。Git 远端下载／发布目前仍由接续核心按现有条件尝试，不代表已实现独立可审核的桌面传输步骤。全量 pytest 未运行。因此 DT-12 已接入原型并通过定向核心验证，仍处实施／验收中。

### DT-13 离线迁移包格式与版本规则（2026-10-01）

已固定 v1 `manifest.json` schema、内容寻址对象路径、逻辑来源 URI、已知数据类型、适配器 ID／版本、依赖和排除类别。目录包与 `.aiconfig` ZIP 约定共用相同内层结构；`package_id` 唯一标识导出实例，`content_id` 根据可移植字段和对象实际 SHA-256／长度稳定计算。父版本未知时只报告 unknown，不声称具备三方合并基线。已添加不含真实数据的可用／无效 JSON 样例、包格式说明与严格本机校验器；缺字段、额外字段、重复键／路径／条目、未知版本／类型、无可用适配器、对象缺失／多余／内容哈希错误均拒绝或明确报告不支持。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt13-format-20261001-e` → **9 passed，0 failed**。schema 与 Tauri 配置 JSON 解析、`git diff --check` 通过。这里仅验收格式和内存字节校验，不代表目录／ZIP 导出、归档安全暂存或客户端导入已经实现；这些归 DT-15、16、20。

### DT-14 纳入范围与本机数据隔离（2026-10-01）

`sync_core/package/policy.py` 固定当前候选来源：仅读取 `common/` 七个规则主题、设备配置中选择且仍在 allowlist 的 Codex／Claude 共享标量设置、只含受支持 topics 的 `agents.toml`，以及剥离本机 `root` 与实例名后的 Agent profile 声明。个人 overrides、device 配置、agent 根目录、认证、会话、运行数据库、cache、私钥、回执、事务和其他未知文件均不进入读取范围；未知 store 顶层项目只计数，不遍历或返回名称。凭据启发式命中时正文不进入候选；本机路径检测不作全文替换，只提供逻辑来源和行号供用户处理。各数据类别与限制见 `docs/package-format.md` 的 DT-14 表。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt14-policy-20261001-c` → **14 passed，0 failed**。覆盖 allowlist、共享设置选择、override 和路径剥离、含凭据规则排除、本机路径行号提示、Agent 根目录诱饵与未知文件未被打开、非普通 registry 路径受保护报告，以及 package 格式回归。

边界：策略能证明代码的明确读取集合和当前测试诱饵行为，不证明启发式扫描可以识别所有潜在秘密；尚未通过真实迁移 UI 展示此报告。完整归档检查由 DT-16 的核心检查器覆盖，原生 UI 展示与跨平台实机验收仍待进行。

### DT-15 一致采集与自包含离线导出（2026-10-01）

新增 `sync_core/package/export.py`，用 DT-14 的固定采集结果构建严格 v1 manifest 和 SHA-256 内容对象。相同字节只保存一次；逻辑来源按 UTF-8 百分号编码。目录包和 `.aiconfig` ZIP 使用相同内层文件布局。manifest 和对象写入目标同盘暂存后，核心重新读取 allowlist 来源并比较文件哈希与采集报告；如来源发生变化则删除暂存、不发布。已有目录／文件拒绝覆盖，ZIP 使用同目录硬链接原子发布。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_export.py tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt15-export-20261001-c` → **17 passed，0 failed，0.62 秒**。验证了目录与 ZIP 回读内容一致且可按 manifest 验证、零字节对象、非 ASCII 逻辑名编码、已有目标保留、过期来源阻止发布并清理暂存。尚未接入 UI，也未实测 macOS／其他平台、断电故障或第二台设备客户端打开；完整包读取安全检查仍属 DT-16。

### DT-16 目录与归档只读安全检查（2026-10-01）

新增 `sync_core/package/check.py`，统一检查目录包与 `.aiconfig` ZIP。目录只能包含 `manifest.json` 和 `objects/`；归档只接受对应 manifest 与内容寻址对象。检查器限制压缩／展开大小、单对象大小和成员数，分块读取 ZIP 对象；拒绝链接／reparse point、特殊／加密成员、路径穿越、重复或大小写／Unicode 规范化碰撞、额外／缺失成员和错误哈希。正确但目标端无对应适配器时明确返回 `unsupported_adapter`，不可导入。读取只使用有界内存，不执行包文件或触碰目标配置。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_check.py tests/test_package_export.py tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt16-check-20261001-d` → **22 passed，0 failed，1.15 秒**。覆盖合法目录／ZIP、兼容状态、越界路径、大小写碰撞、额外成员、对象篡改与限制、无效深层 manifest，兼测 DT-13～15 回归。尚未在其他操作系统验证；尚未映射并写入 Agent 目标；客户端入口与 DT-19 导入事务未实现。

### DT-17 接收设备逻辑路径映射预览（2026-10-01）

新增 `sync_core/package/mapping.py`。包中 shared topic 和设置字段按适配器 allowlist 映射到接收端配置库及 Agent 配置路径；来源设备的 Agent 实例名和 root 不参与映射。候选来源为接收端现有设备配置或注入的只读 `HostEnv` 检测。仅唯一已安装候选自动选择；多候选必须选择所列 instance ID，传入任意路径不会成为映射。没有安装的 Agent 标 `not_installed`；可保存的配置库内容与 Agent 应用状态分开。冲突／已有覆盖不静默覆盖。配置提案复制接收端配置并仅加导入目标字段，保留接收端 device 标识与本机状态／记忆路径。安全公开结果只输出映射摘要，不返回完整设备配置和设置值。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_mapping.py tests/test_package_check.py tests/test_package_export.py tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt17-mapping-20261001-c` → **25 passed，0 failed，1.20 秒**。覆盖唯一路径匹配、双实例显式选择、伪造绝对路径拒绝、未安装提示、冲突阻塞、接收端身份保留及预览信息不泄露完整设备配置；并回归 DT-13～16。所有 Agent 发现都使用临时目录／注入的 Windows 环境，没有对开发机配置执行写入；Mac、真实另一设备、Tauri UI 和导入提交未验收。

### DT-18 只读差异与冲突决定核心（2026-10-01）

新增 `sync_core/package/conflicts.py`，比较包条目、接收端配置库、Agent 当前共享设置字段与规则受管区块。父版本必须与已校验父包的内容 ID 相同，且同一逻辑来源存在于父包，才参与该项三方比较；没有可信基线时只展示差异并要求逐项决定。排除或缺失条目不会生成删除。共享设置本机覆盖和 Agent 声明冲突不会自动覆盖；人工合并规则会再次执行凭据和本机路径策略。预览不返回本机配置正文或字段值。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_conflicts.py tests/test_package_mapping.py tests/test_package_check.py tests/test_package_export.py tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt18-conflicts-20261001-d` → **29 passed，0 failed，2.07 秒**。这是只读核心测试，不包含界面交互、写入、备份、恢复、全量 pytest 或其他操作系统验收；这些仍分别由 DT-19、DT-20、DT-26、DT-27 完成。

### DT-19 可恢复事务导入与本机 RPC（2026-10-01）

新增 `sync_core/package/importer.py`，在 `ApplicationService` 和 JSON Lines 协议注册 `package_import`。预览读取受支持目标并记录哈希；应用重新核验包身份，再用既有锁、事务 journal 和备份批量写入配置库、Agent 文件及接收设备配置。目标逐个回读校验后才更新已校验的本机父包。读回失败时事务按日志回滚；已提交操作可从历史撤销，父包也随操作一起恢复。落盘正确仍不证明 Agent 新会话已加载。协议核心已接入，但桌面迁移页面、进度交互和原生窗口验收在 DT-20。

定向验证（2026-10-01，Windows，项目虚拟环境 Python 3.13.14）：`.venv/Scripts/python.exe -m pytest -q tests/test_package_importer.py tests/test_package_conflicts.py tests/test_application_protocol.py tests/test_package_mapping.py tests/test_package_check.py tests/test_package_export.py tests/test_package_policy.py tests/test_package_format.py tests/test_core_import_direction.py --basetemp=tmp/run-dt19-import-20261001-e` → **59 passed，0 failed，4.61 秒**。覆盖协议边界、目标被更改后拒绝陈旧计划、事务中途写入失败的恢复、重复导入零变更、父版本再次参与三方比较和历史撤销；不代表全量测试、前端构建、跨平台或原生窗口验收通过。

## 六、已知限制

- 三机验收与零基础验收尚未执行，需要实机与外部远端。
- Codex 导出是参考快照，不是原生记忆数据库导入；未验证模型是否采用快照内容。
- 跨设备同步成功不等于工具已加载；需要新会话。
- 敏感检测是启发式的，首次发布共享内容前应人工复核。
- 独立加密备份目的地仍属于原可靠性计划，不因体验改造取消。
- 原新 Agent 接管只覆盖规则入口；本轮增加的 Codex／Claude skills、Codex MCP 和 Claude 可移植 Markdown 部署仅限各自适配器，未知 Agent 不因此获得这些能力。
- 版本号问答证明的是“这个会话读到了该入口”，不代表模型会遵守每一条规则。

## 2026-10-01 DT 无外部条件本轮集中验收

用户明确要求实现期间不自测，最后只选择核心功能集中自测。实现和边界详见 [本轮实施记录](desktop-local-implementation.md)。本轮没有执行全量 pytest；历史测试不计为本轮通过数。

环境：Windows 10 19045 x64，`desktop/.build-venv/Scripts/python.exe` 为 Python 3.14.0；临时文件与所有写入都在隔离测试目录，服务端用 SQLite 和注入身份验证器、模拟 HTTPS 传输，未连接真实 OIDC／用户服务器。

选择性主测试命令（2026-10-01）：

```powershell
desktop/.build-venv/Scripts/python.exe -m pytest -q tests/test_desktop_extensions.py tests/test_cloud_core.py tests/test_package_importer.py::test_package_import_commits_as_one_undoable_transaction_and_is_idempotent tests/test_package_importer.py::test_external_change_after_preview_rejects_without_overwriting_it tests/test_package_importer.py::test_mid_transaction_write_failure_restores_all_original_targets tests/test_package_importer.py::test_desktop_protocol_rechecks_then_applies_package_preview tests/test_application_protocol.py::test_protocol_schema_operation_allowlist_matches_runtime tests/test_application_protocol.py::test_json_lines_jobs_are_serialized_and_stream_progress tests/test_application_protocol.py::test_json_lines_shutdown_acknowledges_and_stops_accepting_requests tests/test_layout.py::test_legacy_import_preview_writes_nothing_then_copies_and_keeps_a_backup --basetemp=tmp/run-dt-final-core-20261001-b
```

当时文件中的选择共 20 项：**19 passed，1 skipped，4.60 秒**。跳过项为当前 Windows 账户不能创建符号链接；这不证明外部链接实机验收通过。首次运行 `...-a` 为 1 failed／18 passed／1 skipped，暴露 skills 单独导入被无关规则快照阻塞；修复后运行上述 `...-b` 通过。该修复只为包中实际有规则条目时生成规则目标快照。

主测试后针对发现的边界做了局部修正，仅补测相关场景，未扩大为全量：

| 新临时目录 | 选择场景 | 结果 |
| --- | --- | --- |
| `tmp/run-dt-final-hardening-20261001-c` | 技能复制／撤销、采集来源变化、Claude 快照恢复 | 3 passed，0.52 秒 |
| `tmp/run-dt-final-extension-paths-20261001-d` | 技能复制／撤销、排除类别、关闭范围不读取 | 3 passed，0.39 秒 |
| `tmp/run-dt-final-handoff-20261001-e` | 无 Git 交接查看／缺源码和依赖、RPC schema allowlist、服务器归属／撤销 | 3 passed，1.48 秒 |
| `tmp/run-dt-final-core-20261001-f` | 上述主测试选择，加上新交接场景 | 20 passed，1 skipped，4.10 秒 |
| `tmp/run-dt-final-upload-20261001-g` | 源包校验后变化仍上传已校验字节；加密上传幂等／下载／明文检查 | 1 passed，1.30 秒 |

補测均指定上述节点和全新临时目录。最后一轮新增 `test_portable_handoff_view_without_git_reports_missing_source_and_dependencies`；重新执行整个测试文件会多出该场景，不应据此改写原主测试通过数。TestClient 有一条 Starlette 对 httpx 测试适配的弃用警告，没有据此更换协议或增加依赖。

前端 `desktop/` 下 `npm run build`（TypeScript + Vite）和 `npm run lint` 均通过，包含最新交接查看入口。Python 编译和 `git diff --check` 的最终状态见下面产物记录。sidecar 隔离只读启动检查将 PATH 限于 System32，读取未配置状态、适配能力并正常退出；该检查没有执行 Git、写入真实 Agent 或调用 vault，不等于安装环境验收。

`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-secrets.ps1` 返回 **exit 1**：标记 `tests/test_application_protocol.py` 的规则凭据检测样例及 `tests/test_package_policy.py` 的敏感规则排除样例。这两份文件和样例在本轮开始时已存在；原样保留，未在报告输出值，未提交代码。不能把秘密扫描标为通过。

真实原生窗口、干净账户安装、Mac、第二台 Windows、真实 Agent 加载、OIDC／系统 vault、PostgreSQL 并发、容器镜像、服务器部署和备份恢复演练均未执行。用户已明确先做无外部条件部分。安装包是未签名开发预览，DT-01～40 的完整验收勾选不因本地代码／构建存在而完成。

### 本轮最终构建与产物（2026-10-01）

- Python 3.14.0，Node.js 22.22.3，npm 12.0.2，Windows 10 19045 x64。`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop-sidecar.ps1` 成功；冻结资源只纳入 common、templates、schemas 和 Codex／Claude 共享配置模板，以及代码／运行依赖。
- 将 Cargo bin 加入当前进程 PATH 后，在 desktop 执行 `npm run tauri:build`，最新代码和 sidecar 的 Windows release／NSIS 成功，Rust 编译 38.63 秒；有 MSVC 正常创建库信息的 linker warning。安装器未运行，未验证升级／卸载。
- 最新 sidecar 的只读检查在全新 `tmp/run-dt-sidecar-final-20261001-h` 目录执行，`AI_CONFIG_HOME` 指向该目录下 data，子进程 PATH 只有 System32。JSON Lines 返回未配置状态、4 类适配能力、shutdown_accepted，exit 0，未产生 device.json。它只验证冻结启动／资源导入／有序退出，不能证明已完成无 Python／Git 的全流程实机迁移。
- Python `compileall -q` 覆盖 sync_core、server、deploy 和本轮 Python 构建／发布脚本，通过；`git diff --check` 通过（只有换行转换提示）。最终秘密扫描仍为上述 2 个既有测试样例发现，exit 1，未提交代码。
- Windows 第三方归档收集 322 项、缺失 0，单独排除本机未安装的 53 个可选 npm 平台包。伴随 ZIP 大小 1,211,055 字节；来源与范围见 docs/third-party-licenses.md，不代替正式合规审核。

| 产物 | 项目内位置 | SHA-256 |
| --- | --- | --- |
| Windows 0.2.0 x64 NSIS 预览 | `desktop/src-tauri/target/release/bundle/nsis/AI Config_0.2.0_x64-setup.exe`（22,832,992 字节） | `fee166746a282a3006ec0a857ca06839878cb97d8e19a4347151a4e0ca0bc9eb` |
| 冻结 RPC sidecar | `desktop/src-tauri/binaries/ai-config-rpc-x86_64-pc-windows-msvc.exe` | `3fb59773f7000f4d6ffb16b023e1dfb84200080a3e9c119758df9d76b83fd378` |
| Windows 版权文本伴随归档 | `release-artifacts/AI-Config-0.2.0-Windows-NOTICES-full.zip` | `6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f` |

发布清单由 `scripts/release-manifest.py --artifact <上述安装器> --notices <上述版权归档> --output release-artifacts/AI-Config-0.2.0-Windows-manifest.json` 生成并核对：源 HEAD `69262fc0fe1c4c2145cdfa245ee1a716d7b4367b`，**dirty=true**，源文件集合摘要 `d1eb5a0a60e3a227b1a67ceeabb9e43121424b65e27fd93739e47fb29cc58664`；安装器、版权归档和清单中的源码文件哈希逐项一致。源码集合限 scripts／sync_core／server／desktop／schemas／templates／common／deploy，未读取用户运行目录；不把 dirty 产物称为正式发布。

任务／验收先更新后同步 PROJECT_STATUS.md。本地逐项核对通过：frontmatter 无重复字段、必填字段齐全，project_id=ai-config，updated 为未加引号的 2026-10-01，status=active，摘要非空，42 个 evidence 都是现存项目内稳定文件，无隐藏／运行目录、网址、越界或自引用。没有访问外部日常库或执行同步工具。本段记录摘要格式检查，不能计作功能验收。


## 设置页可读性与原内容／识别边界（2026-10-01）

本轮仅修改 desktop/src/App.css、desktop/src/index.css、desktop/src/App.tsx 的字体／对比度和说明，保留已有核心逻辑与用户未提交改动。正文／路径 16px、辅助文字至少 14px，减少远程字体依赖，路径按可用宽度换行。设置页说明本机配置库与 Agent 文件的边界、规则区块外原文保留、独立规则文件覆盖保护、设置字段覆盖、迁入采纳／移除和历史撤销，以及新会话加载核验；WorkBuddy 两个实例不承诺已经自动识别。官方文档链接与入口表在 docs/getting-started.md。

实际验证日期 2026-10-01，Windows 开发主机：

- 在 desktop 运行 `npm run build`、`npm run lint`：exit 0。随后 `npm run tauri:build`：exit 0，生成 Windows 0.2.0 x64 NSIS 未签名预览安装包。未安装或改写日常 Agent 配置。
- 首次 `py -3.14 -m pytest -q tests/test_agent_contract.py tests/test_verify_load.py tests/test_onboarding.py --basetemp=tmp/run-setup-readability-20261001-a`：11 failed／23 passed，失败均为全局 Python 3.14 环境缺少 tomlkit。未据此修改核心代码或安装依赖。
- 改用项目既有 Python 3.13.14：`.venv/Scripts/python.exe -m pytest -q tests/test_agent_contract.py tests/test_verify_load.py tests/test_onboarding.py --basetemp=tmp/run-setup-readability-20261001-b` → **34 passed，8.86 秒**。覆盖各规则适配器原文保留、写入核对、本机编辑保护、重复运行、撤销／退出接管与加载核验版本状态。均为临时目录／测试替身，不代表真实 Agent 加载。
- `.venv/Scripts/python.exe -m pytest -q tests/test_sync.py::test_config_preserves_provider_and_mcp tests/test_application_protocol.py::test_setup_preview_cannot_replace_an_existing_device_config tests/test_application_protocol.py::test_setup_uses_the_selected_custom_agent_root tests/test_migrate.py::test_unique_rules_are_never_touched_without_a_choice tests/test_migrate.py::test_adopting_moves_unique_lines_into_the_store_verbatim tests/test_migrate.py::test_keep_is_remembered_and_the_file_is_left_alone tests/test_migrate.py::test_a_duplicate_copy_is_removed_by_default_and_undo_brings_it_back --basetemp=tmp/run-setup-preservation-20261001-c` → **7 passed，0.70 秒**。补核对选定设置之外字段保留、首次设置防覆盖、实际所选路径、迁入／保留／移除与撤销边界。
- Chrome 使用实际 React 前端和临时只读 Tauri 替身、虚构 D:\Demo 路径，在 940×700 与 360×780 检查设置预览：定义列表实际计算字号 16px，页面无横向溢出；窄窗口预览标签与路径转为单列。截图和演示替身在 tmp/readability-preview，仅为布局检查产物，不作摘要 evidence 正本。没有真实 Agent 文件 I/O；此检查不代替原生 WebView、系统缩放、安装验收。
- `git diff --check`：exit 0，仅换行转换提示。`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-secrets.ps1`：exit 1，仍标记 tests/test_application_protocol.py 与 tests/test_package_policy.py 的既有检测样例，本轮未修改这些文件；未把扫描写成通过。未提交／推送，未运行全量 pytest。

旧 Windows 安装包及旧来源清单在 `release-artifacts/before-readability-20261001/` 保留。本轮新安装包仍为 `desktop/src-tauri/target/release/bundle/nsis/AI Config_0.2.0_x64-setup.exe`，**22,834,014 字节**，SHA-256 `001787b7e5886333a08fa17e40824fbb1728af938ad08b54ba7cd321bd183618`；新清单 `release-artifacts/AI-Config-0.2.0-Windows-readability-20261001-manifest.json`，源码摘要 `50cdd059c57b4ba9b9f1368745ca01ef5c828a208ceb9a81aec176421743497d`，dirty=true。既有版权伴随归档不变，SHA-256 `6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f`。用户需安装这次重建包才会看到新界面；现有已安装程序不会因仓库 CSS 改动自动更新。

真实 Agent 新会话加载（尤其 WorkBuddy）、原生窗口与安装、第二台 Windows／Mac、服务器和正式签名发布仍待验收；没有新增这些验收的完成声明。

交付前本地逐项自检：PROJECT_STATUS 必填字段／唯一字段／active 状态／未加引号的真实日期与 50 项 evidence 路径通过；安装包大小、SHA-256 和新清单中全部源码哈希一致。未使用外部日常同步工具。旧默认发布清单已备份后更新为本次新清单，使其与当前同名安装包一致。
## 2026-10-02 换机迁移工具包 P0 本机记录

执行环境：Windows 10，Python 3.14.0；当前工作树原有大量未提交的桌面、服务器与文档修改，均保留。方向改为 `MACHINE-MIGRATION-TASKS.md` 所述离线换机备份／恢复；旧桌面、服务器／云同步、受管区块同步标记为冻结，原验收记录仍属历史。

- MK-00：README 已提供到新任务清单的一步链接；七份旧任务／方案文档顶部加冻结提示，没有删除原正文。
- MK-02 本机实现：核心与冻结测试依赖分层；仅冻结范围变化时运行冻结 CI job；修正 `user_excluded` 过期测试断言；pytest 自动隔离 HOME 并清除 Agent 根目录环境变量；扩展共用的凭据检测正则，测试样例改为运行时拼接。
- `tmp/venv-mk02-core/Scripts/python.exe -m pip install -r requirements-test.txt`：成功，新建仅含核心依赖和 pytest 的 Python 3.14 环境。
- 在独立 HOME、USERPROFILE、CODEX_HOME、CLAUDE_CONFIG_DIR、AI_CONFIG_HOME 下运行 `tmp/venv-mk02-core/Scripts/python.exe -m pytest -q --basetemp tmp/run-mk02-core-20261002-c`：**349 passed，2 skipped，164.14 秒**。跳过冻结范围的依赖测试，不代表冻结范围已验收。
- `.venv/Scripts/python.exe -m pytest -q tests/test_secret_patterns.py tests/test_onboarding.py --basetemp tmp/run-mk02-secrets-20261002-b`：16 passed；此前 MK-02 相关定向测试 6 passed。
- `python scripts/check-secrets.py`：**0 findings**；`git diff --check`：exit 0（仅换行提示）。
- MK-01：负责人在本次会话明确授权向私有 `origin` 的 `wip/` 分支推送；`gh repo view loonslo/ai-config --json isPrivate,visibility,nameWithOwner` 返回 `isPrivate=true`。按核心／冻结代码／文档／测试分为四个本地提交（`6b004af`、`0d3b421`、`089be70`、`febc522`），先运行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-secrets.ps1`，结果 0 findings；`git push -u origin wip/machine-kit-baseline` 成功。`git rev-list --count origin/wip/machine-kit-baseline..HEAD` 为 0，推送后工作树干净，后续开发切到 `feat/machine-kit`。未推送 main，未用 `--force`。

此时未验证：GitHub Actions 的 Windows/macOS `core` 与 `frozen` job；下节记录随后首次 CI 运行结果。未读取真实 Agent 状态文件、未运行备份／恢复、未进行跨机或新手试用。本节的测试只说明本机代码范围，不代表整个迁移工具包完成。

### P1 路径、分档、配置、包格式与夹具（2026-10-02）

架构边界：`sync_core/machine/` 独立于已冻结的 `sync_core/package`、`cloud`、`application`；路径层只归一和映射，目录层按批准项放行，配置缺失采用安全默认，包层只写新的 zip 格式并对所有成员有界校验。WorkBuddy 条目保持 `draft`，默认不采集。目标真机目录和私有状态尚未读取。

- 新增 `paths.py` 的 Windows／Mac 规范化、Git 主检出根、最长前缀根映射与真实大小写；`catalog.py` 的默认拒绝目录；`config.py` 的可选本地配置和占位示例；`bundle.py` 的内容标识、原样字节、`.partial` 写入、有限读取与压缩包完整性校验；`tests/_machine_fixtures.py` 与静态导入守卫。
- 在隔离 HOME 和全新 `--basetemp tmp/run-mk15-20261002-b` 中执行 `tmp/venv-mk02-core/Scripts/python.exe -m pytest -q tests/test_machine_paths.py tests/test_machine_catalog_config.py tests/test_machine_bundle.py tests/test_machine_import_direction.py tests/test_machine_fixtures.py`：**37 passed，1.17 秒**。覆盖 zip 成员路径、大小写／NFC 重名、符号链接、压缩方式、大小与压缩比上限、JSON 重复键／非有限数／未知版本、清单不符、损坏中央目录、无覆盖发布、稳定内容标识和中文往返。
- `MK-10` 的真实 Claude 路径 self-check 需单独只读授权；`MK-11` 的整包哨兵验收依赖后续采集器；`MK-12` 的 11 个核心项目真机只读预览未运行。`MK-13` 的 FAT/exFAT U 盘行为尚未实测；本轮只完成本地包格式验收。
- 首次推送的 GitHub Actions run `36963621887` 失败：macOS 核心与冻结 job 在 pytest 创建 `tmp/ci-*` 前发现干净 runner 缺 `tmp/`，350 项均为 setup 错误，测试用例没有实际运行；Windows job 被取消。已在 CI 配置的两个 job 中加入创建 `tmp/` 步骤，尚未推送或复测，MK-02 CI 门槛继续未通过。

### P2 软件与①档采集的只读预览（2026-10-02）

- MK-20：软件清单函数仅运行本机已安装程序的版本查询、全局 npm 包名／版本查询，不联网；进程调用可注入、单个命令最多 10 秒，符号链接能力只在系统临时目录试建并清理。测试 `tests/test_machine_collect_records.py` 在隔离 HOME、`--basetemp tmp/run-mk20-20261002-b` 下 1 passed。本机读取得到 Windows AMD64、Node 22.22.3、npm 12.0.2、Git 2.54.0、uv 0.12.10、pnpm 10.29.3、cargo/rustc 1.98.1、winget 1.29.380；6 个 npm 全局包名，Claude Desktop 内置 Claude Code 版本目录 2.1.284／2.1.286。Codex Desktop 与 CC Switch 版本获取方式仍未核实，记 `null`。`reports/software.json` 要到 MK-26 组包时生成。
- MK-21：`collect_tier1()` 只读 Claude/Codex 的批准项；设置只派生白名单字段，WorkBuddy 草案与 Claude 信任文件、Codex 会话库均不读取。沙箱生成 zip 后验证哨兵零出现、受保护文件零读取、源目录零变化、`content_id` 稳定和按助手过滤。`tests/test_machine_collect_tier1.py` 在隔离 HOME、`--basetemp tmp/run-mk21-20261002-e` 下 **4 passed，2.03 秒**。
- 本机只在内存中预览，没有写 zip：91 个条目，其中规则 2、设置字段 2、Claude 记忆 62、Codex 技能文本 25；93 个已读源文件的哈希和修改时间在二次读取后全部一致；排除疑似凭据的记忆 1 个、非文本技能 1 个，警告 0。规则两份各 7,576 B，重复统计均为 41/111。内存预览没有读取 `~/.claude.json` 或 Codex sqlite，也没有输出人设／记忆／令牌内容。
- 这与 2026-10-01/02 的旧基线 61 个记忆／7 目录、5 个非文本技能不同。负责人本次会话确认以当前快照继续核对；原数值保留为历史参照。整包报告、正式备份及跨机还原仍未验收。
- MK-10 单独获得本次会话 G2 只读授权后运行 `tmp/venv-mk02-core/Scripts/python.exe scripts/machine.py paths --self-check`：29 个 Claude 项目路径键；15 个含转录的目录中有 8 个与登记路径编码匹配、7 个无对应登记键，长路径不支持项 0。对**登记路径且存在转录目录**的 8 个样本，推导一致率 8/8；其余 7 个目录可能来自不同工作目录，未逐个核对、也未读取转录内容。此结果不代表所有转录目录均由信任登记键覆盖。
- 增加源文件二次哈希／mtime 检查与密钥命中／符号链接沙箱用例后，统一运行 `tmp/venv-mk02-core/Scripts/python.exe -m pytest -q <tests/test_machine_*.py 的文件列表> --basetemp tmp/run-mk21-20261002-g`：**43 passed，4.33 秒**。此前一次直接把通配符传给 Windows 版 pytest 的调用未展开文件名，0 项运行；本次改为 PowerShell 枚举测试文件后通过。`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check-secrets.ps1` 为 0 findings，`git diff --check` 与 Python 编译检查通过。

### P2 项目档案采集与真机只读预览（2026-10-02）

- MK-22 新增 `collect_projects.py`：核心文件夹与 Git 根分别标识，同一个 Git 根下的核心文件夹仍保留独立档案；Claude 信任只提取两个布尔字段并按规范化路径合并，Codex 只取核心项目的 `trust_level`，SQLite 通过 `mode=ro` 仅读 `project_roots.path` 和 `threads.cwd`。项目本地权限文件限深度 2，按最长核心路径归属并去重；会话只统计文件名／cwd，不读转录正文；`known_folders()` 仅返回规范化路径。派生报告为 `reports/projects.json`，信任字段与权限原文件可进入新 bundle；命中凭据特征的权限文件会跳过。
- 合成 HOME 的 `tests/test_machine_collect_projects.py` 在全新 `--basetemp tmp/run-mk22-20261002-g` 下 **4 passed，3.29 秒**；覆盖凭据哨兵不进包、受保护诱饵不被打开、源目录不变、数据库缺失、共享 Git 根仍保留两个项目档案。全部 machine 定向测试此前为 46 passed；新增第 4 项后待合并复测。
- 负责人本次会话先授权 MK-22 对 `~/.claude.json` 两个信任字段、Codex `config.toml` 核心信任字段与 sqlite 路径／cwd 计数的只读核对，随后又授权项目本地权限文件与 Claude Desktop cwd 登记、转录目录文件名计数；未授权真实备份写入或远程推送。预览只在内存建立 `BundleWriter`，没有 `finalize()`、没有 zip 输出。首次预览重复统计了共享 Git 根下的文件，修正最长核心路径归属后再运行。
- 修正后：11 个核心文件夹均存在，对应 8 个不同 Git 根；`~/.claude.json` 规范化项目 21 个，其中 12 个存在、16 个已信任；Codex sqlite 项目根 12 个且均存在，线程 cwd 行 545；Codex 核心信任在 11 个档案均有记录。权限文件 7 个、allow 规则 135 条、当前绝对路径规则 9 条。内存中 11 个项目档案与 27 个条目，警告 0。Claude Desktop `claude-code-sessions` 目录当前有 0 个 JSON；旧基线 46 个，原因未核实。Claude 项目转录文件按核心目录计数总计 41，线程 cwd 落在核心目录内 426；这些是当前计数，不代表会话可迁移。
- 与 §4.3 的历史基线差异按负责人先前确认的当前快照记录，不覆盖旧基线。实际 bundle 组装、`reports/projects.json` 写入 zip、真实文件哈希／mtime 全量复核与跨机还原待 MK-26 及后续任务。
- 汇总复测：PowerShell 枚举 `tests/test_machine_*.py` 后，`py -3.14 -B -m pytest <文件列表> -q --basetemp tmp/run-mk22-20261002-h` 为 **47 passed，4.92 秒**；`scripts/check-secrets.ps1` 为 0 findings，`git diff --check` 与 `compileall` 通过。项目内摘要契约自检：必填字段、唯一字段、日期／状态和 62 个现存稳定 evidence 路径均通过；未运行外部日常库同步工具。

### WorkBuddy 分档与 P2 报告／组包（2026-10-02）

- MK-14：本次获得 G7 只读结构调研授权后，列出两个实例和项目级目录的元数据，仅读 settings 顶层／二级键名、类型和集合长度。没有打开人设／记忆／skills 内容、keyblob、凭据、账户 UUID 目录或数据库。官方产品记忆、系统设置与 Skill 文档没有证明 `.workbuddy[-ai]` 的文件加载时机；调研与引用保存在 `docs/machine-migration-workbuddy.md`。负责人随后批准安全文本的 `manual` 分档，enabledPlugins 仅记名称，sandbox／claw／账户状态排除；未批准自动恢复或加载实验。
- MK-23：获批后实现 `collect_workbuddy.py`，只采集批准的安全文本，排除迁移标记、VCS、符号链接、非文本和凭据命中。初次真机内存预览发现不同子目录在 archive 中重名，修正为保留核心项目内相对路径；未写 zip。修正后内存预览 76 条（当时目录分类为人设 9、记忆 40、技能文本 27；随后将全局 `MEMORY.md` 正确归入 memory，条目总数不变）、项目级 38，疑似凭据排除 1、警告 0，已读源文件二次哈希／mtime 全部一致。真实加载与还原仍未验证。
- MK-24：`collect_reinstall.py` 仅记录 CC Switch 技能名、体积、Git 远端（移除用户信息／查询串）与 HEAD，Claude 插件／marketplace 名称与安装版本、Codex MCP 的程序名／去敏端点／参数个数／env 键名，hooks／notify 只记存在；WorkBuddy 仅记已批准的插件名称和设置存在标志。真实机只读预览识别 **35 个 CC Switch skills、6 个 Codex MCP**，与旧基线相符；Claude skills 符号链接不跟随。合成报告低于 1 MB，哨兵零出现。
- MK-25：`collect_login.py` 生成只有变量名、主机名与重新取得位置的清单。凭据文件、SSH 私钥、CC Switch 数据库均不打开。合成报告的受保护诱饵零读取、哨兵零出现、源目录不变；本机只读预览清单为 35 行、3793 B，OAuth 主机 5 个。具体密钥值未输出。
- MK-26：新增 `backup.py` 与 `scripts/machine.py backup`，默认内存预览，`--apply --out` 才写；保存目录必须已存在且位于所有助手根与核心项目之外。集成六份报告、源文件二次哈希／mtime 核对、写后包校验与 SHA-256，支持 `--agents` 与 `--name`。两个旧启动器仅在首参数 `machine` 时转发，PowerShell 文件保持 CRLF。恢复命令尚未实现，summary 明确该边界。
- 沙箱：`py -3.14 -B -m pytest tests/test_machine_backup.py tests/test_machine_catalog.py tests/test_machine_collect_workbuddy.py tests/test_launchers.py -q --basetemp tmp/run-mk26-20261002-a` 为 **11 passed，5.79 秒**；全 machine 文件列表加 `tests/test_launchers.py`、`--basetemp tmp/run-mk26-20261002-b` 为 **59 passed，11.01 秒**。验证完整 zip、六份报告、哨兵零出现、源目录不变、内容标识稳定、单助手零越界读取、禁止源目录内输出、预览后源文件变化拒绝写入。此前旧 WorkBuddy 草案断言导致 1 failed／49 passed，已按本次批准范围修正后通过。
- 真机 CLI 只读预览：使用被 Git 忽略的本地配置指定 D12 的 11 个项目，目标桌面、文件前缀 `AI备份`；命令退出码 **3**，符合预览约定。内存共 **200 条**：Claude 79、Codex 38、WorkBuddy 12、WorkBuddy AI 65、报告 6；①档 192、②档 8；排除 3、提醒 0，已选源文件二次核对通过。没有生成桌面 zip。第一次外围脚本错误地按 UTF-8 解码 Windows 本地编码输出，CLI 本身正常退出；外围调用改用 `-X utf8` 后读取成功，文件名前缀也核对为正确 Unicode。真实 `--apply`、zip 大小／SHA-256、U 盘和 M1 人工核对仍待 G3 与后续验收。
- 最终复测加入 WorkBuddy 路径标记与正确的 MEMORY 分类后，`--basetemp tmp/run-mk26-20261002-c` 为 **59 passed，12.17 秒**。秘密扫描 0 findings，`git diff --check`、`compileall`、PowerShell 原生语法解析（0 errors）与 Git Bash `bash -n ai-config.command` 通过；PowerShell 文件为 CRLF。项目内摘要契约 74 个稳定 evidence 路径与必填／唯一字段、日期、状态检查通过；未使用外部日常同步工具。`origin` 所属 `loonslo/ai-config` 再核对为 PRIVATE；未作本轮推送。

### MK-26 真机备份与 M1（2026-10-02）

- 本次 G3 明确授权后运行 `py -3.14 -X utf8 -B scripts/machine.py backup --config <Git 忽略的本地配置> --out <用户桌面> --name AI备份 --apply --json`，Windows／Python 3.14.0，退出 0。唯一新增桌面文件 `AI备份-20261002-084533.zip`：**723584 B**（小于 5 MiB），**200 条、11 个项目**；Claude 79、Codex 38、WorkBuddy 12、WorkBuddy AI 65、报告 6；①档 192、②档 8。排除 3（疑似凭据 2、非文本 1），采集提醒 0。
- SHA-256 `9c3fdab00f7a706491f51520df6889c84cb6dc8bd98417ff230d68804b878002`；content_id `c21ce1678095fce613e468107c0f43e88ddbaa871b232beafb923ddcebbc0c81`。写前／写后已采集源文件 hash／mtime 全部一致；发布时及独立复核的 `validate_bundle` 均通过，独立 SHA-256 一致。未改写助手源数据。
- 从 ZIP 仅读取 `reports/summary.md` 到被 Git 忽略的临时审阅文件并打开，ZIP 与摘要交负责人过目；负责人本次会话明确“确认范围，继续 P3”，**M1 通过**。临时报告和真实个人内容不进入 Git 或 PROJECT_STATUS evidence。
- 当前快照允许日常变化；旧基线差异与未知桌面版本已注明。不代表可恢复、助手加载成功、U 盘发布或跨机验收通过。

### MK-27 新手备份向导（2026-10-02）

- `guided.py` 提供可注入问答、禁用词扫描、路径拖入清洗、桌面解析及本地时间；Windows 使用 SHGetKnownFolderPath 的 Desktop ID，并依次回退已有 Desktop／主目录。`guide_backup.py` 复用同一备份引擎，按助手与存在的工作文件夹选择，排除主目录本身／配置排除项，只有最终确认后写新 ZIP。无配置也能运行；异常画面及日志不记录异常值、局部变量或个人正文。摘要／登录清单正文同步改为普通用语；高级命令放折叠详细信息。
- 官方接口核对：<https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath>、<https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid>（2026-10-02）；Desktop GUID 为 B4BFCC3A-DB2C-424C-B029-7FE99A87C641。
- 隔离 HOME、全新目录运行全 machine 测试与 `tests/test_launchers.py`：`py -3.14 -B -m pytest <tests/test_machine_*.py 文件列表> tests/test_launchers.py -q --basetemp tmp/run-mk27-20261002-b` → **66 passed，21.27 秒**。新增向导 7 项覆盖全程回车与专家 content_id 一致、最终确认前 q 零写入、无配置、少选助手零读取、桌面各级及禁止源目录内输出的回退、拖入路径、异常哨兵不泄露；源目录保持原样、ZIP 校验与哨兵检查通过。后续补入工作文件夹排除断言的定向复测另记。
- `scripts/machine.py guide --help` 正常，仅公开 backup 选择。真实双击及未改过执行策略的环境仍待 MK-28／44，macOS 待 MK-61；未以沙箱替代实机验收。

- MK-27 最后定向复测（补入主目录／不存在／重复／scratch 工作目录过滤断言）：`py -3.14 -B -m pytest tests/test_machine_guided_backup.py -q --basetemp tmp/run-mk27-20261002-c` → 7 passed。秘密扫描 0 findings，diff 检查通过；本地摘要契约 77 个证据路径及字段检查通过，未调用外部同步工具。

### MK-28 启动器实现（2026-10-02）

- 标准库 `scripts/start.py` 共用仓库 .venv 与大小写不敏感的 requirements SHA-256 戳记，低于 Python 3.11／找不到 Python／建环境失败／安装失败均三段式说明并退出 2，只在项目 .venv 安装依赖；参数原样传给 machine.py。Windows `备份.cmd` 为 ASCII／CRLF，不调用 .ps1 或修改执行策略；缺 Python 的说明来自 UTF-8 BOM 文本，由内联 PowerShell 输出。成功及向导取消／失败已在结果页等回车，只有准备失败追加 pause，保证正常流程五次回车。Mac 两个 .command 已设 Git 100755／LF。quickstart 为一页备份说明，恢复入口与系统拦截未实测项明确保留。
- `py -3.14 -B -m pytest tests/test_start_bootstrap.py tests/test_launchers.py -q --basetemp tmp/run-mk28-20261002-a`：**14 passed，0.26 秒**。用假的进程执行器验证 stamp 只在安装成功后写入、就绪不重装、失败边界和含中文／空格路径的参数传递；旧启动器用例保留。Git Bash `bash -n` 两个 .command 通过；秘密扫描 0 findings、diff 检查通过。
- 本机 cmd.exe 仅读运行缺 Python 提示片段，退出 0、中文三段式完整；外围首次转义失败、随后错误使用 GBK 解码，改用脚本文件与 UTF-8 后核对成功。没有运行实际 guide backup，没有读取真实助手路径或写 zip。此检查不是 Windows Terminal 或资源管理器双击验收，也不代表默认执行策略／SmartScreen／Mac 已通过。
- MK-28 真机另需本次 G3＋G2；资源管理器双击需实机操作。当前未获该授权，保持部分完成；恢复实现可按已确认 M1 范围继续。

### MK-30 恢复前检查（2026-10-02）

- 只读解析经过有界校验的 ZIP，重新按分档目录约束生成目标，拒绝未知字段／目录、受保护名称、父路径跳转、链接与 Windows 特殊文件名。核心项目与记忆 Git 根分开映射；记忆目录按目标 Git 根重新推导并复用 Windows 大小写变体。目标助手未初始化时 blocked，不创建目录；已初始化但空的目标为 new（此边界优先于任务中“空 HOME 全 new”的简写）。按字段比较设置，生成信任与安全设置清单哈希；可输出普通用语检查／后续清单。进程检测可注入，软件主版本不符／缺失有提示。
- `py -3.14 -B -m pytest tests/test_machine_preflight.py tests/test_machine_import_direction.py -q --basetemp tmp/run-mk30-20261002-c`：**5 passed，7.17 秒**。覆盖 new／differs／找不到项目、目标零变化、缺助手根、单助手筛选、运行程序、危险路径、Windows→Mac 样例。前两轮揭示记忆条目实际位于 files/projects 与测试目标未初始化 Git 根的问题，按实际采集格式与目标 Git 初始化修正后通过。
- 新增专家 preflight 命令，默认只打印；显式 out-dir 可在源目录之外新增两份报告，已有报告拒绝覆盖。未访问真实目标 HOME、未运行 restore、未验证真实 Mac。

### MK-31 恢复写入核心（2026-10-02）

- 预先构造 PlannedChanges，保留检查时目标 hash；白名单字段合并保留未知设置，默认保留不同字段，整文件冲突写 .from-bundle（该位置已存在且不同则跳过）。只有明确 overwrite／prefer-bundle 才替换，confirm 类未确认则跳过；安全清单可绑定哈希。所有写入通过现有 transaction 的锁、写前备份和 journal；写前及逐文件重新拒绝路径链接、运行中的应用、目标变化，写后重读核对。权限文件被 Git 跟踪只提醒。缺助手根或项目不创建。真实写入仍须 G4。
- 初次全局 Python 3.14 缺 tomlkit，测试 collection 失败；改用既有核心隔离环境（Python 3.14、requirements-test 已安装），不安装全局依赖：`tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_apply.py tests/test_machine_preflight.py -q --basetemp tmp/run-mk31-20261002-b` → **5 passed，14.53 秒**。验证初次恢复、重复无操作、冲突保留＋另存、明确覆盖、进程拒绝、目标后续修改拒绝及中途失败回滚。只写夹具 HOME。
- 记忆、信任与 WorkBuddy 扩展在 MK-32…34 实现；WorkBuddy manual 文本默认不写，新增显式 --workbuddy-files 仅复制批准候选并保留人工加载核验，避免把 G7 的 manual 分档变成默认自动恢复。专家 restore 默认只打印计划。

### MK-32 Codex 信任还原（2026-10-02）

- 只处理 bundle 核心项目存在者的 trusted 条目，默认不写。显式 codex-trust 要求 confirm-trust 与刚检查的清单哈希完全一致；应用前再次检查清单未变、项目仍存在。用 tomlkit 追加项目字段，保留注释／顺序与未知项；Windows 路径小写并识别大小写／分隔符已有变体。不同信任级别保留目标并报冲突，不接受 overwrite 绕过；与普通设置合并到同一个事务计划。
- `tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_trust.py tests/test_machine_apply.py -q --basetemp tmp/run-mk32-20261002-a`：**4 passed，10.24 秒**。验证哈希不符拒绝、注释／未知项保留、仅预期项目、重复无操作、已有 untrusted 保留、展示后清单变化拒绝。找不到项目不进入信任清单，由 MK-30 用例覆盖。无真实目标写入或 G5 确认。

### MK-33 Claude 记忆还原（2026-10-02）

- 核心项目记忆默认加入恢复计划；先映射存在的核心文件夹与 Git 根，再按目标原生路径推导目录；Windows 复用已有大小写变体。索引不合并，冲突保留现有并写 .from-bundle、提示手动整理；写前再次检查核心项目仍存在。
- `tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_memory_restore.py tests/test_machine_apply.py -q --basetemp tmp/run-mk33-20261002-a`：**4 passed**。覆盖大小写变体不重复建目录、MEMORY.md 冲突保留、原样字节恢复及 Windows→Mac 目标路径样例（运行环境仍是 Windows，不代表真实 Mac）。

### MK-34 WorkBuddy 手动候选恢复（2026-10-02）

- 按已批准 manual 分档，默认跳过 WorkBuddy；专家显式 --workbuddy-files 才将批准的人设／记忆／技能安全文本按原相对路径写回两个独立实例及映射后的项目。仍用 MK-31 的进程门禁／事务；没有 settings 字段、AGENTS.md、应用标记或账户文件写入。结果明确要求打开 WorkBuddy 核对加载，文本落盘不代表自动加载。
- `tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_workbuddy_restore.py -q --basetemp tmp/run-mk34-20261002-b`：**1 passed，3.31 秒**。验证默认不写、显式恢复原样字节及项目相对目录；keyblob／security／app／数据库／settings 诱饵零读取、字节不变；未新建 AGENTS.md 或迁移标记。初次用例错误调用 ReadTracker 不存在的 close，删去后通过（零读取断言在测试主动核对诱饵字节之前执行）。
- 真实 WorkBuddy 加载／人工识别仍未验收，MK-34 保持部分完成。

### MK-35／MK-36 自动核验与撤销（2026-10-02）

- verify 逐条核对恢复后的规则／记忆／本地权限／WorkBuddy 原样字节、实际选中的白名单字段和 Codex 信任，支持部分助手 SKIP；主版本核对、重装清单完成标记独立记录。登录、实际加载、未选择的确认项仍 MANUAL，不冒充 PASS。规则问答从不少于 12 字的唯一行随机选取，提供新会话问题与原句对照；未读取会话事件或写 hook（G6 可选项未执行）。
- undo 仅列 machine_restore 的未撤销记录；共用 select_operation 增加可选 operation_filter（默认旧行为不变），使用 plan_restore＋transaction，不调用旧 restore()。撤销前校验备份限定于 state/backups、数字文件名与已记录目标边界，拒绝链接／后续修改／运行程序；撤销写后核对字节，并以 machine_undo 记录避免重复撤销。新建文件删除，原文件逐字节恢复；目录可以保留为空，不声称删除整个工作目录。
- `tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_verify_undo.py tests/test_ux_flows.py tests/test_machine_import_direction.py -q --basetemp tmp/run-mk35-36-20261002-c`：**54 passed，20.48 秒**。完整沙箱恢复含确认设置、信任、记忆、WorkBuddy；自动项一致，破坏规则文件 FAIL，撤销拒绝后续修改，修复后完整撤销，目标文件回到之前字节，再次检查状态与还原前一致；共用旧撤销接口回归通过。上一轮错误指定不存在的 tests/test_restore.py，0 项运行，随后改为现有接口回归文件。
- 真实目标／净室撤销仍未运行，MK-36 保持部分完成；本次未读取真实助手目录。专家 verify／undo 接口已提供，真实 apply 仍需 G4。

### MK-37 恢复向导与 P3 合并验证（2026-10-02）

- 恢复向导复用 preflight／plan_restore／apply_restore／verify／undo。只在指定桌面、下载、启动目录／上级及可移动盘根的顶层查 ZIP，发现阶段仅读有界 manifest；选定后完整校验。可拖入路径、选择助手、补整体缺失的工作文件夹位置、等待关闭程序。安全设置／信任／WorkBuddy 文本默认跳过，各自明确选择后绑定刚显示的清单；向导不提供覆盖选项。总确认后写入，结果保留冲突路径、三份说明及人工后续事项；再次打开可撤销，失败日志不记录异常值／局部变量。
- Windows 恢复入口 ASCII／CRLF，带引号的 %~1 转交路径；空参数让向导自动查找。Mac 恢复入口 LF／Git 100755，拖文件进窗口；quickstart 恢复节已补。新版备份摘要指向恢复入口，首份真实 ZIP 是旧生成时报告，原文件保持不变。真实跨机与新手试用仍未验收。
- `tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_guided_restore.py tests/test_machine_guided_backup.py tests/test_launchers.py tests/test_start_bootstrap.py -q --basetemp tmp/run-mk37-20261002-b` → **25 passed，20.86 秒**。覆盖全程回车与专家文件字节等价、最终确认前 q 零变化、冲突另存、程序运行时等待、撤销回原字节、显示的信任清单变化拒绝、坏文件拒绝、顶层发现／拖入路径与禁用词扫描。
- 专家 CLI 测试 `--basetemp tmp/run-mk37-cli-20261002-d`：**2 passed，3.30 秒**。合成 HOME 中只读检查／预览无写入，明确信任及 apply 后 verify 通过，再 undo；恶意 manifest 指向 auth.json 在目录白名单阶段拒绝，受保护目标零读取。初次该恶意夹具漏填 logical_path，修正用例参数后通过。
- 合并：PowerShell 枚举 `tests/test_machine_*.py`，`tmp/venv-mk02-core/Scripts/python.exe -B -m pytest <文件列表> tests/test_launchers.py tests/test_start_bootstrap.py -q --basetemp tmp/run-p3-machine-20261002-a` → **91 passed，64.10 秒**。全部测试隔离 HOME／助手根环境变量；没有真实恢复或新双击备份。秘密扫描 0 findings，diff 检查、compileall、三个 .command 的 Git Bash 语法检查通过。
- 净室准备清单已保存 `docs/machine-cleanroom-checklist.md`，未因此标记 MK-40 完成。MK-28 真机另需 G3＋G2，MK-40 的环境须 G8，MK-41 每次真实 apply 须 G4，信任须 G5，新手试用须 G9。没有运行真实工作区恢复、创建 Windows 用户／虚拟机、读取会话正文、推送新分支或实施可选 P7。

- P3 交付前本地摘要自检：必填／唯一字段、未加引号日期、active 状态与 102 个稳定 evidence 路径通过，未使用外部日常同步工具。
