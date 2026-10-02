# 跨设备配置一致性与零基础体验改造任务

> 状态：已冻结；2026-10-02 起由 [MACHINE-MIGRATION-TASKS.md](MACHINE-MIGRATION-TASKS.md) 取代。下文验收记录均为历史记录。

2026-10-01 说明：本文保留 2026-09-15 的 CLI 体验改造与历史验收记录。下文“第一版采用命令行、不新增 GUI 或服务器”是当时范围，已被本次桌面客户端方向取代；当前实施任务以 [DESKTOP-TASKS.md](DESKTOP-TASKS.md) 为准，不能因旧 TASK 完成就认定客户端任务完成。

日期：2026-09-15。本文为新增实施计划，所有任务初始为未完成；不替代 TODO.md 中的可靠性与三机验收工作。

核心用户目标：不手工编辑 JSON、不理解 Git 内部结构，就能让两台 Windows 和一台 Mac 加入同一配置源，修改、同步并确认共享配置实际生效。记忆与项目交接保留为可选能力，不阻塞仅配置用户。

本文的 setup、sync、status 等为拟新增命令。内部现有命令保留兼容，不把示例误写成当前已支持功能。第一版采用中文交互式命令行，不新增 GUI 框架或配置服务器。

## 总体约束

- 保留现有事务、操作系统锁、内容核对、备份、敏感信息扫描及非强制 Git 传输保护。
- 自动识别事实；只有共享范围、变更归属及外部目标需要用户选择。
- 配置相同指受管共享字段与规则一致，不要求路径、系统专属值、凭据及所有工具设置完全相同。
- 区分下载完成、应用完成与工具会话已重新加载，不虚构运行时生效验证。
- 不自动提交整个工作区、不覆盖无关文件、不从远端配置执行任意脚本。
- 新任务先写回归测试，再实现；任务完成后记录文件、测试和限制。

## 第一阶段：建立可验证的配置一致性

### TASK-01：定义用户状态和一致性数据结构

- [x] 完成
- 优先级：P0；依赖：无。
- 修改位置：schemas/device.schema.json；新增 schemas/config-state.schema.json、sync_core/status.py。
- 工作：定义配置源身份、工具启用状态、受管字段、期望值摘要、本机差异、目标文件实际摘要、最近应用版本、最近核对时间。分别返回 config、memory、handoff 三类状态。
- 状态至少包括：未设置、待同步、已应用、存在本机修改、冲突、离线、应用失败、需要重启；不得用单一 ready 表达所有能力。
- 只在本机保存真实路径和实际值；共享回执仅保留明确允许的摘要及非敏感元数据。
- 验收：结构版本可验证；未知版本明确拒绝；未启用记忆时配置状态可独立成功；状态字段有单元测试。

### TASK-02：正确计算共享配置与本机期望结果

- [x] 完成
- 优先级：P0；依赖：TASK-01。
- 修改位置：scripts/sync.py 的 _config_facts、_config_plan；sync_core/config.py、sync_core/handoff.py。
- 工作：从设备实际选择读取受管字段，替代固定的全部允许字段；生成共享模板 → 平台差异 → 本机覆盖的明确结果，并标识每个值来自哪里。
- 禁止凭据、登录和会话字段进入共享字段集合；未经验证的工具参数不默认管理。
- 验收：两设备选项不同可识别；合法系统／路径差异不算共享冲突；修改未受管字段不算配置漂移；共享字段变化可检测。

### TASK-03：核对工具目标文件，发现配置漂移

- [x] 完成
- 优先级：P0；依赖：TASK-02。
- 修改位置：新增 sync_core/config_status.py；复用 sync_core/doctor.py 和规则受管区块逻辑。
- 工作：读取真实 AGENTS.md、CLAUDE.md、config.toml、settings.json，仅比较受管内容；报告缺失、格式错误、本机修改、待应用及已应用。源文件一致不能直接判定工具目标一致。
- 应用成功后重新读取目标文件核验；不能读取时返回未知／失败。工具需要新会话加载时单独提示。
- 验收：人为修改目标受管字段后 status 必须识别；目标文件丢失不能成功；无关注释和未受管字段变化不误报；应用后核验失败不得生成成功回执。

## 第二阶段：零基础首次设置

### TASK-04：环境与工具自动检测

- [x] 完成
- 优先级：P1；依赖：TASK-01。
- 修改位置：新增 sync_core/environment.py；复用 sync_core/inventory.py。
- 工作：检查 Python、Git、项目依赖、系统、已安装工具及实际配置目录；尊重自定义工具根目录。未发现工具不自动创建其配置。
- 将检测结果转换为中文提示；缺依赖给出适合当前系统的明确操作，不要求用户猜命令。
- 验收：Windows／Mac 路径、自定义目录、只安装一个工具、缺 Git、缺依赖均有测试；检测本身无写入。

### TASK-05：提供统一启动入口

- [x] 完成
- 优先级：P1；依赖：TASK-04。
- 修改位置：新增根目录启动脚本 ai-config.ps1、ai-config.command，按项目约定提供 Python 入口。
- 工作：解析脚本所在目录，不依赖当前工作目录；支持带空格／中文的路径；检查运行环境后进入同一个命令界面。保留原 Python 命令入口。
- 不自动修改系统 PATH、安装全局包或绕过系统执行策略。依赖安装优先用本项目独立环境，并给出清晰进度和失败原因。
- 验收：从不同工作目录调用均正常；缺环境可理解地退出；重复启动不重复安装；Mac 可执行权限纳入仓库与实机验收。

### TASK-06：首次设置向导 setup

- [x] 完成
- 优先级：P1；依赖：TASK-02、TASK-04、TASK-05。
- 修改位置：新增 sync_core/setup.py；scripts/sync.py；device.example.json、examples/。
- 工作：区分第一台设备与加入已有配置源；自动生成不冲突的稳定设备 ID；识别工具；选择“公共规则＋选定工具设置”或“仅公共规则”；默认不开启记忆。
- 展示检测到的当前值和即将应用的值；有旧配置时先保留，再让用户决定差异归属。输出本机配置无需用户编辑 JSON。
- 第一次设备需要明确配置源地址；加入设备校验源身份。不要把安装完成描述为三机同步完成。
- 验收：新设备、已有配置、自定义目录、仅规则、单工具、中途取消及重复运行均能正确处理；取消不产生半套应用。

### TASK-07：新增设备加入流程

- [x] 完成
- 优先级：P1；依赖：TASK-06。
- 修改位置：setup.py、配置源登记结构及 examples/。
- 工作：第二台／第三台复用共享字段选择，不重复选择全部参数；路径等本机事实重新检测。设备同名或 ID 冲突时明确处理，不覆盖已有设备记录。
- 网络或认证失败保留已填写信息，允许重试；不在日志输出带凭据的 URL。
- 验收：三个独立目录模拟加入同一源；系统差异正确处理；重复加入幂等；连错配置源明确停止。

## 第三阶段：统一日常同步与状态

### TASK-08：实现配置专用 sync 编排

- [x] 完成
- 优先级：P0；依赖：TASK-03、TASK-06。
- 修改位置：新增 sync_core/config_sync.py；scripts/sync.py；复用 transaction.py 与 Git 基础设施。
- 工作：本机漂移检查 → 获取远端 → 解析共享变更 → 预览 → 备份／应用 → 目标核验 → 保存回执。配置同步不得要求存在 ai-memory。
- 共享源有未提交修改时，不自动丢弃或提交所有文件；引导到 TASK-12。远端分叉保留双方，不能强制更新。
- 同一锁协调配置源更新、生成和应用；失败清楚区分下载阶段、应用阶段与回执上报阶段。
- 验收：拉取后自动进入应用流程；离线、dirty 源、远端分叉、目标漂移、写入失败和重复执行均覆盖；没有变化时零无意义写入。

### TASK-09：提供中文 status 总览

- [x] 完成
- 优先级：P1；依赖：TASK-01、TASK-03、TASK-08。
- 修改位置：status.py、CLI 输出层。
- 工作：展示本机配置源、共享版本、各工具受管范围、目标核验结果、最近成功应用时间、下一步；记忆和交接单独列示启用状态。
- 输出示例含义：“本机共享配置已应用；需要启动新会话加载；其他设备最近状态见下方”。零变更预览不等于已应用。
- 验收：用户不读 JSON 能判断是否需要操作；未知状态不伪装成功；仅配置用户不出现无关记忆错误。

### TASK-10：共享设备回执与三机总览

- [x] 完成
- 优先级：P1；依赖：TASK-08、TASK-09。
- 修改位置：新增 schema/device-receipt 及 sync_core/receipts.py。
- 工作：在配置源建立专用设备状态分支，每设备独立文件；回执不改变 main 的配置内容版本。记录实际选择的受管范围、内容摘要和已验证应用版本。
- 回执写入／读取使用隔离工作区，不切换用户分支。失败时本机已应用状态仍保留，另报“状态尚未上报”。普通推送遇并发前进可重试，不能 force push。
- 其他设备只显示“最近报告于某时刻”，不把离线设备标为当前在线或实时一致。
- 验收：A 与 B 同时上报不会覆盖；回执分支更新不触发配置重应用；三设备可区分已应用、待更新和未知；无真实路径及敏感值。

## 第四阶段：友好的修改与恢复

### TASK-11：差异展示及归属选择

- [x] 完成
- 优先级：P1；依赖：TASK-03。
- 修改位置：新增 sync_core/diff_view.py、交互输出层。
- 工作：列出字段中文名称、共享值、本机值与来源；提供“共享到其他设备”“仅此设备”“恢复共享值”。默认不替用户选择覆盖。
- 复杂结构第一版只展示并引导高级处理，不假装能安全自动合并。敏感字段始终遮蔽且不得共享。
- 验收：工具界面产生的本机修改可识别；选择前不写入；每种选择的后续影响明确；非交互模式需要显式参数并返回稳定状态。

### TASK-12：将本机修改保存为共享或本机覆盖

- [x] 完成
- 优先级：P1；依赖：TASK-08、TASK-11。
- 修改位置：config.py、config_sync.py。
- 工作：共享选择只更新允许的模板字段，限定提交清单，敏感检查后提交／普通推送；本机选择写入本地覆盖，不改共享模板；恢复选择经备份后应用共享值。
- 远端新修改导致冲突时保留原值和待发布变更；不能自动提交仓库中的无关代码／文件。
- 验收：共享修改可在 B 生效，本机覆盖不影响 B；失败后可重试；已有无关暂存修改不被带入提交。

### TASK-13：按操作恢复配置

- [x] 完成
- 优先级：P1；依赖：TASK-08。
- 修改位置：transaction.py；新增用户级恢复入口。
- 工作：展示最近操作的时间、工具和更改数量；用户选择“撤销上次配置应用”，无需寻找 UUID／备份编号。恢复前核对备份及目标后续修改。
- 配置恢复与记忆快照恢复分开；不自动把恢复结果推为共享最新值。
- 验收：恢复后受管字段与当时一致；备份损坏拒绝；后续用户修改出现冲突提示；中断后再次执行可恢复。

### TASK-14：统一错误与下一步操作

- [x] 完成
- 优先级：P1；依赖：TASK-06、TASK-08、TASK-13。
- 修改位置：新增 sync_core/messages.py，统一 CLI 渲染。
- 工作：错误输出固定为“发生什么／原数据是否保留／下一步怎么做”；提供稳定错误编号。默认中文，--json 供自动化，--verbose 查看脱敏技术详情。
- 覆盖未设置、未登录 Git、网络错误、源冲突、目标漂移、目录缺失、备份损坏、文件被占用等。
- 验收：常见错误不直接抛 traceback；中文输出与 JSON 退出码含义一致；不出现“退出成功但应用失败”。

## 第五阶段：记忆与项目功能渐进接入

### TASK-15：记忆启用向导与来源映射

- [x] 完成
- 优先级：P2；依赖：TASK-06、TASK-09、TASK-14。
- 修改位置：inventory.py、setup.py、现有记忆配置模块。
- 工作：用户完成配置同步后可选启用记忆；连接私有 ai-memory，显示候选来源并关联项目。明确 Claude 原生目录同步和 Codex 参考快照的不同能力。
- 待映射、排除和不支持来源可见；不启用记忆时不检查它的远端或阻塞配置同步。
- 验收：不编辑 JSON 能接入一个记忆来源；新项目可追加；凭据文件阻止共享；关闭记忆功能保留原数据。

### TASK-16：面向用户的项目接续入口

- [x] 完成
- 优先级：P2；依赖：TASK-15，且现有 start／finish 可靠性验收通过。
- 修改位置：handoff.py、CLI 项目选择与交接展示。
- 工作：用户选择项目及最近可用交接，不手输项目 ID／快照 ID；显示目标、已完成、下一步、版本和未同步项。保留高级 ID 参数用于精确恢复。
- 源代码未上传或工作区有修改时解释原因；不自动切分支或清空工作区。
- 验收：新设备能选择正确交接并读取上下文；历史与当前交接不混淆；缺少资料不能显示可完整接续。

## 第六阶段：文档与用户验收

### TASK-17：重写入门文档并修正过时说明

- [x] 完成
- 优先级：P1；依赖：TASK-06、TASK-08、TASK-09、TASK-14。
- 修改位置：README.md；新增 docs/getting-started.md、docs/troubleshooting.md、docs/advanced.md。
- 工作：README 按“能做什么 → 首台加入 → 第二台加入 → 修改一次并同步 → 确认状态”组织；内部目录、快照和事务格式移到高级说明。
- 修正旧父快照基线说明、传输文件允许范围及“所有命令默认预览”等不准确表述。写清哪些命令读、哪些写、哪些发布。
- 保留脚本兼容说明，但不在首页并列十余种命令。
- 验收：逐条执行文档命令；文档展示的状态与真实输出一致；初学者完成配置同步无需阅读高级文档。

### TASK-18：三机功能与零基础可用性验收

- [ ] 完成（自动化部分已完成，实机部分待用户提供设备）
- 优先级：P0 发布门槛；依赖：TASK-01 至 TASK-14、TASK-17。记忆部分另依赖 TASK-15、TASK-16。
- 修改位置：tests/、CI、docs/acceptance.md。
- 工作：分别记录 Windows A、Windows B、Mac 的版本与结果；用无敏感测试配置完成 A 修改 → B 获取 → Mac 获取 → 三机回执核对。
- 让一位未参与开发的使用者仅按入门文档操作，记录卡点、误解与是否需要口头帮助。
- 必测：首次安装、重复加入、离线重试、本机覆盖、远端冲突、目标文件被工具改写、撤销应用、回执上传失败、单工具及未启用记忆。
- 验收：无需手工改 JSON；日常同步一个入口；用户能准确说明“本机是否已应用／哪些设备待更新／失败后如何继续”。三机测试报告完整；不能用 Windows 模拟目录代替 Mac 实机。
- **当前进度**：验收清单与记录表已写入 `docs/acceptance.md`；单机端到端流程已逐条手工验证；自动化测试 145 项全绿。三机实机与零基础用户验收需要用户提供两台 Windows、一台 Mac 和一个配置源远端。

## 建议执行顺序

1. TASK-01 → 02 → 03：先能准确判断一致性。
2. TASK-04 → 05 → 06 → 07：完成首次设置与其他设备加入。
3. TASK-08 → 09 → 10：形成同步与状态闭环。
4. TASK-11 → 12 → 13 → 14：补齐修改、恢复和错误处理。
5. TASK-17 → 18：交付配置同步第一版；TASK-18 中记忆部分此时标未启用。
6. TASK-15 → 16 → 18 的记忆验收：增量交付记忆与上下文接续。

阶段验收不能仅凭测试数量：必须对照每个任务的可观察行为。

## 实施记录

| 任务 | 主要文件 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| TASK-01 | schemas/config-state.schema.json、sync_core/status.py | tests/test_config_consistency.py | 已实现 |
| TASK-02 | sync_core/config.py、sync_core/handoff.py、scripts/sync.py | tests/test_config_consistency.py | 已实现 |
| TASK-03 | sync_core/config_status.py | tests/test_config_consistency.py | 已实现 |
| TASK-04 | sync_core/environment.py | tests/test_config_consistency.py | 已实现 |
| TASK-05 | ai-config.ps1、ai-config.command | tests/test_ux_flows.py | 已实现 |
| TASK-06 | sync_core/wizard.py、scripts/sync.py | tests/test_ux_flows.py | 已实现 |
| TASK-07 | sync_core/wizard.py | tests/test_ux_flows.py | 已实现 |
| TASK-08 | sync_core/config_sync.py | tests/test_ux_flows.py | 已实现 |
| TASK-09 | sync_core/status.py、scripts/sync.py | tests/test_ux_flows.py | 已实现 |
| TASK-10 | sync_core/receipts.py | tests/test_ux_flows.py | 已实现 |
| TASK-11 | sync_core/diff_view.py | tests/test_ux_flows.py | 已实现 |
| TASK-12 | sync_core/config_sync.py、sync_core/config.py | tests/test_ux_flows.py | 已实现 |
| TASK-13 | sync_core/restore.py | tests/test_ux_flows.py | 已实现 |
| TASK-14 | sync_core/messages.py、scripts/sync.py | tests/test_config_consistency.py | 已实现 |
| TASK-15 | sync_core/onboarding.py、sync_core/inventory.py | tests/test_onboarding.py | 已实现 |
| TASK-16 | sync_core/onboarding.py | tests/test_onboarding.py | 已实现 |
| TASK-17 | README.md、docs/getting-started.md、docs/troubleshooting.md、docs/advanced.md | 逐条执行文档命令 | 已完成 |
| TASK-18 | docs/acceptance.md | 自动化部分已完成；三机与零基础验收待实机 | 部分完成 |

本次修复的既有缺陷（非新增功能，但影响本计划安全性）：

- `sync_core/handoff.py` 的 `_git` 会在工作区内普通目录上调用 `git ls-remote origin`，Git 向上找到真实仓库的远端并等待凭据输入，导致同步流程无限挂起。已加 `timeout`、`stdin=DEVNULL` 与 `GIT_TERMINAL_PROMPT=0`，并新增 `repo_root()`／`code_facts_for_project()` 在采集前确认目录本身是仓库。
- `sync_core/inventory.py` 会把 `blocked_secret`／`unreadable`／`unsupported`／`path_collision` 的扫描结果一律改写为 `pending_mapping`，把含凭据的来源显示成“确认映射即可启用”。已新增 `_as_candidate()`，只对正常扫描降级为待映射，安全状态原样保留。
- `sync_core/config_status.py` 的 `observed_digest` 丢弃了 `managed_block` 的错误原因，导致**目标文件不存在也会被判为已应用**。已改为保留 missing／no_managed_block／malformed 的区分。
- `sync_core/setup.py` 与 pytest 的 `setup_module` 钩子重名，导致测试无法收集。已重命名为 `sync_core/wizard.py`。
- `sync`／`status`／`diff`／`undo`／`memory-setup`／`project` 曾只输出原始 JSON；`doctor` 只输出英文 JSON。已统一为默认中文、`--json` 结构化，且错误不再抛 traceback。
- `sync_core/config_sync.py` 的 `verified` 要求每个目标都是 `applied`／`pending_sync`，导致“无受管字段”的目标让成功应用永远显示未核验。已改为 `_targets_verified()`。
- `diff` 之前只打印影响说明、不保存选择，TASK-12 实际未落地。已新增 `plan_ownership()` 持久化 share／local／restore 三种归属，并保证敏感值不可共享也不写入覆盖。
- **恢复路径曾是死循环**：手改受管规则区块后 `sync` 报 E3001 并要求“运行 diff 选择处理方式”，但 `diff` 只比较工具配置键、完全忽略规则区块，于是打印“没有需要处理的字段差异”——用户照做之后再次 `sync` 仍然失败，文档承诺的恢复步骤走不通。已让 `diff` 通过 `config_sync.local_drift()` 识别 `rules_block` 漂移并列为单独一行；规则区块只提供 `share`／`restore`（`local` 会被拒绝，因为“只此设备保留不同区块”正是区块结构无法表达的静默分歧）；新增一次性 restore 意图标记，让 `_rules_plan` 在用户明确选择后才会覆盖（仍先备份）；提示语改为只列出该行真正可用的选择。
- `OwnershipError`／`ConfigSyncError` 在 CLI 顶层被 `(ValueError, OSError, RuntimeError)` 一并按字符串猜退出码，用户看到的拒绝理由被降级为笼统的 `E9001`、退出码 1。已新增针对这两类的处理器，保留各自的退出码与错误编号。
- `ai-config.ps1` 在 `.venv` 已存在时仍要求系统 `python` 出现在 PATH 上。已改为优先复用项目环境。

## 测试环境注意

运行测试时必须为每次运行指定**全新的** `--basetemp` 目录：

```text
python -m pytest -q --basetemp=tmp/run-<新编号>
```

复用同一个 `--basetemp` 会让上次运行留下的 `tmp_path` 内容与本次冲突，产生大批与本改动无关的失败（实测同一个目录第二次运行出现 33 个假失败，换新目录后 145 全绿）。

## 用户需提供的信息

- 配置源地址（已有地址需在实施时核对），以及第一台作为初始配置来源的设备。
- 第二台 Windows 和 Mac 的接入机会；路径由检测自动取得。
- 启用记忆时的私有仓库地址；尚未启用不影响配置第一版。
- 独立备份目的地仍沿用原可靠性计划，不因体验改造取消。

字段映射、状态结构、函数拆分和测试实现由执行者完成，不再要求用户做内部技术选择。
