---
project_id: ai-config
updated: 2026-10-02
status: active
overview: 当前转向离线换机迁移工具包，目标是备份并恢复 AI 助手配置、记忆和项目状态；旧桌面客户端及服务器同步方向已冻结。
progress: >-
  2026-10-02 完成换机任务入口与旧方向冻结标记，实施 MK-02 本机依赖分层、隔离 HOME、过期断言和秘密检测修复。Python 3.14 核心环境全量回归 349 passed／2 skipped，秘密扫描 0 命中；CI Windows／macOS 尚未验证，MK-02 不据此宣称全部验收。旧 DT 实现、预览安装包及此前验收仅保留为历史，原生安装、真实 Agent 加载、跨机、服务器与新手试用仍未验收。迁移采集、备份和恢复尚未实现。
next: >-
  按 MACHINE-MIGRATION-TASKS.md 推进 MK-01 私有 wip 分支保存现状、MK-02 CI 核验及 P1 路径／分档／配置／包格式；后续采集、恢复和真机步骤按各自门禁执行，并把结果先写入任务与验收记录。
evidence:
  - MACHINE-MIGRATION-TASKS.md
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

2026-10-01 维护：本轮仅推进不依赖用户外部环境的实现，集中自测只选核心功能。历史 DT 测试保留在原验收记录中，不计为本轮复测。Windows 构建和隔离核心验证不能代替原生窗口、跨设备或真实部署；未执行项继续保持待验收。

正式发布未完成。最新逐项边界、实际命令、结果与产物校验值以 DESKTOP-TASKS.md、docs/desktop-local-implementation.md 和 docs/acceptance.md 为准。本摘要证据只指向仓库内稳定正本，不引用临时运行目录。

同日最终产物记录已同步：Windows 0.2.0 x64 NSIS 为 22,832,992 字节，安装器／源码清单／版权伴随归档哈希核对一致；冻结 sidecar 隔离检查正常退出。42 项证据路径的本地摘要契约检查通过，未使用外部日常同步工具。这些结果没有改变实机和正式发布仍待验收的边界。


2026-10-01 设置页修订维护：本次实际通过前端构建／lint、41 项定向核心测试、使用虚构路径的浏览器布局检查和 Windows 安装包重建。原生安装与真实 Agent 加载没有复测；同日先前 sidecar／服务器实现及版权收集属于保留历史证据。新安装包／旧包备份／哈希以 docs/acceptance.md 本次新增节为准，上文同日产物数值是修订前历史值。未调用外部日常库同步工具。

本次交付前摘要字段与 50 项稳定 evidence 路径自检通过；未使用外部日常同步工具。该检查不代表未执行的实机验收完成。
