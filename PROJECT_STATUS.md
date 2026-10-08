---
project_id: ai-config
updated: 2026-10-09
status: active
overview: 桌面客户端为唯一用户入口，只保留 ZIP 原样备份、恢复、核验和撤销；云端继续冻结，不提供用户内容托管。
progress: >-
  2026-10-08 已接入三页桌面流程与 machine 引擎，替换旧 .aiconfig 界面并拒绝旧云端及包操作；项目选择与映射、安全和信任确认、冲突另存、自动核验与撤销已实现。Windows Python 3.14 隔离相关回归 56 passed，前端构建和 lint、Windows sidecar 与 0.3.0 NSIS 构建通过，冻结 sidecar 在合成 HOME、无外置 Python/Git PATH 中完成备份到撤销全流程。上述不代表原生安装、窗口交互或真实跨机加载验收。2026-10-02 的隐私修正版备份及 101 项隔离测试属于历史记录，本次未刷新或恢复真实助手数据。
  本日随后针对安装反馈修正宽屏根布局，加入检测超时重试和完整行响应兼容；5 个宽度与静默响应的浏览器夹具检查、前端构建和 0.3.1 NSIS 构建通过。用户确认 0.3.0 检查备份一直等待，复现外部 Git 继承请求输入管道的阻塞并以 DEVNULL 修复；相关 21 项回归及正常软件 PATH 的冻结 sidecar 全流程通过，0.3.2 Windows 安装包构建通过并保存发布清单。原生窗口与修复包升级仍待用户现场复测。
  0.3.2 Windows x64 安装包已作为 GitHub 预发布公开，附 SHA-256 清单和完整 NOTICE；资产哈希与本地一致，172 个源码文件哈希对应干净提交。原生升级、签名和真实跨机加载仍未验收。
  2026-10-09 发现 v0.3.2 标签仍在但 GitHub Release 记录已缺失，重建预发布并重新上传安装包；匿名下载请求返回 200，长度及 GitHub SHA-256 与本地一致。
next: >-
  在净室验证 Windows 安装与三页窗口、选择器、ZIP 拖入、退出时写入保护及旧版本关联清理；再进行第二台电脑恢复、真实助手加载和新手试用，Mac 单独验收。云端保持冻结，旧命令脚本仅为历史开发兼容。结果先写当前离线任务与验收记录，再维护本摘要。
evidence:
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
