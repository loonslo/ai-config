---
project_id: ai-config
updated: 2026-10-02
status: active
overview: 当前转向离线换机迁移工具包，目标是备份并恢复 AI 助手配置、记忆和项目状态；旧桌面客户端及服务器同步方向已冻结。
progress: >-
  2026-10-02 完成换机任务入口与旧方向冻结标记；MK-01 经当次授权分四个主题提交并推送到私有 wip/machine-kit-baseline。MK-02 本机 Python 3.14 核心环境全量回归 349 passed／2 skipped、秘密扫描 0 命中；首次跨平台 CI 因缺 tmp 目录而未运行测试，修复待推送复测。P1 路径、分档、可选配置、新 zip 格式及夹具已实现；经单独授权的 MK-10 路径核对在有登记键的转录目录上 8/8 一致，另有 7 个转录目录未对应登记键。P2 软件清单与①档采集器已在沙箱验证，本机内存预览得到 91 条，93 个已读源文件二次核对哈希／mtime 不变；与旧基线差异经负责人确认使用当前快照继续核对。MK-22 合成测试 4 passed；经单独授权的真机只读预览为 11 个核心项目、7 个权限文件／135 条规则，Claude Desktop 登记目录现无 JSON。整包备份及 U 盘未验收。旧 DT 仅保留历史；恢复尚未实现。
next: >-
  按 MACHINE-MIGRATION-TASKS.md 在 feat/machine-kit 完成 P2 重装／登录清单和组包命令；修复后的 CI 待授权推送核验。MK-22 的旧基线差异、Desktop 登记目录为空待核实。真机备份写入、恢复与 WorkBuddy 分档按各自门禁执行，结果先写任务与验收记录。
evidence:
  - MACHINE-MIGRATION-TASKS.md
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

2026-10-01 维护：本轮仅推进不依赖用户外部环境的实现，集中自测只选核心功能。历史 DT 测试保留在原验收记录中，不计为本轮复测。Windows 构建和隔离核心验证不能代替原生窗口、跨设备或真实部署；未执行项继续保持待验收。

正式发布未完成。最新逐项边界、实际命令、结果与产物校验值以 DESKTOP-TASKS.md、docs/desktop-local-implementation.md 和 docs/acceptance.md 为准。本摘要证据只指向仓库内稳定正本，不引用临时运行目录。

同日最终产物记录已同步：Windows 0.2.0 x64 NSIS 为 22,832,992 字节，安装器／源码清单／版权伴随归档哈希核对一致；冻结 sidecar 隔离检查正常退出。42 项证据路径的本地摘要契约检查通过，未使用外部日常同步工具。这些结果没有改变实机和正式发布仍待验收的边界。


2026-10-01 设置页修订维护：本次实际通过前端构建／lint、41 项定向核心测试、使用虚构路径的浏览器布局检查和 Windows 安装包重建。原生安装与真实 Agent 加载没有复测；同日先前 sidecar／服务器实现及版权收集属于保留历史证据。新安装包／旧包备份／哈希以 docs/acceptance.md 本次新增节为准，上文同日产物数值是修订前历史值。未调用外部日常库同步工具。

本次交付前摘要字段与 50 项稳定 evidence 路径自检通过；未使用外部日常同步工具。该检查不代表未执行的实机验收完成。
