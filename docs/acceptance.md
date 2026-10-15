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

### MK-12／MK-26 交付复查与隐私修正（2026-10-02）

- 复查发现配置排除仅用于向导选择文件夹，专家采集未统一应用。现按完整／主目录相对／核心项目相对／助手根相对路径匹配；HOME 本身始终排除，`/**` 同时排除根目录。遍历前剪枝、候选读取前过滤，多个采集器的排除记录去重；不会读取被排除文件正文。隔离 HOME 的哨兵断言验证项目子目录与自建技能均零读取，源树未变。
- 定向：核心 Python 3.14 隔离环境，`tmp/venv-mk02-core/Scripts/python.exe -B -m pytest tests/test_machine_exclusions.py tests/test_machine_backup.py tests/test_machine_collect_tier1.py tests/test_machine_collect_workbuddy.py tests/test_machine_collect_projects.py -q --basetemp tmp/run-mk12-excludes-20261002-a` → **14 passed，14.04 秒**。剪枝完善后全 machine＋启动器／bootstrap → **93 passed，70.25 秒**，`--basetemp tmp/run-machine-final-20261002-b`。历史排除基线未全部重新核对，MK-12 不标为全部验收。
- 只读检查已生成首份 ZIP，发现 **4 个文件命中邮箱格式**；不输出匹配值，不判定这些是否为实际邮箱或示例／标识，按 §5.6 一律保守排除。原检测覆盖密钥而遗漏邮箱／URL 用户信息，首份 ZIP 的完整性验证及原 M1 范围确认保留为历史，不能作为隐私验收通过。未改变源数据或删除原 ZIP。
- `privacy.py` 对邮箱、URL 用户信息、Unicode 转义及原有 SECRET 特征检测；采集器排除命中文本，预览／发布前检查全部文件、报告和元数据，恢复在读取目标文件前拒绝含私人信息的旧包。邮箱／URL 用户信息不能通过逐文件秘密例外放行，最终输出仍受整体门禁约束。无法证明安全的报告／路径直接拒绝，错误不带匹配值；不改写源文本。
- 首轮隐私定向 **1 failed／15 passed**，暴露整文件采集未识别转义邮箱，完善检测后 `tests/test_machine_privacy.py` → **8 passed，9.23 秒**，`--basetemp tmp/run-machine-privacy-20261002-b`。新增覆盖多类采集、转义、路径例外不能放行邮箱、报告／元数据与预览后改动拒绝，以及旧包在目标读取前拒绝。
- 最终合并：PowerShell `$machineTests = @(rg --files tests -g 'test_machine_*.py')`，`& tmp/venv-mk02-core/Scripts/python.exe -B -m pytest @machineTests tests/test_launchers.py tests/test_start_bootstrap.py -q --basetemp tmp/run-machine-privacy-full-20261002-c` → **101 passed，69.89 秒**。全部隔离 HOME，未跑真实恢复；diff 检查通过、`scripts/check-secrets.ps1` **0 findings**。共用撤销接口的 54 项回归沿用同日已执行记录，本次未重复冻结范围全量测试。
- 负责人在修正摘要及“保留 196 条／11 项目、排除 4 条”的说明后明确授权 **本次修正版 G3**。只读取原 ZIP 并验证原 SHA-256，重建批准的既有快照，未再次读助手目录／白名单数据库，未刷新源数据。额外排除：项目本地操作许可 1、WorkBuddy 记忆 1、WorkBuddy AI 人设 1、项目 WorkBuddy AI 技能 1；对应文件正文完整移除。项目权限文件／规则／绝对路径计数按保留内容重算，其余机器画像仍为原快照；摘要明确标注此来源。
- 实际修正版 `AI备份-修正版-20261002-211502.zip`：**668504 B，196 条，11 项目，排除 7**；Claude 78、Codex 38、WorkBuddy 11、WorkBuddy AI 63、报告 6。SHA-256 **`b7b97f841e03020b0aab81c0f09fca6fb3c23ec2ac0664fe488dd473338703c7`**；content_id **`d85c1a273a2a40475bd5d9326f40dbd68675a5893c17659eabc4fd02dfbf7962`** 与批准前内存预览一致。发布后独立有界读取／哈希检查通过，私人信息命中文件 **0**、元数据 **0**；原 ZIP SHA-256 仍为 `9c3fdab00f7a706491f51520df6889c84cb6dc8bd98417ff230d68804b878002`，原包保留。正则检查通过不保证发现所有形式的私人信息，仍须保管为个人备份。
- 负责人已回复“暂时没有净室”。MK-40／41／42／44 等待环境，真实加载、双击、U 盘、Mac 及 CI 均不因此完成；未在日常工作区恢复、未推送 feat 分支、未调用外部日常同步工具。
- 本次本地 PROJECT_STATUS 契约自检：必填／唯一字段、真实未加引号日期、waiting 状态、非空概览／进展／下一步与 **105 个**现存稳定 evidence 路径通过。未使用外部同步工具；该检查仅确认摘要格式和证据路径。


## 2026-10-08 桌面原样离线备份恢复（OF-01～04）

- 负责人本次明确：只保留换机 ZIP 的原样备份恢复能力，以桌面客户端为唯一用户入口；云端冻结，命令向导不作为交付方式。当前任务正本为 `docs/desktop-offline-migration.md`，2026-10-02 的桌面冻结范围已被此次决定取代；历史测试和真机备份没有重新验收。
- 实现：React 改为备份、恢复、恢复记录三页；助手选择、项目选择／目标映射、安全设置与信任确认、WorkBuddy 文本选择、ZIP 选择／拖入、核验与撤销均接入 MachineProtocol。桌面 sidecar 只接受五个 machine 操作，云端与旧 `.aiconfig` 操作被拒绝。原 `.aiconfig` 文件关联从新构建配置移除，不接管所有 ZIP 的系统关联。用户无需外置 Python 或 Git，源码旧脚本仅为历史开发兼容。
- 环境：Windows 10 19045 x64，现有 `desktop/.build-venv` Python 3.14.0、pytest 8.4.2；构建复用现有锁定依赖，无新增运行依赖。最初直接 `py -3.14` 缺少 tomlkit，测试未收集成功；随后改用已具备依赖的 3.14 构建环境。一次合并回归发现旧 RPC 子进程测试仍要求 import_config，已将测试改为当前 machine_detect 及合成目录检测。
- 实际回归：`desktop/.build-venv/Scripts/python.exe -B -m pytest tests/test_machine_desktop.py tests/test_application_protocol.py tests/test_machine_backup.py tests/test_machine_apply.py tests/test_machine_preflight.py tests/test_machine_trust.py tests/test_machine_memory_restore.py tests/test_machine_workbuddy_restore.py tests/test_machine_verify_undo.py tests/test_machine_privacy.py tests/test_machine_exclusions.py -q --basetemp tmp/run-desktop-20261008-e`：**56 passed，40.49 秒**。新增桌面测试覆盖预览零写入、源／目标变化阻止确认、一次性计划、冲突保留与另存、目录映射、自动核验、历史撤销、进程门禁及旧操作拒绝。
- 前端 `npm run build` 与 `npm run lint` 通过。`scripts/build-desktop-sidecar.ps1` 与 desktop 的 `npm run tauri:build` 通过；Rust 只有链接器“创建库／对象”stdout 提示，构建成功。旧 sidecar 另存 `release-artifacts/ai-config-rpc-before-offline-20261008.exe`；旧 0.2.0 安装包保留。
- 打包后隔离验证：冻结 exe 用合成 HOME 和独立 AI_CONFIG_HOME、PATH 仅保留 Windows System32，实际完成检测→备份预览→确认 ZIP→恢复预览→确认恢复→核验无 FAIL→历史→撤销→无剩余可撤销记录，退出码 0。第一次演练被正在运行的真实 Codex 进程门禁阻止；随后仅在合成 HOME 配置不匹配真实应用的测试进程名，完成演练，未修改真实助手配置。此证据说明打包 core 无需外置 Python/Git，不代替原生窗口、安装或真实加载。
- Windows 0.3.0 x64 NSIS：`release-artifacts/AI-Config-0.3.0-Windows-x64-setup.exe`，**23881173 B**，SHA-256 **`a0c310b2b7745a778b08930ad36e8380935d295676ca686debfacbf6aa6b47e9`**。伴随版权归档复制既有完整归档为 `AI-Config-0.3.0-Windows-NOTICES-full.zip`（依赖版本未新增）；来源与范围沿用 `docs/third-party-licenses.md`，不是新平台完整许可证验收。发布清单由 release-manifest.py 记录当前源码哈希和上述文件。
- 未执行：整个仓库全量回归、原生窗口／选择器／拖拽／关闭时写入保护、干净账户安装、旧版本升级关联清理、签名、真实用户备份与恢复、第二台机器、真实助手规则／记忆加载、新手试用和 Mac。未远程推送，未部署服务器，未调用外部日常库同步工具。

- 交付前复核：`scripts/check-secrets.ps1` 为 **0 findings**，`git diff --check` 通过；PROJECT_STATUS 的唯一字段、未加引号日期、允许状态、非空摘要和 **111 项稳定 evidence 路径**逐项本地自检通过。环境未安装 PyYAML，未引入依赖，按本文件实际采用的 YAML 标量／折叠字符串／列表子集核对格式。未访问外部日常库。发布清单的安装包大小、SHA-256、当前源码文件哈希及安装包副本字节均一致。


## 2026-10-08 检查备份一直等待修复（OF-08）

用户明确：0.3.0 在“检查备份内容”后一直等待，尚未进入确认生成。使用合成助手 HOME、正常软件 PATH、持续打开 stdin 的 JSON-lines 服务复现；冻结 sidecar 的诊断堆栈显示阻塞在 paths.git_root → subprocess.run 的超时清理 → communicate → readerthread.join，Git 子进程仍持有管道。仅清理 PyInstaller DLL 搜索路径不能解决，源码 sidecar 同样复现，因此 DLL 根因假设撤回，诊断插桩及 DLL 改动不进入发布。

最小修复：machine 的 Git 项目根、重装来源、登录清单、软件版本、进程检测及恢复 Git 跟踪探测，均显式设置 stdin=subprocess.DEVNULL；外部命令无需读取用户输入，不能继承桌面仍打开的请求通道。修复项目根后调用链推进到登录清单的 Git 探测，补齐其余同类边界后源码、冻结 sidecar 全链通过。

验证日期 2026-10-08，Windows x64、Python 3.14：`desktop/.build-venv/Scripts/python.exe -m pytest tests/test_machine_process_input.py tests/test_machine_desktop.py tests/test_machine_paths.py tests/test_machine_collect_records.py tests/test_machine_collect_login.py tests/test_machine_collect_reinstall.py tests/test_machine_apply.py tests/test_machine_backup.py --basetemp tmp/run-backup-wait-20261008-b -q` → 21 passed in 24.17s。新增测试在子进程 stdin 保持打开时执行真实 Git 探测，等待退出而不调用会关闭 stdin 的 communicate。源码和重建后的冻结 sidecar 在正常 PATH、合成 HOME、无控制台窗口模式完成检测、备份预览、确认 ZIP、恢复、核验、历史和撤销；冻结测试响应包含 preview/applied，没有卡住。测试使用合成文件，未恢复或覆盖真实助手数据。前端 lint 通过。

0.3.2 发布：前端构建、lint、sidecar 重建、Tauri NSIS 构建通过；`release-artifacts/AI-Config-0.3.2-Windows-x64-setup.exe` 为 23,880,226 字节，SHA256 `8701613747a6f4b22187c65202c0628451fa4b4fca9b662f88d30d493ac7e1e0`。同版本发布清单及完整 NOTICE 归档随包保存；安全扫描 0 findings，diff --check 通过。

交付前复核：回归测试增加无控制台创建标志后，使用新 basetemp `tmp/run-backup-wait-20261008-c` 单独复跑输入管道测试，1 passed in 0.40s；PROJECT_STATUS 字段、日期、非空摘要、唯一字段及 115 个稳定 evidence 路径自检通过，0.3.2 发布清单当前源文件和安装包哈希一致。未使用跨项目日常同步工具。

未验收：0.3.2 原生升级后的用户现场窗口操作和第二台电脑真实助手加载。0.3.0/0.3.1 安装包保留，修复包单独发布。

## 2026-10-08 GitHub Windows 安装包

在 GitHub 发布 [v0.3.2 预发布页](https://github.com/loonslo/ai-config/releases/tag/v0.3.2)，包含 Windows x64 NSIS 安装包、源码/产物 SHA-256 清单和完整 NOTICE 归档。安装包 23,880,226 字节，SHA-256 `8701613747a6f4b22187c65202c0628451fa4b4fca9b662f88d30d493ac7e1e0`；GitHub 资产返回的 digest 与本地一致。清单在干净提交 `ad686d888b7ab091194f644ddc0e09447fe9f943` 重新生成，172 个源码文件哈希与发布源码匹配，`dirty=false`。Release 按预发布标记；代码签名未验证，原生安装升级及第二台电脑真实助手加载仍未验收。

## 2026-10-08 安装后问题排查与 0.3.1 修复（OF-07）

交付检查：`scripts/check-secrets.ps1` 返回 0 findings，`git diff --check` 通过；本项目内自检 PROJECT_STATUS 必填字段、唯一字段、日期、状态和 114 个 evidence 路径通过，0.3.1 发布清单源文件哈希及安装包大小/SHA256 一致。未调用跨项目日常同步工具。浏览器测试页已关闭，临时 Vite 服务已停止。

- 用户报告：安装后看起来未生效／卡住；窗口拉宽后按钮消失，缩窄后可见。本轮不执行真实备份或恢复，不改真实助手文件。
- 确认的布局根因：MachineApp 根元素为 `app-shell`，沿用 App.css 只定义了 `client-layout` 的两列布局。宽度大于 700 时，侧栏 height 为 100vh，占据整行，主内容落到下方；窄屏媒体查询使侧栏 height 为 auto，才看见内容。现改为正确类名，主区 min-width:0，防止长路径撑出窗口，并调整状态面板间距。
- 安装检查：进程位于当前用户 Local/AI Config，程序文件版本为 0.3.0；安装的 RPC exe SHA-256 与本轮 0.3.0 sidecar 一致。对安装后的 exe 只运行 machine_detect，退出 0，1.68 秒返回 accepted／progress／preview，识别 4 个助手，stderr 为空。该只读结果不能证明真实窗口所有操作正常。
- 通信判断边界：最初怀疑 Tauri 去掉换行导致缓冲等待，进一步核对本机 tauri-plugin-shell 2.4.0 和 tauri-utils 2.10.1 源码后发现本版本保留换行，因此撤回“已确认通信根因”的表述。具体卡住的步骤尚未获得用户补充。前端改为直接解析完整行，兼容有／无换行，属于稳健性改进；不把无换行夹具通过当作用户现场根因证明。
- 等待行为：machine_detect／machine_history 15 秒未响应时恢复控件并显示重试提示，迟到的旧请求结果被忽略；备份／恢复／撤销及确认写入不会因超时解除锁定或误报完成，只显示等待，关闭仍等写入安全结束。增加「重新检测助手」。
- 实际界面验证：启动 `node node_modules/vite/bin/vite.js --mode ui-test --host 127.0.0.1 --port 5175`，通过浏览器 API 查看真实 React DOM。仅该测试模式将 Tauri 模块映射到 `desktop/tests/tauri-fixture.ts`；生产模式不注入。
- 五个宽度（高 800）：360／700 使用 flex，main 顶部 110.39；940／1200／1600 使用 grid，main 顶部 0。文档宽度未超过 viewport，按钮右边界均在窗口内；窄屏长页允许正常垂直滚动。分别验证不带换行及 CRLF 的启动检测、选择模拟保存位置、备份预览与确认按钮可见；静默检测 15 秒后提示出现且导航与重试启用；静默 apply 15 秒后继续锁定且没有成功提示。所有路径均为合成 Fixture，无真实备份文件写入。
- `npm run build`、`npm run lint` 与 `npm run tauri:build` 通过，Rust 仍只有创建链接库／对象的 stdout 提示。Python 引擎未变化，前节 56 项回归为历史本日结果，本轮未重复。复用相同 sidecar 与依赖锁，无新增运行或测试依赖。
- 新安装包：`release-artifacts/AI-Config-0.3.1-Windows-x64-setup.exe`，23877279 B，SHA-256 `b5df0e212962331a11a33929678a1c3b592554209249f5bb25057c4da4bb2f0d`。旧 0.3.0 包保留；NOTICES-full 沿用同依赖版权归档，发布清单单独记录当前源码及产物。未在用户机执行升级安装。
- 原生限制：computer-use 能列出安装后的 AI Config 窗口并读到外层 accessibility，但 Windows 窗口截图两次超时；停止原生输入，没有用旧截图或盲点坐标操作。浏览器测试不能代替已安装 WebView、原生文件选择器和实际升级验收。未使用外部日常库，未推送。

## 2026-10-09 GitHub 下载链接 404 修复

用户反馈安装包链接 404。核对发现仓库公开、`v0.3.2` Git 标签仍指向提交 `ad686d888b7ab091194f644ddc0e09447fe9f943`，但该标签对应的 GitHub Release 记录不存在。以保留的标签重建预发布，重新上传 Windows x64 安装包；GitHub 资产摘要为 `sha256:8701613747a6f4b22187c65202c0628451fa4b4fca9b662f88d30d493ac7e1e0`。匿名执行 `curl.exe -I -L` 跟随重定向后返回 **200 OK**、Content-Length **23,880,226**，下载地址现已恢复。Release 页面：[v0.3.2](https://github.com/loonslo/ai-config/releases/tag/v0.3.2)。Release 记录之前为何消失无法从当前证据确定。

## 2026-10-09 中文备份路径误报损坏（OF-09）

Windows 10 x64、Python 3.14。用户提供的 ZIP 为 638,210 字节，SHA-256 `b4ac49f1eec7f597f776fae4e495afd483cae62a2897b0db08176604e158cc05`；源码 validate_bundle 对 134 个条目完整校验通过。只读取清单并验证数据，包内规则、记忆和说明均作为数据处理，没有执行其中内容。

使用已安装的 sidecar，在合成 HOME、独立 AI_CONFIG_HOME、助手根及项目目标映射下，只发送 machine_restore 的 preview 请求。同一份包与参数：ensure_ascii=False 的 UTF-8 请求返回 E_OPERATION_FAILED / invalid or damaged machine bundle；ensure_ascii=True 得到 preview。未发送 apply。根因是 desktop_rpc.py 只对 stdout/stderr 设置 UTF-8，stdin 仍使用 Windows 管道默认编码，中文文件名被错误解码后无法找到 ZIP，FileNotFoundError 被包校验器包装为损坏提示。

最小修复将 stdin 明确设为 UTF-8 严格解码，继续保持 stdout/stderr 为 UTF-8。新增真实子进程管道回归，在 PYTHONUTF8=0 且 PYTHONIOENCODING 分别为 cp1252/cp936 时发送未转义中文路径；隔离 HOME、助手根和状态。修复前：`desktop/.build-venv/Scripts/python.exe -B -m pytest tests/test_machine_process_input.py -k utf8 -q --basetemp tmp/run-unicode-input-20261009-a` → 2 failed，分别复现找不到文件和 UnicodeDecodeError。修复后：`desktop/.build-venv/Scripts/python.exe -B -m pytest tests/test_machine_process_input.py tests/test_machine_desktop.py tests/test_machine_bundle.py -q --basetemp tmp/run-unicode-input-20261009-b` → **35 passed，9.74 秒**。前端 lint 通过。

版本标记升至 0.3.3。`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop-sidecar.ps1`、desktop 中 `npm run tauri:build`（含 TypeScript/Vite）完成，Windows x64 NSIS 构建成功。重建后的冻结 sidecar 在 CREATE_NO_WINDOW、PYTHONUTF8=0、PYTHONIOENCODING=cp1252、隔离 HOME/助手根/状态及项目映射下，以用户原包和 ensure_ascii=False 的 UTF-8 路径请求得到 **preview，退出码 0，stderr 为空**。未发送 apply，合成助手根未创建，原 ZIP 的 SHA-256 前后相同。

交付文件：`release-artifacts/AI-Config-0.3.3-Windows-x64-setup.exe`，**23,876,881 字节**，SHA-256 `c595a8d64e528cbc923c6220a70a976fabeed47da839cadca2822e14c1f47fb4`。完整 NOTICE 归档从依赖未变的 0.3.2 归档复制，SHA-256 `6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f`；随附 0.3.3 源码/产物清单，记录 dirty=true 的本地开发构建。release-manifest.py 首次运行按 GBK 读取 Git 输出失败；使用 `python -X utf8 -B scripts/release-manifest.py --artifact <安装包> --notices <版权归档> --output <新清单>` 后生成成功，没有修改该历史工具的行为。秘密扫描 0 findings，diff --check 通过；摘要字段、日期、状态与 115 项稳定 evidence 路径本项目内自检通过。

未执行真实助手恢复、原生安装升级、真实窗口复测或跨机加载。未将用户备份加入仓库，未使用外部日常同步工具。

## 2026-10-09 已有配置覆盖选择与核验汇总（OF-10）

用户提供现场恢复输出：57 个文件写入、4 处冲突、1 项跳过，同时大量重复的技能/记忆/操作权限核验和 WorkBuddy AI 未检查条目。该输出为用户反馈，安装版本、真实目标文件和实际加载未独立核对；不能将另存副本或部分设置的一致称为环境完整恢复。负责人要求已有配置由用户选择是否覆盖，覆盖前备份本机原文件，并收敛核验输出。

实现：桌面 machine_restore 增加 conflict_choices，按已有文件显示支持字段和路径，让用户选择备份后覆盖或保留。未决定的差异不生成可确认计划，核心 apply 也拒绝未决定的计划；选项变化须重新检查，原有输入/目标哈希和确认清单门禁继续生效。整文件覆盖到原目标；设置仅替换 ZIP 中已采集的支持字段，完整本机配置先通过既有事务备份，未知字段和注释保留。选择保留时原文件字节不变，既有设置文件的缺失字段或项目信任新增也需选择；安全设置/信任/WorkBuddy 确认不能被覆盖选择绕过。原生恢复仍由用户明确确认，本次只写合成 HOME。

核验报告增加助手/类型汇总与每个条目的文件路径、字段和原因。GUI 默认折叠已完成的配置处理及核验详情，技能、记忆和权限按文件数量汇总，未选择助手合并为一个条目；保留本机、部分字段和仅另存副本分别标识，核验 FAIL 时主提示明确失败。后续 Markdown 待办按列表显示，规则提问过滤 HTML 注释/代码块，只针对核验通过的实际规则文件。当前桌面保留选项不再创建 from-bundle；历史核心调用的另存兼容经过相关旧测试验证。

环境：Windows 10 x64，Python 3.14，项目 desktop/.build-venv；全部测试在合成 HOME、独立状态和全新 basetemp 中运行。

- 首轮：`desktop/.build-venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_machine_restore_choices.py tests/test_machine_desktop.py tests/test_machine_apply.py tests/test_machine_verify_undo.py tests/test_machine_trust.py tests/test_machine_memory_restore.py tests/test_machine_guided_restore.py tests/test_machine_process_input.py -q --basetemp tmp/run-restore-choices-20261009-a` → 30 passed，40.25 秒。
- 补覆盖失败回滚与信任确认后专项：`desktop/.build-venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_machine_restore_choices.py -q --basetemp tmp/run-restore-choices-20261009-b` → 11 passed，11.36 秒。
- 首次冻结演练发现保留设置时仍会添加缺失字段，原文件不变断言失败；据此收紧保留语义，并补已有设置缺失字段必须选择的回归。最终使用上述 8 个文件、`--basetemp tmp/run-restore-choices-20261009-c` → **33 passed，55.88 秒**。覆盖备份先于写入、原配置完整备份、撤销逐字节还原、写入失败回滚、安全/信任确认、选择门禁、保留整文件、缺失字段选择、设置部分核验、未选择助手汇总、具体文件身份和坏文件 FAIL。
- Vite ui-test 浏览器夹具（restore-choices/restore-fail）：未选择时无确认按钮；规则覆盖与设置保留可以分别选择，全选及重新检查后可确认；确认后按钮不再保留。26 个 Codex 技能文件合为一行，WorkBuddy AI 未选择合为一行，详情默认隐藏并可展开。模拟核验 FAIL 显示主错误提示且展开失败组。浏览器控制台无 error。结果页示例保存为本地 `release-artifacts/restore-summary-0.3.4-preview.png`，含虚构 Fixture 路径，属于浏览器夹具，不能作为原生窗口或真实恢复证据。
- 冻结后端：`desktop/.build-venv/Scripts/python.exe -X utf8 -B tmp/frozen-choices-smoke-20261009.py`，CREATE_NO_WINDOW、持续打开 stdin、PYTHONUTF8=0/PYTHONIOENCODING=cp1252、未转义中文 ZIP 路径，独立 HOME/助手根/状态。合成配置指定不匹配真实进程的测试名称，未改真实进程门禁。完成待选择 → 覆盖 → 完整原文件备份/汇总核验 → 撤销 → 保留 → 汇总核验 → 撤销，正常退出且 stderr 为空；配置未知字段保留，保留时原文件不变，两次撤销后原文件和 ZIP 哈希不变，没有生成另存副本。

版本升至 0.3.4，最终 `npm run tauri:build` 与 `npm run lint` 均退出 0；Windows x64 NSIS 包已保存到 `release-artifacts/AI-Config-0.3.4-Windows-x64-setup.exe`，23,885,146 字节，SHA-256 `62152a3327bed9a94671e1be9b9b03daff4a8c6a1c288eeec2ebc8998cea1454`。链接器报告创建库和对象的普通提示，无构建失败。完整 NOTICE 同步为 0.3.4 文件名，1,211,055 字节，SHA-256 `6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f`；源码和产物清单为 `release-artifacts/AI-Config-0.3.4-Windows-manifest.json`，标明本地未提交构建和原生安装未验收。

交付前 `git diff --check` 通过，`scripts/check-secrets.ps1` 为 0 findings；逐项核对清单中 173 个源码文件哈希及安装包/NOTICE 的大小与 SHA-256，均一致。`PROJECT_STATUS.md` 按项目契约本地自检：必填字段、非重复字段、真实未加引号日期、合法状态和非空说明通过，117 个稳定 evidence 路径存在且无越界、隐藏或运行目录项。未使用外部同步工具。

未自动安装/更新正在运行的客户端，未覆盖真实助手数据、未重新验收真实加载、Mac 或跨机；未使用外部日常同步工具或发布新远程版本。

## OF-11 简化恢复交互（2026-10-09）

用户反馈未选择时按钮像加载、重复检查步骤过多、重复裸路径难以理解。直接原因是继承样式对所有 disabled 按钮设 cursor:wait，以及修改选项后前端仅使 plan 失效而要求手动重新预览。修复范围仅为桌面交互和版本号；后端、冻结 sidecar、事务备份与输入/目标变化门禁沿用 OF-10，未再次读写真实助手数据。

增加 activeRequest 区分实际操作与禁用；灰色禁用使用 not-allowed，真正检查/恢复以操作文本和 aria-busy 标明。增加 restoreDirty 自动合并 300ms 内的选择变化并请求只读 preview，选择变化即时清除旧 plan；页面切换和选新 ZIP 取消待更新。常驻重新检查按钮移除，确认按钮在未选完或更新中禁用，检查失败/助手运行时才显示重试。写入仍必须点击确认。首次检查结果、自动更新结果与实际完成状态分别显示；完成后隐藏检查/确认入口，选择新 ZIP 开始下一次。

工作文件夹按路径去重并标注「备份中的位置」「本机恢复位置」，默认折叠，未找到说明暂不恢复该项目；Codex 信任以独立说明和默认折叠的去重文件夹名单显示，不将这些位置当作需要手工输入的空白参数。

本次 Windows 前端 `npm run build`（TypeScript + Vite）与 `npm run lint` 退出 0。既有 Vite ui-test restore-choices 界面观察：未选保存位置/ZIP 时 disabled=true、aria-busy=false、背景 rgb(41,49,54)、cursor=not-allowed；一次检查后全部覆盖，自动更新后「确认恢复」enabled=true，重新检查选择按钮数量为 0；改选助手自动更新，重新选择后直接确认，模拟完成页没有再次检查/确认入口。浏览器 error 日志为空。截图 `release-artifacts/restore-flow-0.3.5-preview.png` 为虚构 Fixture 数据，不能代表原生写入。未新增或运行 pytest/自动测试套件；此前 33 项后端回归属于 OF-10 历史验证，不能称为本次复测。目录与信任列表的新展示本次仅源码/类型检查，既有夹具没有相应数据，原生窗口仍待用户验收。

最终 `npm run tauri:build` 退出 0，打包前端资产为 `index-CpRF_8D6.js`。交付 `release-artifacts/AI-Config-0.3.5-Windows-x64-setup.exe`，23,887,159 字节，SHA-256 `27a17f5bcad75aff03352bc9098977a0f9b4e7edbe9d204c675ae4341f45c27a`；完整 NOTICE 沿用未变的依赖，1,211,055 字节，SHA-256 `6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f`。0.3.5 发布清单记录本地未提交构建、173 个源码文件和未验收原生安装；交付前逐项核对源码/安装包/NOTICE 哈希及大小。`git diff --check` 通过，密钥扫描 0 findings；摘要契约和 117 个稳定证据路径本地自检通过。未自动安装、远程发布、真实覆盖或使用外部日常同步工具。

## 2026-10-09 同步分类实施：分类、覆盖与项目默认检测

Windows Python 3.14、合成 HOME 执行，三项方案选择由用户明确接受。72 个稳定 ID 双向一致，分类优先级与既有采集白名单兼容；新增 reports/coverage.json，只枚举/stat，不打开凭据、历史或未定性内容。开关对比的实际携带条目、哈希及字节一致。machine_detect 默认列出已登记且存在的项目，过滤死条目、工作树、scratch、链接及排除项；两个项目记忆夹具通过。

命令、阶段结果、最终复测和限制集中记录于 [同步实施记录](machine-sync-execution.md)。脱敏、manifest v2、新来源采集/恢复、分组界面和历史未验收；未重建安装包或读取真实助手目录，不能把本次分类登记当作已实现全部同步能力。

### 同日继续实施：隐私处理、v2 和 A/B 采集

Windows Python 3.14、合成 HOME：隐私单阶段 machine 回归 151 passed、1 skipped。已接入七类凭据检测、默认脱敏/可选跳过、解析保护、flagged 清单与恢复人工填写提示；旧邮箱拒绝测试按 D17 修改，凭据拒绝与受保护文件零读取仍验证。v1/v2 恢复核验撤销、新元数据校验、报告目录导出边界及桌面协议相关 23 项通过；新增采集复合夹具逐字节核对 18 个 A 类文件及 B 类字段恢复，Git 已跟踪文件未重复带上。

集成回归曾有 5 项旧向导失败（系统标签误用作助手根查询），已修复并专项 7 passed；此阶段最终回归 168 passed、1 skipped，88.29 秒。其他未验收边界详见同步实施记录。本阶段没有读取真实助手配置、执行注册表脚本、导入账号技能或重建/发布安装包。

### 同日继续实施：账号技能、来源及用户环境变量

Windows Python 3.14、合成 HOME：最终完整 machine 回归 180 passed、1 skipped，96.64 秒。支持两层账号/组织的 user 技能及二进制资产、内置技能正文零读取、多账号同名独立 ZIP，恢复不写应用目录；用户环境变量注入测试验证密钥名称零值读取、代理账号信息排除、脚本转义和 PowerShell ParseFile 语法检查，脚本未执行。

技能七级来源、URL 清理、dirty 计数、构建产物排除、超大阈值注入、同名内容不同、第三方启发式示例原样往返及目标逐路径专家允许均通过专项。四类批准链接边界通过 Windows 联接点实际测试；恢复不穿过接管目录，旧符号链接测试仍因权限不足跳过。失败轮次、旧二进制夹具调整与缩进修复逐项记录于同步实施记录。

完整覆盖联动、同名相同、长路径/失败/嵌套项目补验、输出卫生、完整旧包夹具、分组界面和历史仍未完成。未访问真实新来源、CC Switch 数据库、真实注册表、真实恢复或导入账号；未构建/发布新安装包，不代表新电脑已可直接使用。

最终来源复查进一步拒绝全部父路径联接点；直接相关 19 项复测通过，13.29 秒，完整 180 项回归未重复运行。项目摘要本地自检 143 个稳定证据路径通过，密钥扫描 0 findings、git diff --check 退出 0。


### 同日继续实施：内容分组、桌面脱敏与输出卫生

Windows Python 3.14、合成 HOME 的完整 machine 回归 191 passed、1 skipped，98.83 秒；其后项目定制分组及副本摘要不完整标记的直接相关 16 项通过，完整回归未重复。桌面 npm run build/lint 退出 0，最终前端资产 index-DVi4OG7N.js。IAB localhost 合成夹具核对默认分组、历史不选、自动切换脱敏/整份跳过、行号展开、技能整组选项与自动刷新确认；浏览器 error 日志为空，截图保存在 release-artifacts/machine-sync-groups-preview.png 和 machine-sync-restore-groups-preview.png。

含邮箱的项目使用内部选择键完成检测到映射恢复，展示不泄露邮箱而载荷保留；二进制 ASCII 凭据也检查。详细命令、失败修复和验收边界见 machine-sync-execution.md。本次仅构建前端，没有重建或安装发布包，真实源未读取。SC-11 历史仍未接入，SC-10 不能作为含历史的完整验收；CLI 全输出与专家生命周期、其他逐项补验及真实跨机继续保留。


### 同日继续实施：历史流式核心

细化历史实施契约并新增 history.py；Windows Python 3.14、合成 HOME 专项 17 passed，0.38 秒（tmp/run-sync-history-hardening-20261009-1）。单个文件超过注入分包阈值仍能跨 ZIP64 包逐字节重组；未选择零遍历/正文读取、来源变化、缺包/错序/主包不匹配、排他发布、有界重组正文的凭据/JSON 校验、FAT 类无硬链接分支及联接点边界通过。只有核心 API 已实现，主包协调、恢复事务/撤销、项目映射和桌面历史入口仍未接通，不能称为历史恢复验收。未访问真实会话，详细边界和后续全量记录见 machine-sync-execution.md。

历史核心全量 machine 回归 209 passed、1 skipped，103.89 秒；最后边界改动直接相关 17 passed，0.35 秒。密钥扫描、diff 与摘要本地契约 151 个证据路径通过；命令与复测先后见实施记录。


### 同日继续实施：历史主包协调

历史计划已接入备份与桌面协议：主包保存独立包引用，先暂存校验整组、历史包先发布/主包最后发布；已有目标不覆盖，第二包发布失败会回滚本次产物。桌面计划绑定原始历史摘要，即使脱敏字节相同仍拒绝旧预览。最后改动相关 29 passed，14.88 秒（tmp/run-sync-history-coordinator-last-20261009-1）；阶段命令与夹具失败修复见实施记录。历史恢复、界面分包面板/行号截断提示和 Codex 非 JSONL 格式尚未完成；未读取真实会话或重建安装包。


### 同日继续实施：历史恢复所需流式事务设施

StreamContent 描述符进入原共享事务、备份、日志、回滚和中断恢复；机器撤销与协议版本检查使用有界摘要。超过 64 MiB 的流式新文件与普通规则混合提交→撤销通过，且禁止历史目标整份 read_bytes；后续用户修改保留并标待处理。最后相关 38 passed，2.84 秒（tmp/run-sync-stream-final-20261009-1）。共享层全仓回归 576 passed、3 skipped、1 failed（219.89 秒），失败为旧检测用例仍要求四个助手，已按 shared 接入改为核对明确的五个 ID；该修订后专项通过，未再次全仓复测。首次测试模块同名导入失败及修复见 machine-sync-execution.md。

历史包到目标规划的业务接线尚未完成，未声称历史恢复/续接或跨机已验收；没有读取真实会话或构建安装包。


### 同日继续实施：JSONL 历史恢复后端

历史主包引用、同目录分包、摘要/集合/来源数量和有界正文校验接入恢复预检；未选历史不读相邻 ZIP，缺包 E7507。Claude 项目映射/未映射 report/history-unmapped 与 Codex 原位置新增通过；已有文件不读正文、不覆盖，仅唯一另存。历史文件进入共享流式事务，协议恢复→核验→撤销通过；分包变化拒绝旧计划，目标联接点不穿越，脱敏标人工核对。提醒只列已选择内容，不承诺可续接。

完整 machine 回归 232 passed、1 skipped，114.04 秒；之后边界专项 37 passed，10.92 秒。最后改动续记及失败修复详见实施记录；尚未再次全仓复测。前端独立分包展示、Codex 非 JSONL、覆盖联动和真实跨机尚未完成，未读取真实会话或构建安装包。

JSONL 恢复最后相关 46 passed（12.45 秒），相邻包引用命名收紧后 14 passed（3.35 秒）；全量先后范围见执行记录。


### 同日继续实施：编码隐私与历史摘要

多编码字节范围脱敏专项 35 passed；历史全局行号预算与恢复/隐私相关 75 passed（19.39 秒），失败轮次及修正见 machine-sync-execution.md。历史分包摘要和行号截断提示已接入界面，前端 build/lint 通过，尚未补新面板浏览器交互验收。Codex 非 JSONL 历史仍未启用，不能据此声称全部历史格式或真实跨机验收完成。

完整 tests 回归 tmp/run-sync-encoded-full-20261009-1：618 passed、3 skipped，262.63 秒，无失败。三个跳过分别为 test_cloud_core 缺少 jwt 依赖、test_desktop_extensions 当前账号无法创建符号链接、test_machine_coverage Windows 符号链接权限不足；未将跳过当作通过。运行开始后新增的四项二进制 skill 策略用例未计入此轮收集，另以最后相关 39 passed 为证；Python 生产代码在本轮收集后未修改。最后前端 build/lint 通过，凭据扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定证据路径通过。


### 同日继续实施：Codex 非 JSONL 历史

非 JSONL 文本/二进制已进入分包与恢复校验；UTF-16/32 JSONL、跨行私钥整体脱敏及二进制恢复/核验/撤销相关 112 passed（19.70 秒）。最后新边界及完整 machine 回归结果续记。超长无换行二进制和结构化脱敏复查预算仍有显式排除，不声明所有格式/大小均完成；失败轮次与限制详见 machine-sync-execution.md。未读取真实历史或验证助手加载。


历史最后边界 tmp/run-sync-raw-history-last-20261009-1：75 passed，18.65 秒。完整 machine 回归（tests -k machine）tmp/run-sync-raw-history-regression-20261009-1：301 passed、2 skipped、357 deselected，160.89 秒；跳过为收集 test_cloud_core 时缺少 jwt，以及 test_machine_coverage 符号链接权限不足。此轮不是全仓回归，且发生在最后 UTF-32 无效正文修订之前。

最后发现原始 UTF-32 私钥正文可能含无效编码单元；结束标记检查改用替换式解码（仅用于标记判断，原字节只在命中范围内脱敏），新增合成用例验证整个私钥仍被隐藏。最后专项 tmp/run-sync-raw-history-invalid-unit-20261009-1：76 passed，19.03 秒。格式门禁测试的数字密码字面值触发仓库扫描，改为运行时拼接后密钥扫描 0 findings，未放宽规则。最后前端 build/lint 退出 0（index-CGGrhfGR.js）；git diff --check 退出 0。本轮仍未补新面板浏览器交互、超长原始记录的完整支持、覆盖联动或真实跨机验证。


### 同日继续实施：新来源覆盖账本

账号技能、批准链接、第三方原产物分桶、用户环境变量名称字段与历史成功来源携带数已联动；相关 45 passed、1 skipped（8.15 秒），skip 为符号链接权限。账号 .pyc/common artifacts 已补排除且零读取，自建程序仍携带。完整 machine 回归结果续记；实际命令、限制及源映射说明见 machine-sync-execution.md。本轮未读取真实新增来源或验证跨机加载。


新来源覆盖阶段完整 machine 回归（tests -k machine）tmp/run-sync-coverage-new-sources-regression-20261009-1：306 passed、2 skipped、357 deselected，151.67 秒，无失败。跳过为收集 test_cloud_core 时缺少 jwt 和 test_machine_coverage 符号链接权限不足；本轮不是全仓回归。最后 Python 生产改动均发生在该轮开始前。凭据扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过；未使用外部日常同步工具。


## SC-08 同名相同副本全流程补验（2026-10-09）

合成 HOME 在 Claude/Codex/通用技能三个原位置放入同名相同技能，每份包含 UTF-8 非 BMP 文本与二进制资源。skills.json 明确一组 identical、三个成员；主包有六个独立且唯一的成员。恢复实际写入六文件到各原位置、字节一致；核验六项 PASS；同一次事务撤销移除全部六新增文件。没有去重或合并。命令 py -3.14 -m pytest tests/test_machine_provenance.py --basetemp tmp/run-sync-identical-skills-20261009-1 -q：4 passed，2.51 秒。此轮只增加合成验收夹具，未修改生产代码，未重复全量回归；上轮全量不是此新增测试的收集结果。真实同名来源及跨机仍未核实。


## SC-08 长路径与正文读取失败（2026-10-09）

- 技能归档成员超过 240 字符在读取正文前排除，按 path_too_long 记录真实大小与相对路径；其余文件继续采集。读取失败现在进入技能 excluded 和主包排除清单，技能标 partial，不能只留一个通用警告。账号技能同样提前排除长路径、记录读取失败并保留可用导出内容（未知大小为 null，不假报 0）。
- 仅产物缺失仍提示重装/构建；一般文件缺失提示核对排除清单、从原位置补齐。界面不再把所有未携带文件称作“程序文件”。最后前端 build/lint 退出 0，生成 index-DTxCkkqN.js；本轮没有重建 sidecar/安装包。
- 合成普通技能与账号技能分别验证长路径零正文读取、注入 PermissionError 明确排除、其它 SKILL.md 继续备份/恢复或导出 ZIP，原失败文件不写目标。首轮相关 tmp/run-sync-skill-file-failures-20261009-1：9 passed，3.87 秒；账号导出与文案联动 tmp/run-sync-skill-file-failures-last-20261009-1：20 passed，7.15 秒。
- 精确计数复现 tmp/run-sync-skill-exclusion-count-20261009-1：1 passed、1 failed、4 deselected，长路径在采集器和 writer 两处登记，主排除清单重复。改为合并全部排除来源后按路径+原因统一去重，保留技能自身 excluded，未删除问题记录。最后相关和完整 machine 回归结果续记；全量在最后去重修订之前启动。
- 这轮只覆盖可枚举、可 stat 的文件正文读取失败；目录枚举/stat 失败和嵌套项目归属边界仍需补验。真实新增来源、超长历史原始记录、新面板浏览器及跨机仍未验收。


技能文件失败阶段 machine 回归 tmp/run-sync-skill-file-failures-regression-20261009-1：309 passed、2 skipped、357 deselected，172.65 秒。skip 为收集 test_cloud_core 缺少 jwt，以及 test_machine_coverage 的符号链接权限。该轮在最后主排除清单去重修订及新增两项账号失败用例之前启动；最后修改以 tmp/run-sync-skill-file-failures-final-20261009-1 的 23 passed（14.76 秒）为证，未冒充最后全量。最后前端 build/lint、密钥扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过。


## SC-08 嵌套项目技能归属（2026-10-09）

合成父/子项目均有 WorkBuddy AI 同名技能并同时选择。首轮 tmp/run-sync-nested-skill-owner-20261009-1：2 failed、6 deselected，实际采集三份，子项目技能被父项目递归扫描和子项目扫描各带一次；与项目输入顺序无关。采集技能容器前复用既有 _owner/_key 最长匹配，只由真实所属项目采集，不再重复读取/记录子项目技能。修复后 tmp/run-sync-nested-skill-owner-20261009-2（技能来源、WorkBuddy、项目采集相关）：13 passed，6.47 秒。两种顺序均核对只有两条唯一项目成员，归属父/子各一，恢复映射至新父/子项目后分别保留各自字节；明确选择 WorkBuddy 手动候选，仅合成目标写入。

本轮未重复完整 machine 回归；仅修改技能容器归属过滤，相关验证覆盖父子双选、输入顺序与恢复路径。目录枚举/stat 失败、其它嵌套边界及真实跨机仍待补验。未访问真实新增来源、构建或发布客户端。


## SC-08 技能目录枚举与元数据失败（2026-10-09）

- 普通技能容器无法枚举时记录 enumeration_failed，不再整次备份异常退出或无声漏掉。技能子目录通过 os.walk.onerror 记录具体相对目录，技能标 partial；其它可用文件继续采集。单文件 stat 失败记 metadata_unreadable，大小为 null；排除产物大小统计失败同样返回未知，不伪造为零。
- 合成权限失败夹具验证容器/子目录无法枚举、单文件 stat 失败均进入排除报告，问题文件正文零读取，覆盖 totals.complete=false；可用 SKILL.md 仍可发布。未修改权限或读取真实 HOME。原有技能来源/批准链接 tmp/run-sync-skill-enumeration-20261009-1：12 passed，6.96 秒；新增失败与覆盖 tmp/run-sync-skill-enumeration-failures-20261009-1：20 passed、1 skipped，7.56 秒（Windows 符号链接权限不足）。
- 桌面备份预览补充“部分目录未完成扫描”的实际状态说明，以及未携带内容列表（最多 20 项、中文原因）。前端 build/lint 退出 0，index-FoDqYRUL.js；本轮未执行该新列表的浏览器交互验收。完整 machine 回归随后记录。
- G10 只读新增来源授权已通过对话异步提出，当前尚未收到授权答复，不据沉默执行。明确目标为账号 skill/manifest、通用技能、批准链接的 CC Switch 技能、用户环境变量名称及非密钥值、桌面 MCP 配置；不含 CC Switch 数据库、不写助手/注册表、不执行迁移。依据 machine-sync-plan.md §6/§9。
- 此轮主要覆盖通用技能采集器的枚举/stat；账号目录枚举/stat、其它嵌套/字段边界、超长原始历史记录、浏览器全流程以及真机/第二台电脑验收仍待完成。


技能枚举/元数据失败阶段完整 machine 回归（tests -k machine）tmp/run-sync-skill-enumeration-regression-20261009-1：316 passed、2 skipped、357 deselected，174.74 秒，无失败。skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 符号链接权限；本轮不是全仓回归。全部本轮 Python 生产改动与失败夹具在收集前完成。最后前端 build/lint、密钥扫描 0 findings、git diff --check 退出 0，PROJECT_STATUS 本地契约及 156 个稳定 evidence 路径通过。G10 尚无授权答复，未访问真实新增来源，后续继续推进独立合成工作。

## SC-10 历史与扫描失败浏览器补验（2026-10-09）

Windows localhost Vite ui-test，浏览器使用 sync-history 传输夹具，全部为合成路径/响应。历史初始不选，未选时无历史面板；勾选后显示 5 文件/600 MiB/3 独立分包并可展开文件名，提醒与主包同目录保存。行号显示 5、7（实际命中 8 行、样本截断），另一个文件没有保留行号样本但仍显示实际 4 行与截断说明。选择整份跳过自动更新为 3 文件/400 MiB/2 包，排除项增加为 3 项。主排除列表 22 项只显示前 20 项并说明上限，不完整提示可见。

浏览器复现旧的“未纳入备份的内容”与新列表重复显示、旧列表暴露内部原因码且不限制数量；统一为一处可折叠列表，最多 20 项并使用中文原因，恢复报告同样适用。恢复预览历史默认不选、计划 2 文件；勾选自动更新期间确认禁用，更新后显示规则 2 + 历史 5 = 7 文件、分包摘要与排除原因，模拟确认完成后显示 7 文件及“不保证可继续对话”。这里只验证真实 React 界面配合模拟传输，没有执行真实后端恢复或原生窗口操作。

初次 npm dev 参数启动被当前 npm 的配置校验拒绝，改用本地 node_modules Vite 二进制启动成功。夹具热更新仍持有旧传输对象，主动重载后验收；过程中修正夹具的 skip 文件/包计数与恢复总数，没有修改后端以匹配模拟响应。最后 npm run build/lint 通过，前端 index-CF2p5Uco.js；浏览器错误日志为空。稳定截图 release-artifacts/machine-sync-history-browser-preview.png、machine-sync-history-browser-restore.png 已人工查看，无重叠/裁剪。临时页与本次 Vite 进程已关闭。没有重建 sidecar/安装包。

## SC-07 账号技能权限失败补验（2026-10-09）

账号根/账号目录枚举、manifest stat/读取失败、技能目录/子目录枚举与单文件 stat 失败现在明确进入主排除报告；技能内失败保留相对路径、未知大小 null、partial 状态。目录访问失败不再异常终止或无声消失，其它可用内容继续导出。同名账号别名继续隔离，层级故障报告使用序号，不回显真实账号目录名；vendor 正文零读取保持通过。

专项 tmp/run-sync-account-permissions-20261009-1：18 passed、1 failed，技能目录 stat 故障虽已进入主报告，但 Windows 观察器的 is_dir/scandir 仍能工作，覆盖账本错误显示 complete。修复为 CollectionResult 私有 coverage_issues 保留采集阶段已知失败，由备份观察完成后合并入同一根账本，不依赖第二次扫描再次碰到同一故障。最后账号/桌面协议/覆盖/来源相关 tmp/run-sync-account-permissions-20261009-2：39 passed、1 skipped，14.47 秒；skip 是 Windows 符号链接权限不足。夹具覆盖七类 PermissionError，失败内容零读取，nested/file stat 两种场景实际备份→导出 ZIP 只含可用 SKILL.md。后续完整 machine 回归结果续记。

G10 尚无授权答复，未访问真实新增来源；原始历史超长记录、其它字段/嵌套边界、真实源布局和跨机验收仍待完成。

账号权限/浏览器阶段完整 machine 回归（tests -k machine）tmp/run-sync-account-permissions-regression-20261009-1：323 passed、2 skipped、357 deselected，146.29 秒，无失败。两个 skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 符号链接权限不足；本轮不是全仓回归。全部本轮 Python 生产改动和新增七类失败夹具在收集前完成。最后密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 本地逐项字段/唯一键/日期/状态/稳定路径自检通过，158 个 evidence 文件现存且无运行目录/越界/链接，未调用外部日常库同步工具。未将合成浏览器响应当作真实后端恢复证据；真实来源 G10、原生窗口、第二台电脑与助手加载仍待验收，目标保持 active。

## SC-04 完整 v1 合成兼容流程（2026-10-09）

新增旧格式完整夹具：从合成来源取全部八种旧条目类型（含报告），四个旧助手、项目记录和内存/权限/信任字段；去除全部 v2 属性，文本技能使用旧 skills_text 类型。新引擎只读预检不改目标，明确选择覆盖/安全确认/信任确认及 WorkBuddy 手动文件后恢复；全部文件逐字节比较，Codex 设置保留本机未知项并更新白名单值/项目信任，核验无 FAIL；再次恢复 changes 为空且文件不变，一次撤销恢复全部原文件字节，ZIP 哈希始终不变。允许撤销后留下空目录，未把目录移除当作承诺。

tmp/run-sync-full-legacy-v1-20261009-1：14 passed、1 failed；-2 单例仍失败，暴露夹具误将旧版没有携带的 Claude skills 转为旧文本技能。按旧目录表排除它们，不放宽恢复门禁。-3：14 passed、1 failed；旧包字段冲突需要按实际条目选择，不能只按初始 whole-file differs 状态选。改为明确选择全部相关条目后 -4：15 passed，5.42 秒。此项是全类型合成 v1 生命周期，不是真实 134 条旧 ZIP 的新版完整恢复，更不证明旧版客户端可读 v2。

## SC-05 项目登记 MCP、叶级门禁与无 Git（2026-10-09）

复现 CC-14 缺口 tmp/run-sync-project-mcp-20261009-1：1 failed、1 deselected，选中项目 .claude.json 的 mcpServers 没有任何条目。采集现在仅对明确选择且存在的项目生成独立字段条目，以 project_id 关联；项目路径和账号值不装入 payload。恢复到映射项目登记键，不写项目里的 .claude.json。Windows 规范化后匹配已有键，保留原大小写/斜杠；CheckItem.field_path 独立保存层级，点号项目名不被拆为字段。合并和核验共用同一层级，事务仍备份/检查原件/可撤销。

专项包含源 project.with.dot、目标 new.project、目标键大写和斜杠变化、已有远程 URL 冲突；未确认零变化，确认覆盖只更新 URL 与安全 env，保留本机其它 MCP、信任和未知字段、未选择项目及 oauthAccount 字节语义；核验 PASS，撤销恢复原 JSON 字节。真实来源/凭据没有读取。源字段 deviceId、unknown、env.API_TOKEN 不装包。

MCP 恢复门禁由前缀匹配收紧到 url/command/args/type 及合法非密钥 env 叶；20 个伪造字段场景覆盖四种来源文件，deviceId/unknown/url.extra/headers.authorization/env.API_TOKEN 全部拒绝。仍需更完整的字段账本与偏好键验证，不能以这 20 项宣称全部设置均已验收。

无 Git 两分支：程序缺失抛 FileNotFoundError；已安装 Git 对非仓库返回非零。项目规则、提示和通用技能全带且各条 git_unavailable，实际备份/映射恢复逐字节一致并核验成功。测试 tmp_path 在仓库下，必须注入非仓库结果，不能误把父仓库有效 Git 当作此分支。

集成 -2：17 passed，10.94 秒。扩充测试 -3：46 passed、2 failed（测试插入位置把 MCP 后半段放入无 Git 用例，以及非仓库夹具实际继承父仓库）；修正位置后 -4：47 passed、1 failed。-5：47 passed、1 failed，非仓库替身未模拟 check=True 的 CalledProcessError，导致错误 bytes 类型传入 Path；补齐替身后最后 tmp/run-sync-project-mcp-20261009-6：48 passed，31.39 秒，无失败。生产修复没有为这些测试替身错误扩大门禁。完整 machine 回归续记。

本轮没有前端生产改动、安装包重建或真实迁移；G10 尚无答复。项目多个登记项共享一个目标的组合、其它独立规则/字段边界、原始历史超长记录、CLI 专家全流程与真实跨机继续保留。

v1/项目 MCP 阶段完整 machine 回归（tests -k machine）tmp/run-sync-v1-project-mcp-regression-20261009-1：347 passed、2 skipped、357 deselected，158.83 秒，无失败。skip 为收集 test_cloud_core 缺 jwt，以及 test_machine_coverage 符号链接权限；本轮不是全仓回归。所有本轮 Python 生产代码与新增用例均在收集前完成。密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 字段唯一/日期/状态/证据稳定路径本地检查通过，158 个现存 evidence 文件，没有调用外部日常库同步工具。

G10 仍无授权答复，未读真实新增来源；真实旧包新版完整恢复、其它规则与字段账本、设备偏好、CLI 专家全生命周期、超长原始历史、原生/跨机仍未验收。下一轮优先补多个登记项目与全局 MCP 共享 .claude.json 的组合，并使安全确认列表显示所属项目，以免相同字段名对应多个项目时无法区分。目标保持 active，未构建/安装/发布。

## SC-05/SC-10 共用登记文件与确认归属（2026-10-09）

合成全局和两个登记项目的 MCP 指向同一 .claude.json，项目路径含点号，目标已有大写/斜杠键。两个场景分别全覆盖与保留第二项目：最终都只有一次文件写入、一次原件备份；全局与第一个项目正确合并，第二项目按选择新增或完整保留，其它本机/信任/未选项目字段保留，核验对应 PASS/KEPT，撤销恢复原 JSON 字节。未合并为同一项目、没有回写源路径。

首轮 tmp/run-sync-multi-project-mcp-20261009-1：2 failed、24 deselected，安全确认列表没有项目归属。预检 security_list 增加默认兼容的 project/instance，安全确认摘要包括它们；桌面每项显示全局设置、工作文件夹路径或桌面设置。-2 仍 2 failed，仅为测试直接比较 Windows D:/d: 的大小写；按既有不区分大小写的路径语义修正断言后 -3：2 passed、24 deselected，1.60 秒。没有修改路径映射来迎合断言。账号/项目字段与桌面协议/输出隐私相关 -4：36 passed，18.84 秒。

前端 npm run build/lint 通过，index-BJ11SBL7.js。localhost ui-test sync-mcp 夹具浏览器明确显示同一 mcpServers.remote.url 的全局/第一/第二项目三项和桌面 locale，不再无法区分归属。安全选项默认不选、模拟写入 0；勾选触发自动更新，更新时确认禁用，之后模拟写入 1。原夹具写入数常量修正为随 confirm_security 改变，主动重载后检查。只验真实 React 与合成响应，不当作实际后端写入或原生窗口证据。错误日志为空，稳定截图 release-artifacts/machine-sync-mcp-project-confirmation.png 已查看，无重叠/截断；临时浏览器页和本次 Vite 进程已关闭。

完整 machine 回归启动后补充现有输出隐私夹具：邮箱位于源与目标项目路径，真实 MCP payload 保留并通过映射恢复，公开 security_list.project 隐藏邮箱；预览/应用回复与所有 Markdown 均无邮箱。tmp/run-sync-multi-project-output-20261009-1：2 passed、1 failed，断言误以为整个项目路径都被替换；显示策略实际只替换邮箱部分。按既有 public_value 语义核对后 -2：3 passed，3.27 秒，生产隐私规则没有放宽。本补充夹具以专项为证，不冒充已在启动更早的全量中收集。

本轮未访问真实新增来源，G10 仍无答复；多个来源映射同一目标项目的碰撞、其它字段账本/独立规则/设备偏好、CLI 专家全流程、历史超长记录以及原生/跨机继续未验收。完整 machine 结果续记。

共用登记文件/确认归属阶段完整 machine 回归 tmp/run-sync-multi-project-mcp-regression-20261009-1（tests -k machine）：349 passed、2 skipped、357 deselected，161.77 秒，无失败。两个 skip 为收集 test_cloud_core 缺 jwt 和 test_machine_coverage 的符号链接权限；本轮不是全仓回归。所有 Python 生产变更与两项共用文件场景在收集前完成；启动后扩充的邮箱路径旧测试以最后专项 3 passed 为证，未宣称全量已收集该版本。密钥扫描 0 findings、git diff --check 退出 0；PROJECT_STATUS 本项目内契约自检及 159 个现存稳定 evidence 路径通过，未调用外部日常库同步工具。真实 G10/原生窗口/第二台电脑/助手加载没有完成，仍按原目标继续实施其它独立事项。

## SC-05 多来源目标字段碰撞（2026-10-09）

合成两个来源项目映射到同一目标项目，初始目标登记文件已有其它本机字段。首轮 tmp/run-sync-mcp-collision-20261009-1：3 passed、1 failed、26 deselected，明确同时恢复两个不同 MCP URL 时并未拒绝，后一条会覆盖前一条并令前一条核验失真。恢复计划增加 field_proposals，按实际目标文件、独立字段层级、叶键登记所有实际获准恢复的值（包含原本 same 的项）；Windows 项目键规范化后不区分大小写。若同一字段提出不同值，计划在目标写入/创建事务目录前报固定中文错误，消息不含原值/路径。安全未确认、明确保留或未获准字段不参与碰撞。

相同值可以共用一次写入，互不重叠字段可合并，保留第二来源时第一份可恢复；三个场景均核验无 FAIL 并撤销恢复原字节。初步应用/项目/桌面协议/输出隐私 tmp/run-sync-mcp-collision-20261009-2：42 passed，25.93 秒。

扩展桌面协议 -3：41 passed、1 failed（26.58 秒），夹具误期待未选择覆盖的初始预览直接失败；既有协议此时等待选择，尚未批准两个待写入值。修正为明确选择两份覆盖后验证碰撞后，tmp/run-sync-mcp-collision-protocol-20261009-4：4 passed、26 deselected，3.10 秒；协议返回 failed、中文原因、没有 plan_id、原文件不变，改为保留第二份后可生成计划并实际恢复第一份、核验无 FAIL。没有放宽生产门禁以匹配错误期待。

完整 machine 首轮 tmp/run-sync-mcp-collision-regression-20261009-1 在相关旧夹具尚未修正时已启动，收集了该错误断言；显示已知失败后用本次 session 的 Ctrl-C 停止，退出 1，不计为完成回归或新的生产问题。修正夹具后的完整 -2 结果续记。当前只改恢复计划与测试，无前端生产变更，未访问真实来源/构建安装包。

碰撞修复最终完整 machine 回归 tmp/run-sync-mcp-collision-regression-20261009-2（tests -k machine）：353 passed、2 skipped、357 deselected，150.12 秒，无失败；所有本轮生产与测试变更在收集前完成，包含扩充后的邮箱项目路径场景。跳过为 test_cloud_core 收集时缺 jwt 与 Windows 符号链接权限。本轮未重新运行全仓测试或前端构建（没有前端生产变更）。密钥扫描 0 findings，git diff --check 退出 0；本地摘要契约与 159 个稳定证据路径自检通过，未调用外部日常库工具。真实来源、原生窗口、第二台电脑及助手加载仍未验收。

## SC-03 专家 CLI 输出与最小 v2 生命周期（2026-10-09）

Windows Python 3.14 合成源/目标 HOME 和保存目录含邮箱，Codex 规则正文含邮箱与合成令牌；全部外部来源、软件、进程、用户环境表和 Git 凭据查询用隔离替身。四种组合为文本/JSON 输出 × 默认脱敏/allow_secret_hit_paths 原样保留。首轮 tmp/run-sync-cli-hygiene-20261009-1：4 failed、2 deselected（0.80 秒），均复现备份预览直接暴露保存目录邮箱。

scripts/machine.py 增加统一 _emit，在 JSON 序列化前递归清理展示副本，文本也按 public_value 清理；备份、预检、恢复、核验、撤销及错误输出使用同一规则。专家原样保留仍须源路径和目标路径分别获准；不修改同步正文、存储路径或恢复计划。四种组合完成备份零写入预览→v2 发布→预检→恢复零写入预览→实际恢复→核验→撤销预览→实际撤销，检查公开输出无邮箱/令牌、默认令牌变为占位符、专家正文逐字节保留、源原件不变。相关 tmp/run-sync-cli-hygiene-20261009-2：10 passed（8.32 秒）。这是最小 Codex 规则生命周期，尚未代表所有新增种类、历史和专家参数已完成全流程。

没有前端变更、真实来源访问或安装包构建。完整 machine 回归 tmp/run-sync-cli-hygiene-regression-20261009-1 结果续记。

CLI 输出阶段最终完整 machine 回归 tmp/run-sync-cli-hygiene-regression-20261009-1（tests -k machine）：357 passed、2 skipped、357 deselected，160.19 秒，无失败；所有本轮生产与测试变更在收集前完成。两个 skip 为 jwt 缺依赖和 Windows 符号链接权限。本轮未全仓复测或重建前端/sidecar/安装包。密钥扫描 0 findings、git diff --check 退出 0，本项目内摘要契约与 159 条稳定证据路径自检通过。真实来源与原生/跨机加载仍未完成，项目保持 active。

## 用户追加边界：完全不读取 Git（2026-10-09）

用户先明确“我们不能备份git信息”，随后选择“完全不读取 Git 信息，助手文件按白名单携带”。这项当前指令覆盖原分类/计划中的 Git 跟踪状态筛选、Git 根目录推导、技能 Git 来源和脏状态、Git 凭据主机与版本查询；原三项默认方案仍保留，其它范围继续实施。允许公开来源来自非 Git 的账号清单、技能锁文件或技能自带元数据；不查询 Git，锁文件中的 commit/ref 不提取。

变更前在中文/空格 Git 项目的四状态矩阵（tracked、ignored、untracked、tracked_ignored）复现 Windows GBK 解码 Git UTF-8 路径导致中断：tmp/run-sync-git-matrix-20261009-1 4 failed、30 deselected（1.28 秒）；临时修正编码后 -2：2 passed、2 failed（3.97 秒），后两项是夹具直接读取旧条目缺省 rule_id 的 KeyError。用户随后改变需求，临时 Git 查询修复已被完整移除查询的实现取代，未将其作为最终方案。

当前实现：不运行 Git、不读索引/远端/HEAD/脏状态/配置/凭据/版本；白名单助手文件全部携带，不生成 git_unavailable。选中的工作文件夹自身是记忆/信任边界；新项目记录移除 git_root/git_root_id，工具记录移除 git_commit，CC Switch 技能记录不再含 Git remote/head；skills ref 固定 null，local_changes 固定 unknown。旧包路径字段仅兼容定位，不查询本机 Git。所有来源的 .git（目录或 worktree 指针）、.gitconfig、.git-credentials、.gitignore、.gitattributes、.gitmodules 不带；覆盖、批准链接和技能尺寸扫描均不进入 .git 内部，Git 排除大小用 null。其它排除继续沿用原策略。

初步相关 tmp/run-sync-no-git-20261009-1：56 passed、7 failed（33.42 秒）。七个失败均为已被本次明确要求取代的旧期待：无 Git 时 git_unavailable 两例、共用 git_root_id、CC Switch remote、Git 凭据主机、Git 来源/脏状态、Git 根/worktree 推导；已逐项改为当前无 Git 契约，未为通过而放宽其它隐私/路径规则。相关 -2：86 passed（29.16 秒）。

进一步加入 Git 命令、目录枚举和文件正文哨兵：四状态均带 18 个白名单助手文件（含已跟踪后本地修改、中文命令名、三处技能与二进制资产），正确映射恢复、MCP 字段合并、核验、撤销，源字节不变；嵌套 .git/config、HEAD、Git 配置/忽略/凭据及 worktree 指针不恢复。tmp/run-sync-no-git-20261009-3：91 passed、1 skipped、4 failed（37.39 秒），四个失败均发生在测试自身撤销后 rglob 进入目标 .git 的检查，生产流程已通过哨兵；改为检查时先剪枝 .git 后 -4：4 passed、30 deselected（9.42 秒），没有放宽生产扫描哨兵。

三份规范按当前要求同步。没有前端生产变更，未访问真实来源或构建安装包。完整 machine 回归 tmp/run-sync-no-git-regression-20261009-1 结果续记。

无 Git 阶段完整 machine 回归 tmp/run-sync-no-git-regression-20261009-1（tests -k machine）：361 passed、2 skipped、357 deselected，167.11 秒，无失败；所有此前生产/测试变更在收集前完成。跳过为 jwt 缺依赖与 Windows 符号链接权限。完成后检查发现 Git 元数据的正常排除也可能被当作需要补齐的技能内容，追加修正：只排除 Git 信息不产生 artifacts_excluded 标记、不增加 needs_rebuild、不提示补齐 Git；排除记录仍保留，其它缺失/程序排除继续提示。该最后修改以随后专项为证，不冒充已在本轮完整回归中收集。

最终 Git 排除提示专项 tmp/run-sync-no-git-rebuild-20261009-1：59 passed，31.69 秒，包含四状态全流程/零读取、needs_rebuild=0 与不提示补齐 Git，以及第三方技能、分组、恢复与预检。完整回归 361 passed 早于这项最后修正；本轮无前端生产变更，未重建前端/sidecar/安装包，未运行本轮全仓回归。密钥扫描、diff 与摘要契约最终自检结果见交付记录。

本轮交付自检：scripts/check-secrets.ps1 为 0 findings；git diff --check 退出 0（仅既有换行转换警告）；PROJECT_STATUS YAML 唯一字段、2026-10-09 未加引号日期、active 状态、非空说明及 159 条项目内稳定 evidence 路径逐项本地检查通过。未调用外部日常库同步工具。当前成果为源码与合成验证，已安装程序和现存安装包仍待重建/现场验收。

## 0.3.6 重建交付（2026-10-09）

用户明确要求重建安装包。版本从 0.3.5 升至 0.3.6，保留原 0.3.5 安装包/NOTICE/清单；替换构建侧 sidecar 前保存 release-artifacts/ai-config-rpc-before-0.3.6-20261009.exe。此次重建包含当前同步分类/来源/隐私/v2/分组/历史/恢复代码及完全不读取 Git 的用户边界，不宣称未验收功能已经完成。

Windows x64 / Python 3.14：scripts/build-desktop-sidecar.ps1（PyInstaller 6.22.3）完成；desktop npm run lint 退出 0；npm run tauri:build 退出 0，TypeScript/Vite 与 Rust/NSIS 成功，前端 index-BJ11SBL7.js。Rust 仅既有 linker_messages 警告。版本在 npm、npm lock、Tauri、Cargo manifest/lock 中为 0.3.6。

冻结 sidecar 使用 CREATE_NO_WINDOW、持续打开 stdin、ensure_ascii=False UTF-8 中文 ZIP 路径、PYTHONUTF8=0/PYTHONIOENCODING=cp1252、隔离 HOME/助手根/状态/APPDATA/LOCALAPPDATA，PATH 只保留 Windows System32（无外置 Python/Git）。tmp/frozen-0.3.6-smoke-20261009.py 退出 0、stderr 空：实际 v2 备份携带新审批规则与技能，Git 元数据/忽略文件不携带、软件记录不查询 Git；恢复经历待选择→覆盖→原文件完整备份→核验→撤销→保留→核验→撤销，源文件与原 ZIP 哈希不变。流程仅合成数据，不等同原生安装、窗口或真实助手加载验收。

交付 release-artifacts/AI-Config-0.3.6-Windows-x64-setup.exe，24,046,373 字节，SHA-256 b84057049a4ed15a2d86063787a9257c068496aac591e649897355207bbcf254。NOTICE 沿用 0.3.5 完整归档：核对 Cargo active Windows target 及已安装 npm 的所有名称/版本已覆盖，Python 构建依赖锁哈希未变，322 项记录 complete=true；非当前平台 optional 包不作为缺失。新归档 AI-Config-0.3.6-Windows-NOTICES-full.zip，1,211,055 字节，SHA-256 6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f。

AI-Config-0.3.6-Windows-manifest.json 记录 194 个当前源码文件哈希、sidecar/前端资产/安装包/NOTICE 哈希与大小，生成和逐项验证均不查询 Git；无 source_commit 或 dirty。所有源码及交付产物哈希核对通过。未自动安装、推送或远程发布；安装升级、原生窗口、真实来源预览及跨机仍待验收。本轮以构建与冻结流程为证，未重跑 pytest 全仓/完整 machine；此前 361 项和最后相关 59 项为无 Git 阶段证据。

0.3.6 最终自检：首次清单读取按 Windows 默认 GBK 解码含中文的 UTF-8 JSON 失败，仅为校验命令编码问题；改用显式 UTF-8 后 npm/Tauri/Cargo 五处版本、194 个源码、sidecar/前端/安装包/NOTICE 全部哈希核对通过。密钥扫描 0 findings，diff --check 退出 0；PROJECT_STATUS 本项目内 YAML 唯一字段/真实日期/active/非空内容及 162 条稳定证据路径检查通过，未访问日常同步工具。


## 0.3.6 检查备份隐私误判修复（2026-10-10）

用户报告 0.3.6 点击“检查备份内容”返回 `E_OPERATION_FAILED: private content in migration output`；用户最初称生成 ZIP，随后明确发生在预检阶段。复用采集器的本机只读诊断发现文件清单 entries 元数据命中 token：技能资源名的 `ask-` 中间包含 `sk-`，后续长文件名被旧模式当作 API Key。仅输出字段分类/命中类型和是否位于单词内部，不输出配置正文、路径或凭据；没有生成真实 ZIP，也没有改动助手文件。

修复：仅为 sk- token 前缀增加 ASCII 字母/数字起始边界，ask-/task-/risk-/flask- 词中后缀放行；独立 token、引号、赋值、路径分隔符、中文前缀及下划线/连字符前的 token 仍检测。另为启发式字段识别增加起始边界，避免长连续字符逐位置重试，100 万字符本机扫描 0.203 秒。备份/恢复隐私拒绝改为 E_PRIVATE_CONTENT，安全提示元数据/报告/文件类别、清单序号及识别类型/行号，保留原拦截规则，不显示不可信文件名、原文或凭据。

Windows / Python 3.14，2026-10-10 实际验证：

- 既有隐私三文件初查 `tmp/run-private-output-20261010-1`：47 passed；诊断改动相关六文件 -2：70 passed。
- 长字符串修订相关 -4：71 passed。-3 因误列不存在的 test_machine_collect_skills.py，未运行测试；已改用实际测试文件。
- 文件名边界修订 -5：85 passed、1 failed；失败为新夹具未创建目标 .claude 导致恢复目标不可用，备份与隐私门禁已通过。补齐夹具目标目录后 -6：86 passed（23.19 秒），含该文件名备份到恢复预检、旧包隐私拒绝、协议安全错误、七类凭据与 UTF-16/32 二进制脱敏。
- `py -3.14 -m pytest -q tests/test_machine_history.py tests/test_machine_history_restore.py tests/test_machine_env_export.py tests/test_machine_collect_desktop_skills.py tests/test_machine_skills_links.py --basetemp=tmp/run-private-output-history-20261010-1`：95 passed（14.68 秒）。与最后六文件合计 181 项通过。
- 本机快速预检（未选技能/历史、关闭覆盖统计及软件探测、无项目）33 条通过；含默认技能及已登记项目、同样关闭覆盖统计/软件探测的预检修复前复现 entries 误判，修复后通过隐私门禁但被“采集期间来源发生变化”保护停止。助手仍在运行，不能把这次诊断写成完整真实预检/备份通过；完整覆盖统计、用户实际分组与原生窗口仍待复测。

未执行本轮全仓/完整 machine 测试。安装包重建与冻结后端结果续记；尚未自动安装、远程发布或验证真实跨机加载。


### 0.3.7 重建交付与冻结验证（2026-10-10）

Windows x64 / Python 3.14：scripts/build-desktop-sidecar.ps1（PyInstaller 6.22.3）退出 0；desktop npm run lint 退出 0；npm run tauri:build 退出 0，TypeScript/Vite、Rust 与 NSIS 通过，仅既有 linker_messages 警告。五处应用版本一致为 0.3.7；0.3.6 安装包/NOTICE/清单保留，旧 sidecar 另存 release-artifacts/ai-config-rpc-before-0.3.7-20261010.exe。

冻结后端使用 CREATE_NO_WINDOW、持续输入管道、UTF-8 中文 ZIP 路径、PYTHONUTF8=0/PYTHONIOENCODING=cp1252、隔离 HOME/助手根/状态/APPDATA/LOCALAPPDATA，PATH 仅 Windows System32。合成技能包含 ask- 前缀 Markdown 资源：实际检查备份及 ZIP 生成通过，v2 包原样携带该文件；旧合成包覆盖/完整原文件备份/核验/撤销/保留/核验/撤销通过，原 ZIP 与源文件字节不变。脚本 tmp/frozen-0.3.7-smoke-20261010.py 退出 0、冻结进程 stderr 空；稳定证据为此记录，不引用临时脚本作 evidence。未生成真实助手备份。

交付 release-artifacts/AI-Config-0.3.7-Windows-x64-setup.exe，24,051,107 字节，SHA-256 6c3eda1832dcdfeb2138589db84026c83a1cde5e1dd03d95246f85b361e2312c。依赖文件与 0.3.6 源清单哈希对比仅应用版本变化，Python 三份需求文件哈希相同，沿用已核对的 322 项 NOTICE；0.3.7 NOTICE ZIP 哈希 6ad5d51b0538c171f93a31147997ccf008c0d162ff33146c7237af3cd2cc801f。新清单记录并逐项核对 194 个源文件、sidecar、前端、安装包与 NOTICE 哈希，不查询 Git。未自动安装或远程发布；真实窗口预检、来源稳定条件下完整备份及跨机加载仍待用户复测。本轮未跑全仓或完整 machine；181 项直接相关为本轮测试证据。


0.3.7 交付自检（2026-10-10）：仓库扫描首次 4 findings 均为上述长 ask- 文件名和测试中的占位符赋值触发旧共享扫描器；未改动扫描器或放宽门禁，改为运行时拼装测试名称、通过原输入替换构造预期字节，文档仅记录前缀。最后两测试文件复跑 tmp/run-private-output-final-20261010-1：57 passed（2.29 秒）。最终 scripts/check-secrets.ps1 为 0 findings，git diff --check 退出 0；PROJECT_STATUS 唯一字段/真实未引号日期/active/非空说明及 165 个稳定证据路径本地自检通过，194 源文件和全部交付产物哈希通过。未调用外部日常同步工具。依赖比对首次验证命令把 Cargo 中无关 fdeflate 0.3.7 也替换导致断言失败；改为只逆转 app 版本后哈希完全一致，无依赖变化。

## OF-12 页面整体布局优化（2026-10-11）

实际环境：Windows，现有 React/Tauri 前端依赖和 localhost Vite ui-test；仅读取本项目源码及前端技能，未访问真实助手数据。备份四步骤分区、选择卡片、右侧项目/保存/检查、ZIP 入口、核验报告和记录空态统一为深色导航与浅色工作区。最终 npm run build / npm run lint 均退出 0，产物 index-Dfj3RLoM.css / index-DWlK2Q5f.js。

备份与恢复报告各在 320/360/700/940/1200/1600 px 测量无横向溢出及可见控件越界，默认 940 px 两列保留。合成浏览器验证选择保存位置与备份预览、恢复冲突全部覆盖/保留、自动更新期间确认禁用、更新完成启用、模拟确认后核验汇总以及核验失败红色提示与自动展开。记录页空态及 360 px 布局通过，最后浏览器 error 日志为空。旧 sync-groups apply 夹具未记录备份 operation，模拟备份确认仅验状态提示，不视为备份明细或后端验收；完整经过、设计、截图与边界记录在 docs/ui-layout.md。

人工查看桌面备份和窄屏截图，无重叠；浏览器尺寸覆盖与截图初次不一致，重新使用匹配尺寸保存最终预览。临时页、尺寸覆盖和 Vite 服务已清理。本轮未运行 pytest 或后端回归，未重建 sidecar/NSIS 或安装发布。2026-10-10 的 0.3.7 安装包及 194 文件清单仍属历史产物，不包含新 UI；原生窗口、选择器/拖拽、完整键盘导航与真实跨机仍未验收。

OF-12 交付自检（2026-10-11）：scripts/check-secrets.ps1 为 0 findings，git diff --check 退出 0；PROJECT_STATUS 本项目内 YAML 唯一字段/真实未加引号日期/active/非空说明及 167 个稳定 evidence 路径自检通过，无未通过项。最终桌面三页及窄屏截图已查看；没有使用日常同步工具。

## 2026-10-15 提交与推送验证

Windows / Python 3.14：完整 pytest 使用全新 tmp/audit-20261015-02，735 passed、3 skipped（321.80 秒）；桌面 TypeScript/Vite 构建和 oxlint 通过，scripts/check-secrets.ps1 为 0 findings。首次使用旧 .venv 的 Python 3.13 时因缺 jsonschema 在收集阶段失败，改用已具备依赖的 Python 3.14 后通过；未改全局依赖。

本次提交既有 0.3.7 分类、历史恢复、隐私和桌面布局改动。公开远程历史与本地旧历史树一致但根提交不同，因此保留 backup/pre-sync-20261015，将新提交接到远程历史，避免公开旧历史；无强制推送。当前产品为离线桌面工具，无生产服务器部署。未重建 NSIS、安装升级或真实跨机验收；不把前端构建当作原生发布。

2026-10-15 推送后 CI 发现 requirements-test.txt 漏声明既有测试导入的 jsonschema；已加入测试依赖范围（4.x），不加入运行依赖。完整本机回归仍以 735/3 为本次证据；推送后另核对跨平台工作流。

### 2026-10-15 云端跨平台结果

补齐依赖后 GitHub Actions run 38707301357：macOS core/frozen 均失败，其中 frozen 为 18 failed、724 passed；Windows 两项因矩阵 fail-fast 被取消。失败涉及 Windows 路径夹具、项目 MCP/信任映射、大小写记忆目录、junction 调用 cmd 与启动器路径，不能宣称跨平台验收通过。保留测试和错误，不用跳过掩盖；这些跨平台修复超出本轮提交与服务器发布范围，未发新版安装包。后续仅关闭矩阵 fail-fast，保留各系统独立结果，避免 macOS 失败取消 Windows 证据。
