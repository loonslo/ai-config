---
project_id: ai-config
updated: 2026-10-15
status: active
overview: 桌面客户端为唯一用户入口，只保留 ZIP 原样备份、恢复、核验和撤销；云端继续冻结，不提供用户内容托管。
progress: >-
  2026-10-15 完整回归 735 通过、3 跳过，桌面构建/lint 与凭据扫描通过，已提交推送；补齐 CI 测试依赖；云端 macOS 18 项失败；Windows 唯一包示例失败源于 Git 换行，已声明 .bin 非文本并补验，跨平台仍未通过。原生安装和真实跨机未复验。
  2026-10-08 已接入三页桌面流程与 machine 引擎，替换旧 .aiconfig 界面并拒绝旧云端及包操作；项目选择与映射、安全和信任确认、冲突另存、自动核验与撤销已实现。Windows Python 3.14 隔离相关回归 56 passed，前端构建和 lint、Windows sidecar 与 0.3.0 NSIS 构建通过，冻结 sidecar 在合成 HOME、无外置 Python/Git PATH 中完成备份到撤销全流程。上述不代表原生安装、窗口交互或真实跨机加载验收。2026-10-02 的隐私修正版备份及 101 项隔离测试属于历史记录，本次未刷新或恢复真实助手数据。
  本日随后针对安装反馈修正宽屏根布局，加入检测超时重试和完整行响应兼容；5 个宽度与静默响应的浏览器夹具检查、前端构建和 0.3.1 NSIS 构建通过。用户确认 0.3.0 检查备份一直等待，复现外部 Git 继承请求输入管道的阻塞并以 DEVNULL 修复；相关 21 项回归及正常软件 PATH 的冻结 sidecar 全流程通过，0.3.2 Windows 安装包构建通过并保存发布清单。原生窗口与修复包升级仍待用户现场复测。
  0.3.2 Windows x64 安装包已作为 GitHub 预发布公开，附 SHA-256 清单和完整 NOTICE；资产哈希与本地一致，172 个源码文件哈希对应干净提交。原生升级、签名和真实跨机加载仍未验收。
  2026-10-09 发现 v0.3.2 标签仍在但 GitHub Release 记录已缺失，重建预发布并重新上传安装包；匿名下载请求返回 200，长度及 GitHub SHA-256 与本地一致。
  同日用户提供的 ZIP 完整校验通过（134 个条目），已安装 sidecar 的未转义 UTF-8 中文路径请求复现误报损坏。已将请求输入管道明确设为 UTF-8；Windows Python 3.14 输入管道、桌面协议与包校验 35 项回归通过，重建冻结后端以原包和中文路径完成隔离恢复预览，原包哈希未变。0.3.3 前端、sidecar 和 Windows NSIS 构建完成，安装包及源码/产物清单保存在本地，未发布新版本；原生升级和真实恢复未验收。
  同日按用户反馈实现按已有文件选择覆盖或保留、覆盖前完整备份、保留原文件字节不变，支持撤销；核验默认按助手和类型汇总，可展开具体文件/字段，未选择助手合并，保留或部分字段不再误报完全一致。33 项相关测试、浏览器夹具及冻结后端覆盖/保留/撤销两条隔离流程通过；0.3.4 前端、sidecar、Windows NSIS 和 lint 通过，本地安装包、NOTICE 与源码/产物清单已保存。原生升级、现场覆盖和真实加载仍待验收，未发布新远程版本。
  同日进一步修正禁用按钮误显示等待，移除常驻重新检查步骤；覆盖/保留和选项变更自动更新只读计划，选完可直接确认恢复。工作文件夹与信任名单按用途标注、去重并默认折叠。0.3.5 TypeScript/Vite、lint 和 Windows NSIS 构建通过，既有浏览器夹具查看灰色禁用、自动更新/确认及完成页面，本地安装包/NOTICE/源码清单校验通过；本轮未新增或运行测试套件，目录/信任新展示和原生窗口待现场验收。
  同日用户授权执行同步分类方案并接受第三方源码边界、全部已登记项目和默认脱敏三项选择。分类表 72 个 ID、既有来源覆盖观察与默认项目检测已实现；Windows Python 3.14 合成 HOME 最终 machine 回归 139 passed、1 skipped（符号链接权限不足），实际携带文件条目/哈希/字节开关对比一致。字段报告仅目标定性，新来源尚未接入；脱敏、manifest v2、新增采集/恢复、分组及历史仍未实现，真实跨机未验收，本次未重建安装包。
  随后继续实施：七类凭据识别、邮箱放行、脱敏/跳过和恢复提示已接入；默认写 v2并兼容 v1，新增全局及项目 A/B 复合往返核对 18 个文件。此阶段修复旧向导后最终 168 passed、1 skipped。又接入账号技能、多账号导出、用户环境变量、七级技能来源与批准链接；Windows Python 3.14 合成 HOME 最终完整 machine 回归 180 passed、1 skipped，96.64 秒，新增联接点四边界均通过。来源明确第三方启发式示例原样往返、自建二进制保留、第三方程序排除及 PowerShell 导出脚本仅语法解析通过。失败轮次和夹具调整记录在实施文件。覆盖联动、部分逐规则补验、分组、历史与真实迁移仍未完成；未读取真实新来源或构建安装包。
  同日接入内容分组、桌面脱敏/跳过自动预览、技能分组冲突及输出卫生。完整 machine 回归 191 passed、1 skipped（98.83 秒）；其后项目定制分组及缺摘要副本的直接相关 16 项通过。前端构建/lint 和 localhost 合成浏览器交互通过。历史分包仍未实现，CLI 全输出及专家完整生命周期和真实跨机仍待验收，未重建安装包。
  随后细化历史实施契约并实现 ZIP64 流式核心，17 项合成专项通过，包含单文件跨包、集合/正文门禁与无硬链接文件系统；本阶段完整 machine 回归 209 passed、1 skipped（103.89 秒），最后边界改动直接相关 17 项通过。主包协调与历史恢复事务尚未接通，历史界面仍不可用；没有读取真实会话。
  随后接通历史备份主包协调及桌面协议，合成端到端与发布失败回滚通过，阶段完整 machine 回归 214 passed、1 skipped（108.51 秒），其后最后直接相关 29 passed（14.88 秒）。历史恢复事务、完整界面与 Codex 非 JSONL 格式仍待补齐，未读取真实会话或重建安装包。
  又接入共享流式事务与撤销设施：混合批次、大于 64 MiB 文件、失败回滚、中断恢复及后改冲突直接相关测试通过。共享层全仓回归 576 passed、3 skipped、1 failed（旧助手数量断言，已修订），最新相关 38 passed；未再次全仓复测。历史包恢复路径尚未接入，不能视为会话恢复全流程完成。
  随后接通 JSONL 历史恢复业务与协议：整组前置校验、未选零读取、只新增/另存、Claude 项目映射及未映射报告目录、流式事务/核验/撤销通过。完整 machine 回归 232 passed、1 skipped（114.04 秒），其后最后相关 46 passed，相邻命名再收紧后 14 passed；界面、Codex 非 JSONL 及真实加载仍待完成。
  同日补充 UTF-16/UTF-32 与混合编码凭据检测和字节范围脱敏，专项 39 passed（含二进制技能策略门禁）；历史全局行号预算及相关恢复/隐私 75 passed（19.39 秒）。界面分包摘要/行号截断说明已实现，build/lint 通过；全仓回归 618 passed、3 skipped（262.63 秒，无失败），新增四项策略测试另计入最后专项 39 passed；跳过为 jwt 缺依赖及两处符号链接权限限制。该面板浏览器、非 JSONL 历史及真实跨机仍待验收。
  又接入 Codex 非 JSONL 文本/二进制历史、UTF-16/32 JSONL 重组校验与跨行私钥整体脱敏；含二进制恢复/核验/撤销的相关 112 passed。完整 machine 回归 301 passed、2 skipped、357 deselected（160.89 秒），最后 UTF-32 无效正文修订相关 76 passed（19.03 秒）；超长无换行记录与结构化脱敏复查预算仍有显式排除，界面交互、覆盖联动与真实助手加载仍待完成。
  随后接通账号技能/批准链接/环境变量名称与历史覆盖账本，第三方与产物分桶、成功历史来源计数及幂等携带通过；账号 .pyc 遗漏已修复。最后相关 45 passed、1 skipped（8.15 秒），完整 machine 回归 306 passed、2 skipped、357 deselected（151.67 秒，无失败）；仍未读真实新增来源。
  同名相同技能三个位置的独立成员、恢复六文件/字节一致、六项核验与事务撤销补验通过，技能来源专项 4 passed（2.51 秒）；只新增夹具，未再次全量复测或访问真实来源。
  同日补齐技能/账号技能长路径在正文读取前排除、读取失败明细及部分内容恢复/账号导出；相关 20 passed。排除重复计数已复现并修正，阶段 machine 回归 309 passed、2 skipped、357 deselected（172.65 秒），最后去重修改及账号新增用例相关 23 passed（14.76 秒）；目录枚举/stat 和嵌套边界尚未验收。
  又复现并修复父/子项目同时选择时 WorkBuddy AI 子项目技能重复采集，最长路径归属过滤及两种顺序的项目映射恢复通过；相关 13 passed（6.47 秒），未再次完整 machine 复测。
  同日补普通技能容器/子目录枚举及单文件 stat 失败明细、未知大小与覆盖未完成状态，相关 20 passed、1 skipped（7.56 秒）；备份预览增加失败清单与不完整提示，build/lint 通过，浏览器新列表未验收。完整 machine 回归 316 passed、2 skipped、357 deselected（174.74 秒，无失败）。G10 已询问、尚未收到答复，未访问真实新增来源。
  同日补验历史默认不选、分包摘要、行号样本截断/空样本、整份跳过自动更新与恢复计划更新禁用，localhost 合成传输浏览器通过并保存截图；统一重复失败列表为最多 20 项及中文原因。前端 build/lint 通过。账号技能枚举/stat 失败报告与覆盖账本已知失败合并修正，最后相关 39 passed、1 skipped（14.47 秒）；完整 machine 回归 323 passed、2 skipped、357 deselected（146.29 秒，无失败），跳过为 jwt 缺依赖和符号链接权限。没有读取真实新增来源或重建安装包；158 条稳定证据路径与摘要契约本地自检通过。
  随后补验全部八种 v1 条目类型/四助手的完整合成恢复、设置合并/项目信任、重复零写入、核验及撤销，专项 15 passed（5.42 秒）。复现并接入 CC-14 登记项目 MCP，点号路径层级与 Windows 已有键复用、确认/保留其它字段/核验/撤销通过；MCP 叶级白名单和无 Git 两分支补验，最后相关 48 passed（31.39 秒）。完整 machine 回归 347 passed、2 skipped、357 deselected（158.83 秒，无失败），跳过为 jwt 缺依赖和符号链接权限；真实旧包完整恢复/新来源/跨机仍未验收。
  又补多项目与全局 MCP 共用登记文件的合成覆盖/保留/核验/单次备份写入/撤销，专项 2 passed、24 deselected（1.60 秒）；安全确认列表增加项目和实例归属，相关 36 passed（18.84 秒），localhost 合成浏览器与 build/lint 通过。完整 machine 回归 349 passed、2 skipped、357 deselected（161.77 秒，无失败），跳过为 jwt 缺依赖和符号链接权限；启动后扩充的邮箱项目路径场景单独 3 passed（3.27 秒），未读取真实来源。159 条稳定证据与摘要契约本地自检通过。
  随后复现并修复多来源映射到同一目标字段时后一值无声覆盖前值：实际获准字段的不同值在计划阶段拒绝，相同值/不重叠字段/明确保留继续允许。相关 42 passed（25.93 秒），新增协议期待修正后专项 4 passed、26 deselected（3.10 秒），拒绝不发计划/原件不变及保留一份后恢复核验通过。最终完整 machine 回归 353 passed、2 skipped、357 deselected（150.12 秒，无失败），所有本轮变更均已收集；密钥扫描、diff 和 159 条证据路径本地契约自检通过。真实来源、原生与跨机仍未验收。
  随后复现并修复专家 CLI 直接输出路径邮箱；JSON 序列化前清理展示副本。文本/JSON 与默认脱敏/专家原样保留四组合的最小 Codex v2 备份到撤销通过，相关 10 passed（8.32 秒）。最终完整 machine 回归 357 passed、2 skipped、357 deselected（160.19 秒，无失败），所有本轮变更均已收集；密钥扫描、diff 及 159 条证据本地契约自检通过。所有种类与参数全流程、真实来源和跨机仍未完成。
  同日用户追加完全不读取 Git、助手文件按白名单携带，覆盖原跟踪筛选与 Git 来源规则；运行流程移除 Git 根/索引/远端/HEAD/脏状态/凭据/版本查询及新包 Git 字段。中文项目四种 Git 状态下 18 个助手文件均携带，恢复/核验/撤销与 Git 命令/目录/正文零读取哨兵通过；相关 86 passed，强化专项 4 passed（9.42 秒）。完整 machine 回归 361 passed、2 skipped、357 deselected（167.11 秒，无失败）；其后补修仅排除 Git 不提示重建，最后相关 59 passed（31.69 秒）；完整回归早于这项最后修改。密钥扫描 0 findings、diff 与 159 条证据路径/摘要契约本地自检通过。未访问真实来源或重建安装包。
  用户随后要求重建安装包，已生成本地 0.3.6 Windows x64 NSIS；前端/冻结后端/NSIS 构建与 lint 通过，冻结后端在合成 HOME、中文 UTF-8 管道及无外置 Python/Git PATH 完成 v2 备份/Git 排除与覆盖/保留/核验/撤销。194 个源码及产物哈希核对通过，322 项 NOTICE 覆盖当前 Windows 依赖；密钥扫描 0 findings、diff 与 162 条证据/摘要契约本地自检通过。未自动安装、远程发布或验收真实加载。
  2026-10-10 针对 0.3.6 检查备份隐私错误，只读诊断定位技能资源 ask- 文件名中的 sk- 被当作 token；起始边界修复、安全分类错误及长字符扫描优化已实现，最后相关 86 项和历史/环境/账号技能/链接相关 95 项通过。实际来源修订后隐私门禁通过但采集变更保护停止，不能作为完整真实备份通过；关闭覆盖统计/软件探测的诊断范围、失败夹具及未执行全量回归均记录于 acceptance。0.3.7 Windows sidecar/前端/NSIS 构建与 lint 通过，冻结后端合成 ask- 文件名检查/生成 ZIP 和覆盖/保留/核验/撤销通过，194 源文件及产物哈希一致；最终密钥扫描 0 findings、diff 与 165 条稳定证据/摘要契约自检通过；原生升级预检仍待用户复测。
  2026-10-11 按 frontend-design 技能优化三页布局，默认 940 px 窗口保留备份两列，窄屏改为上下分区和顶栏导航；最终 TypeScript/Vite 构建与 lint 通过。既有合成浏览器验证备份预览、恢复冲突覆盖/保留、自动更新禁用、确认与核验失败展开；备份及恢复报告在六种宽度无横向溢出，记录空态通过。验收边界和截图见 ui-layout 与 acceptance；未运行后端测试或重建安装包，原生与真实跨机仍未验收。既有 0.3.7 产物及源码哈希仍为 2026-10-10 历史交付，不包含本次 UI。
next: >-
  将新版页面打入新的 Windows 安装包，并补原生布局和完整键盘操作验收。
  优先由用户安装 0.3.7 后在原生窗口重试检查备份；保持真实凭据拦截及来源变更保护，核对实际内容选择与来源稳定条件。
  继续补验 SC-03 全种类及专家参数完整生命周期、SC-05 独立规则/字段账本/设备偏好、SC-08 其余嵌套边界，补齐原始二进制超长记录/结构化复查预算边界并核对剩余覆盖边界，补全扫描进度明细。复用当前合成 HOME 与逐规则往返验收；真实旧包新版完整恢复、账号真实布局、SC-06 历史项目覆盖、原生界面及真实跨机仍待验收。
  由用户安装 0.3.6 后在原生窗口重试中文 ZIP 路径，核对灰色禁用、自动更新计划、带说明的目录/信任名单、已有配置选择、原文件备份及撤销；在净室验证 Windows 安装与三页窗口、选择器、ZIP 拖入、退出时写入保护及旧版本关联清理，再进行第二台电脑恢复、真实助手加载和新手试用，Mac 单独验收。云端保持冻结，旧命令脚本仅为历史开发兼容。结果先写当前离线任务与验收记录，再维护本摘要。
evidence:
  - docs/ui-layout.md
  - desktop/src/UiIcon.tsx
  - release-artifacts/AI-Config-0.3.7-Windows-manifest.json
  - release-artifacts/AI-Config-0.3.7-Windows-NOTICES-full.zip
  - release-artifacts/AI-Config-0.3.7-Windows-x64-setup.exe
  - release-artifacts/AI-Config-0.3.6-Windows-manifest.json
  - release-artifacts/AI-Config-0.3.6-Windows-NOTICES-full.zip
  - release-artifacts/AI-Config-0.3.6-Windows-x64-setup.exe
  - sync_core/machine/history_restore.py
  - tests/test_machine_history_restore.py
  - sync_core/streaming.py
  - sync_core/transaction.py
  - tests/test_machine_stream_transaction.py
  - docs/machine-sync-history-contract.md
  - sync_core/machine/history.py
  - tests/test_machine_history.py
  - sync_core/machine/groups.py
  - tests/test_machine_groups.py
  - tests/test_machine_output_privacy.py
  - release-artifacts/machine-sync-groups-preview.png
  - release-artifacts/machine-sync-restore-groups-preview.png
  - sync_core/machine/settings.py
  - sync_core/machine/exports.py
  - sync_core/machine/source_roots.py
  - sync_core/machine/collect_classified.py
  - tests/test_machine_redaction.py
  - tests/test_machine_manifest_v2.py
  - tests/test_machine_restore_new_kinds.py
  - sync_core/machine/collect_env.py
  - sync_core/machine/collect_desktop_skills.py
  - sync_core/machine/collect_skills.py
  - sync_core/machine/provenance.py
  - sync_core/machine/skills_links.py
  - tests/test_machine_env_export.py
  - tests/test_machine_collect_desktop_skills.py
  - tests/test_machine_provenance.py
  - tests/test_machine_skills_links.py
  - tests/test_machine_collect_classified.py
  - docs/machine-sync-execution.md
  - docs/machine-sync-plan.md
  - docs/machine-sync-classification.md
  - docs/machine-sync-interfaces.md
  - sync_core/machine/classification_rules.py
  - sync_core/machine/coverage.py
  - tests/test_machine_classification.py
  - tests/test_machine_coverage.py
  - tests/test_machine_default_projects.py
  - tests/test_machine_restore_choices.py
  - desktop/src/RestoreReport.tsx
  - tests/test_machine_process_input.py
  - MACHINE-MIGRATION-TASKS.md
  - sync_core/machine/privacy.py
  - tests/test_machine_privacy.py
  - tests/test_machine_exclusions.py
  - sync_core/machine/paths.py
  - sync_core/machine/catalog.py
  - sync_core/machine/config.py
  - sync_core/machine/bundle.py
  - tests/test_machine_bundle.py
  - tests/test_machine_import_direction.py
  - sync_core/machine/collect_records.py
  - sync_core/machine/collect_tier1.py
  - tests/test_machine_collect_tier1.py
  - sync_core/machine/collect_projects.py
  - tests/test_machine_collect_projects.py
  - docs/machine-migration-workbuddy.md
  - sync_core/machine/collect_workbuddy.py
  - tests/test_machine_collect_workbuddy.py
  - sync_core/machine/collect_reinstall.py
  - tests/test_machine_collect_reinstall.py
  - sync_core/machine/collect_login.py
  - tests/test_machine_collect_login.py
  - sync_core/machine/backup.py
  - tests/test_machine_backup.py
  - sync_core/machine/guided.py
  - sync_core/machine/guide_backup.py
  - sync_core/machine/guide_restore.py
  - tests/test_machine_guided_restore.py
  - tests/test_machine_cli.py
  - 恢复.cmd
  - 恢复.command
  - docs/machine-cleanroom-checklist.md
  - sync_core/machine/preflight.py
  - sync_core/machine/apply.py
  - tests/test_machine_apply.py
  - tests/test_machine_trust.py
  - tests/test_machine_memory_restore.py
  - tests/test_machine_workbuddy_restore.py
  - sync_core/machine/verify.py
  - sync_core/machine/undo.py
  - tests/test_machine_verify_undo.py
  - sync_core/restore.py
  - sync_core/machine/procs.py
  - tests/test_machine_preflight.py
  - tests/test_machine_guided_backup.py
  - scripts/machine.py
  - scripts/start.py
  - tests/test_start_bootstrap.py
  - tests/test_launchers.py
  - 备份.cmd
  - 备份.command
  - docs/quickstart.md
  - docs/python-required.txt
  - ai-config.ps1
  - ai-config.command
  - DESKTOP-TASKS.md
  - docs/desktop-local-implementation.md
  - docs/acceptance.md
  - docs/third-party-licenses.md
  - task.md
  - TODO.md
  - README.md
  - desktop/README.md
  - docs/desktop-client-plan.md
  - docs/desktop-rpc.md
  - docs/package-format.md
  - docs/server-architecture.md
  - docs/server-deployment.md
  - sync_core/application/service.py
  - sync_core/application/protocol.py
  - sync_core/package/extensions.py
  - sync_core/package/mapping.py
  - sync_core/package/conflicts.py
  - sync_core/package/importer.py
  - sync_core/cloud/client.py
  - sync_core/cloud/crypto.py
  - sync_core/cloud/vault.py
  - desktop/src/App.tsx
  - desktop/src/App.css
  - desktop/src/index.css
  - docs/getting-started.md
  - tests/test_agent_contract.py
  - tests/test_verify_load.py
  - tests/test_onboarding.py
  - tests/test_migrate.py
  - tests/test_sync.py
  - desktop/src/CloudPanel.tsx
  - desktop/src/LocalToolsPanel.tsx
  - desktop/src-tauri/capabilities/default.json
  - desktop/src-tauri/tauri.conf.json
  - desktop/requirements-windows.lock.txt
  - server/app.py
  - server/models.py
  - server/openapi.json
  - server/requirements.lock.txt
  - deploy/compose.yaml
  - deploy/maintenance.py
  - scripts/build-desktop-sidecar.ps1
  - scripts/build-desktop-sidecar.py
  - scripts/collect-release-notices.py
  - scripts/release-manifest.py
  - schemas/desktop-rpc.schema.json
  - schemas/package.schema.json
  - tests/test_desktop_extensions.py
  - tests/test_cloud_core.py
  - docs/desktop-offline-migration.md
  - sync_core/application/machine_protocol.py
  - tests/test_machine_desktop.py
  - desktop/src/MachineApp.tsx
  - desktop/src/Machine.css
  - schemas/machine-desktop-rpc.schema.json
  - desktop/vite.config.ts
  - desktop/index.html
  - desktop/tests/tauri-fixture.ts
  - release-artifacts/machine-sync-history-browser-preview.png
  - release-artifacts/machine-sync-history-browser-restore.png
  - release-artifacts/machine-sync-mcp-project-confirmation.png
---


2026-10-08 维护：负责人澄清桌面客户端继续推进，只保留原样备份恢复 ZIP，云端继续冻结。本次实现、56 项相关回归、Windows 构建及冻结 sidecar 隔离演练结果见 docs/acceptance.md 与 docs/desktop-offline-migration.md。以下 2026-10-01／02 段落保留为历史，原生安装、真实跨机及加载未重新验收。本次未使用外部日常同步工具。


# AI 配置同步 · 项目概览与进度

2026-10-02 方向调整：旧桌面客户端、服务器／云同步和受管区块同步冻结；本轮开始实施 `MACHINE-MIGRATION-TASKS.md`。MK-00 文档入口及状态同步已完成；MK-02 本机核心环境全量测试和秘密扫描通过，GitHub Actions 跨平台 CI 尚未验证。原进展记录日期为 2026-10-01，以下历史段落没有重新验收，具体本轮命令与范围见 `docs/acceptance.md`。本次未使用外部日常库同步工具。

同日继续实施 P1：路径、分档、配置、包格式与隔离夹具的 37 项定向测试通过；MK-10/11/12 的真机或整包验收尚未完成。首次跨平台 CI 因缺 `tmp/` 导致 pytest setup 失败，已本地修正，尚待新的 CI 运行验证；这不算 MK-02 通过。结果和边界见 `docs/acceptance.md`。

同日 P2 更新：MK-22 项目档案在合成 HOME 验证，并在本次单独 G2 授权下完成真机只读内存预览；11 个核心文件夹与 7 个本地权限文件均被识别，Claude Desktop 会话登记目录当前为空。详细计数、旧基线差异及未验证边界见 `docs/acceptance.md`。尚未生成真实备份包或运行恢复。

同日继续：WorkBuddy 结构调研与保守分档已获 G7 批准，重装／登录报告和完整备份命令已在沙箱组装验证；真机命令只读预览 200 条。MK-26 的真实 apply 和 M1 核对仍未完成，不能据此宣称换机成功。最新命令与范围见 `docs/acceptance.md`；未使用外部日常库同步工具。

2026-10-01 维护：本轮仅推进不依赖用户外部环境的实现，集中自测只选核心功能。历史 DT 测试保留在原验收记录中，不计为本轮复测。Windows 构建和隔离核心验证不能代替原生窗口、跨设备或真实部署；未执行项继续保持待验收。

正式发布未完成。最新逐项边界、实际命令、结果与产物校验值以 DESKTOP-TASKS.md、docs/desktop-local-implementation.md 和 docs/acceptance.md 为准。本摘要证据只指向仓库内稳定正本，不引用临时运行目录。

同日最终产物记录已同步：Windows 0.2.0 x64 NSIS 为 22,832,992 字节，安装器／源码清单／版权伴随归档哈希核对一致；冻结 sidecar 隔离检查正常退出。42 项证据路径的本地摘要契约检查通过，未使用外部日常同步工具。这些结果没有改变实机和正式发布仍待验收的边界。


2026-10-01 设置页修订维护：本次实际通过前端构建／lint、41 项定向核心测试、使用虚构路径的浏览器布局检查和 Windows 安装包重建。原生安装与真实 Agent 加载没有复测；同日先前 sidecar／服务器实现及版权收集属于保留历史证据。新安装包／旧包备份／哈希以 docs/acceptance.md 本次新增节为准，上文同日产物数值是修订前历史值。未调用外部日常库同步工具。

本次交付前摘要字段与 50 项稳定 evidence 路径自检通过；未使用外部日常同步工具。该检查不代表未执行的实机验收完成。

2026-10-02 MK-26／27：G3 首份真机备份与 M1 人工核对已通过，新手备份向导隔离测试通过；上文只读预览／尚未生成真实备份的表述属于同日早先过程。恢复、双击真机、U 盘及跨机加载尚未验收；本次未使用外部日常库同步工具。

2026-10-02 MK-28：双击入口与运行环境引导实现，14 项隔离／静态测试及 cmd.exe 提示片段检查通过；真实双击、Windows Terminal、默认执行策略、拦截及 Mac 尚未验收。

2026-10-02 MK-30：只读目标解析和逐项／字段比较的 5 项测试通过，未运行真实目标恢复；P3 正在推进。

2026-10-02 MK-31：核心事务写入、冲突与回滚隔离测试通过；记忆／信任／WorkBuddy、自动核验及撤销正在推进，真实目标写入未授权或执行。

2026-10-02 MK-32：Codex 信任还原哈希门禁与注释／未知字段保留、冲突及幂等沙箱测试通过；真实信任仍需 G5，未执行。

2026-10-02 MK-33：记忆目标目录推导、大小写复用、索引冲突与原样字节的隔离测试通过；真实记忆加载尚未验收。

2026-10-02 MK-34：明确选择后的 WorkBuddy 候选文本落盘沙箱通过，受保护诱饵零读取／不变；真实加载继续未验证。

2026-10-02 MK-35／36：自动文件／字段核验、破坏检出及完整撤销沙箱通过，共用接口相关 54 项回归通过。登录／真实加载为人工项；净室仍未提供。

2026-10-02 P3：恢复向导与专家 CLI 等价验证完成，合并 91 项测试全部通过。当前等待 G8 净室进行真实演练；91 项自动测试不代表附录 B 签收、真实加载或零基础试用通过。净室准备清单仅记录准备步骤。未调用外部同步工具，未推送未授权分支。

2026-10-02 交付复查：补齐配置排除与邮箱／URL 用户信息检测后合并 101 passed。首份 ZIP 的 4 个文本文件命中邮箱格式，原 M1 为历史范围确认，不能据此称原包隐私通过；另获本次 G3，从原包既有快照生成 196 条修正版并核对通过，未刷新源数据，原包哈希不变。负责人明确暂时没有净室，跟进状态改为 waiting；具体产物哈希、排除项及未验收边界见 acceptance。105 项证据路径及摘要字段本地自检通过，未使用外部日常同步工具。

2026-10-08 交付前本地自检：必填和唯一字段、日期、跟进状态、非空摘要及 111 项稳定 evidence 路径通过；未使用外部日常库同步工具。发布清单与当前源码／安装包校验一致。这不改变原生安装、窗口交互和跨机加载仍未验收的边界。

2026-10-08 安装反馈维护：OF-07 布局根因及通信假设纠正、已安装后端只读检测、浏览器夹具结果和 0.3.1 构建写入 acceptance。原生窗口截图超时，具体卡步骤和升级仍未验收，不将浏览器夹具当作真实窗口证据。

2026-10-08 OF-08：用户补充 0.3.0 检查备份阶段一直等待，复现并修复外部探测继承持续打开的请求输入管道；21 项相关回归、无控制台管道回归复跑、正常 PATH 冻结 sidecar 全链通过，0.3.2 安装包构建完成。摘要契约和 115 项 evidence 路径本项目内自检通过，发布源文件及产物哈希一致；现场升级和跨机验收仍未完成。

## 2026-10-15 提交验证

完整 Python 3.14 回归 735 passed、3 skipped，前端构建/lint 与凭据扫描通过；未重建安装包或执行真实跨机验收。证据见 docs/acceptance.md。
