---
project_id: ai-config
updated: 2026-10-02
status: waiting
overview: 当前转向离线换机迁移工具包，目标是备份并恢复 AI 助手配置、记忆和项目状态；旧桌面客户端及服务器同步方向已冻结。
progress: >-
  2026-10-02 完成换机任务入口与旧方向冻结标记；MK-01 经当次授权分四个主题提交并推送到私有 wip/machine-kit-baseline。MK-02 本机 Python 3.14 核心回归 349 passed／2 skipped；首次跨平台 CI 因缺 tmp 目录未运行测试，修复待推送复测。P1 路径、分档、可选配置、zip 与夹具通过；MK-10 已授权只读核对 8/8 一致，另 7 个目录无对应键。P2/P3 已实现批准范围的采集、备份、恢复、核验、撤销、向导与启动器，WorkBuddy 保持手动候选。交付复查补齐专家采集排除与邮箱／URL 用户信息门禁，合并隔离测试 101 passed。首份 200 条快照曾获 M1 范围确认，但后续发现 4 个文件命中邮箱格式；另获本次 G3，从原 ZIP 既有快照生成 668504 B、196 条／11 项目的修正版，整体隐私检测 0 命中，原 ZIP 哈希不变，未重新读助手目录。历史基线差异按原快照记录；历史排除基线、U 盘、真实恢复与加载仍待验收。旧 DT 仅保留历史。
next: >-
  负责人明确暂时没有净室，等待 G8 环境后再做 MK-41／42，以隐私修正版作为演练输入。MK-28 真实双击另需 G3＋G2，目标写入须 G4，信任须 G5，新手试用须 G9。修复后的 CI 待授权推送；Claude Desktop 登记目录为空与 WorkBuddy 加载机制仍待核实。每次真机写入按对应门禁执行，结果先写任务与验收记录。
evidence:
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
---

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
