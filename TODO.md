# 三機同步交接待辦

> 当前决策（2026-10-08）：桌面客户端恢复推进，只保留原样备份恢复 ZIP；云端继续冻结，命令向导不作为用户入口。以下旧冻结范围及旧 `.aiconfig`／终端交付任务属于历史记录，与本声明冲突处以 [桌面离线迁移任务](docs/desktop-offline-migration.md) 为准。


> 状态：已冻结；2026-10-02 起由 [MACHINE-MIGRATION-TASKS.md](MACHINE-MIGRATION-TASKS.md) 取代。下文验收记录均为历史记录。

## 当前实施任务（2026-10-01）

详细工作与验收以 [DESKTOP-TASKS.md](DESKTOP-TASKS.md) 为准，架构以 [详细方案](docs/desktop-client-plan.md) 为准。下面为同一任务的索引，不代表客户端功能已完成；DT-01～04 已完成各自记录范围，DT-05～12 已有原型与定向验证、仍待原生窗口／实机验收；DT-13～17 格式、采集边界、核心导出、安全检查与接收端映射预览已实现；DT-18 只读比较核心、DT-19 事务导入与本机协议已实现并通过定向验证，离线迁移 UI 尚未接入。DT-20～40 尚待实施或外部环境验收。历史 CLI／Git 记录保留在后文，不能作为新客户端任务的验收。

当前桌面相关定向回归：DT-12 协议、来源映射、快照、接续与可靠性测试 70 passed；DT-13 格式测试 9 passed；DT-14 采集策略、格式和导入方向测试 14 passed；DT-15 导出、采集策略、格式和核心导入方向测试 17 passed；DT-16 检查及 DT-13～15 回归 22 passed；DT-17 映射及 DT-13～16 回归 25 passed；DT-18 冲突核心及 DT-13～17 回归 29 passed；DT-19 可恢复导入、本机协议及 DT-13～18 回归 59 passed（Windows，项目虚拟环境 Python 3.13.14；详见 `DESKTOP-TASKS.md`）。前端 TypeScript/Vite build 与 oxlint 历史检查通过。DT-06～12 操作已接入 UI 原型，但原生窗口／真实 Agent／远端交互尚未验收；DT-15～19 目前是本机核心 API，DT-18 冲突选择和 DT-20 客户端导出／导入页面尚未接入。干净账户安装未验收，当前完整工作区 pytest 未重跑。详细边界见 `docs/acceptance.md`、`docs/desktop-rpc.md` 与 `DESKTOP-TASKS.md`。

### A 核心与独立安装准备

- [x] DT-01 核对当前实现，并补验独立配置库
- [x] DT-02 将用户数据与安装分开，解除离线功能对 Git 的依赖
- [x] DT-03 整理共用应用服务，保留全部现有入口
- [x] DT-04 定义结构化请求、进度、预览和应用接口（Tauri UI／打包验收待后续任务）
- [ ] DT-05 验证客户端外壳和内置 Python 核心独立运行

### B 全部现有功能进入客户端

- [ ] DT-06 窗口、导航和真实状态总览
- [ ] DT-07 首次设置、目录识别和自定义 agent 登记
- [ ] DT-08 已有规则识别、逐项选择与迁入
- [ ] DT-09 共享规则编辑、差异处理与应用
- [ ] DT-10 退出接管和真实新会话加载核验
- [ ] DT-11 操作历史、撤销和中断恢复
- [ ] DT-12 现有记忆、快照与项目接续的客户端入口

### C 离线基础迁移

- [x] DT-13 固定包清单、内容标识与版本格式（仅格式／校验，不含导出导入）
- [x] DT-14 登记纳入范围，分离本机状态和共享内容（采集策略，不含包导出）
- [x] DT-15 一致快照与自包含目录／归档导出（仅核心；客户端入口待 DT-20）
- [x] DT-16 包完整性、恶意路径与有界只读检查（尚未写入接收端）
- [x] DT-17 目标 agent／项目目录映射与接收设备配置提案（只读核心；冲突与写入待后续任务）
- [ ] DT-18 包与本机差异、共同基线和冲突选择（核心已实现；界面／应用闭环待完成）
- [x] DT-19 备份、事务导入、内容核验和撤销（本机服务／协议；客户端页面在 DT-20）
- [ ] DT-20 客户端离线导出、打开包、预览与应用

### D 扩展可迁移内容

- [ ] DT-21 skills 内容采集、链接处理与去重
- [ ] DT-22 skills 部署、撤销与 CC Switch 所有权处理
- [ ] DT-23 非敏感 MCP 字段迁移与依赖检查
- [ ] DT-24 记忆／交接可移植包及无 Git 本地存取
- [ ] DT-25 范围选择、实际支持能力与排除报告

### E 真实跨平台与用户验收

- [ ] DT-26 Windows 安装、无开发依赖和异常恢复验收
- [ ] DT-27 macOS 实际架构构建、安装与平台差异验收
- [ ] DT-28 Windows A／B／Mac 实机迁移与 agent 加载
- [ ] DT-29 未参与开发的用户完成纯客户端流程

### F 用户服务器同步

- [ ] DT-30 明确部署条件、账号提供方和运维边界
- [ ] DT-31 数据模型、接口、幂等请求与并发版本规则
- [ ] DT-32 客户端登录、令牌安全保存和每用户授权
- [ ] DT-33 客户端包加密、新设备解锁与密钥恢复
- [ ] DT-34 私有包存储、续传、完成确认和下载
- [ ] DT-35 客户端上传、下载和本机应用流程
- [ ] DT-36 云端冲突选择、历史恢复和设备回执
- [ ] DT-37 云端故障、授权隔离和真实服务器联调验收
- [ ] DT-38 用户服务器部署与备份恢复演练

### G 发布交付

- [ ] DT-39 可重复构建、平台安装包和分发检查
- [ ] DT-40 按发布范围重写入门文档并完成验收


## 四項後續修復

- [x] start 使用接收設備 memory 基線，移除發送方父快照推斷；有不同本機內容但缺基線時停止，不能猜測。
- [x] SyncLock 使用 Windows 位元組鎖／Unix flock；永久保留 sync.guard，metadata 不再決定互斥。不要混用仍在執行的舊版同步程式。
- [x] confirmations/設備/快照.json 獨立保存已確認快照，後續 pending head 不會撤銷歷史確認。舊資料缺確認記錄時，需重新確認推送；不能從最新 head 推測歷史已上傳。
- [x] 配置內容雜湊只包含格式、共享文件和受管欄位；start 分別檢查內容與本機乾淨狀態。finish 仍要求配置可從遠端取得。

回歸測試：tests/test_four_sync_fixes.py。接收設備原有基線文件需保留，不可用發送方父快照替代。

## 2026-09-12 第二輪修復

- [x] 批次寫入前逐文件核對讀取版本，外部在批次途中修改的文件不再被後續寫入覆蓋。
- [x] 未完成或無法解析的事務阻止新套用；恢復前驗證備份內容雜湊。
- [x] 修正 doctor --recover 的巢狀取鎖，恢復函式自行管理鎖。
- [x] Windows 存活探測改用只讀程序查詢，不使用 os.kill 作為探測。
- [x] Git 提交拒絕清單外的既有暫存文件，並掃描實際暫存內容。
- [x] 交接 ID 驗證、文件身份核對，以及已登記專案不可被不同遠端靜默取代。
- [x] 缺少記憶快照或有效配置資料的交接不得標 ready。
- [x] 指定設備查找快照不得退回其他設備；拒絕設備身份不符和重複文件路徑。
- [x] 修正兩項 CLI 測試對臨時目錄深度的固定假設。

回歸測試：tests/test_review_regressions.py。隔離測試不等於三機實機驗收；外部程序仍需停止写入後再回填。雜湊核對不能提供跨程序文件鎖或斷電時跨文件原子性。

建立日期：2026-09-11。設計依據：task.md。

供下一位執行者直接接手。本文件列出上一輪審查後的逐項狀態。2026-09-12 已以本機隔離測試 39 項通過；2026-09-15 體驗改造（UX-TASKS.md）後全量隔離測試 145 項通過。三台實機、私有遠端及完整上下文接續尚未驗收。勾選只代表目前程式與測試已有證據，不代表 P3 已完成。

## 2026-09-15 體驗改造

依 `UX-TASKS.md` 的 18 項任務實作「不需要手工編輯 JSON」的跨設備配置同步。新增 `sync_core/` 下的
`status`、`config_status`、`environment`、`messages`、`config_sync`、`wizard`、`restore`、
`receipts`、`diff_view`、`onboarding` 模組，以及 `ai-config.ps1`／`ai-config.command` 啟動入口與
`schemas/config-state.schema.json`。文件重寫為 `README.md` 加 `docs/` 四篇。

同期修復的既有缺陷（詳見 `UX-TASKS.md` 的「本次修復的既有缺陷」）：Git 事實採集無限掛起、
憑據來源被降級為待映射、目標文件缺失被誤判為已應用、`setup.py` 與 pytest 鉤子重名、
多數新命令只輸出原始 JSON、`verified` 因空受管範圍永遠為假、`diff` 未持久化歸屬選擇、
啟動腳本在已有 `.venv` 時仍要求系統 Python。

**恢復路徑死循環**（本輪修復，最嚴重的一項）：手改受管規則區塊後 `sync` 報 E3001 並要求
「執行 diff 選擇處理方式」，但 `diff` 只比較工具配置鍵、完全忽略規則區塊，於是列印
「沒有需要處理的欄位差異」；使用者照做後再次 `sync` 仍然失敗。已讓 `diff` 識別 `rules_block`
漂移並單獨列出，規則區塊只提供 `share`／`restore`（`local` 會被拒絕），並新增一次性 restore
意圖讓明確選擇後才能覆蓋（仍先備份）。同時 `OwnershipError`／`ConfigSyncError` 不再被降級為
笼統的 E9001。

回歸測試：`tests/test_config_consistency.py`、`tests/test_ux_flows.py`、`tests/test_onboarding.py`、
`tests/test_launchers.py`。恢復閉環由 `test_restore_choice_overwrites_the_edited_block_after_a_backup`
逐步走完（手改 → diff → restore → sync 成功 → 再 sync 零變更 → undo 可找回）。三機實機與零基礎
使用者驗收見 `docs/acceptance.md`，仍待用戶提供設備。

## 2026-09-17 第二輪審查修復（七項）

本輪逐項修復第二輪審查列出的七個缺陷。共同形狀都是「回報了沒有真正發生的事」。

1. **高 · 同步沒有更新配置源**：`sync --fetch` 過去拉的是 `memory_repo`（記憶倉庫），另一台電腦仍可能套用舊配置。
   新增 `sync_core/config_source.py`：`fetch()` 對**配置源**做只快進下載，`publish()` 只提交並推送
   `common/`、`codex/`、`claude/`。新增 `--publish`。同步報告與輸出分成四行：下載共享配置／遠端發布／
   本機應用／狀態上報。分叉或工作區衝突時停止（E2002，退出碼 4），不強制推送。
   同時把「配置源」統一到一處：`config_repo` 有記錄時，下載、發布、模板讀取、期望投影與共享寫入
   都指向同一份 checkout（`scripts.sync._source_root`、`config_sync._share_template_root`）。
2. **高 · 「僅本機保留」無效**：`local_overrides.json` 過去沒有任何讀者。新增
   `config_sync.effective_overrides()`，把它接入實際寫入（`_config_plan`）、差異比較（`diff`，
   顯示為「來自本機覆蓋」）與應用核驗（`_expected_projections`）。覆蓋值優先於共享模板，
   後續同步不再改回共享值。
3. **高 · 啟用記憶後核驗結果不可信**：期望投影改用與寫入完全相同的規則正文
   （`scripts.sync._rules_body`，含記憶索引說明），不再用不含該段落的 `_body()`。成功記錄
   改為**全部核驗通過後**才寫入；`pending_sync` 不再被當成核驗通過（`_targets_verified` 收緊為
   僅 `applied`，或受管欄位為空的目標）。
4. **高 · 設備回執沒有真正上傳**：`publish_receipt` / `fetch_receipts` 過去把本機路徑當成遠端，
   所以「uploaded」永遠讀不到。改為從配置源 checkout 讀取真實遠端地址；無遠端時拋
   `ReceiptUnavailable`（未配置，不是成功也不是失敗）。同步成功後接入上報，`status` 也改為從
   **配置源**讀回執（原本錯讀記憶倉庫）。所有 git 呼叫加上 `GIT_TERMINAL_PROMPT=0` 與 stdin 關閉。
5. **中 · 規則選擇「共享」直接報錯**：`_adopt_local_block_as_baseline` 未匯入 `digest` 導致
   `NameError`，且它只是刷新本機基線，假稱共享完成。改為 `_stage_local_block`：把本機區塊內容
   暫存到 `state_dir/rules-share/` 供合併進 `common/`，**不刷新基線**，衝突保護保留到共享內容
   真正保存並發布。
6. **中 · 預覽會消耗恢復決定**：`_rules_plan` 過去在規劃時就清除一次性 restore 意圖。
   改為把決定記在 `PlannedChanges.metadata["accepted_rules"]`（`build_plan` 負責彙整），
   只有成功套用並核驗通過後才由 `config_sync._consume_restore_intent` 清除。
7. **中 · 測試依賴 Windows 編碼環境**：測試子程序輸出統一以 `encoding="utf-8"` 解碼；
   `scripts/sync.py` 在輸出為管道且未設定 `PYTHONIOENCODING` 時固定以 UTF-8 寫出，
   終端（tty）行為不變。

同時修正一類潛伏缺陷：`git rev-parse <ref>` 在失敗時仍會把 ref 名寫到 stdout，因此
「分支／FETCH_HEAD 是否存在」的判斷過去一律為真。`config_source`、`receipts`、`transport`
中所有此類呼叫改用 `rev-parse --verify --quiet`。

回歸測試：`tests/test_sync_integrity.py`（18 項），全量隔離測試 163 項通過。
文檔同步：`README.md`、`docs/getting-started.md`、`docs/advanced.md`、`docs/troubleshooting.md`。

## 2026-10-01 多 agent 扩展：迁入 → 同步 → 接管

依据：已批准的方案（识别并迁入已有配置、同步配置库、让各 agent 取用配置库）。已确认的决策：第二批接入 WorkBuddy 与 TRAE；skills 首期只盘点；默认接管方式为受管副本。所有开发与测试都在隔离目录中进行，没有修改开发机上任何 agent 的真实配置。

- [x] Phase 1 适配器注册表（`sync_core/agents.py`）：规划、写入、核验、差异、撤销都改为遍历注册表实例；Codex/Claude 沿用顶层字段，其余 agent 登记在 `agents` 下；独占文件从不接管外来同名文件。提交 `522268f`。
- [x] Phase 2 `scan`：只读盘点规则入口、手写规则与配置库的重合度、人格/记忆/设置名称、受保护文件名称、Codex `AGENTS.override.md` 遮蔽，以及 skills（识别 CC Switch 链接）。提交 `15511a8`。
- [x] Phase 3 `migrate` / `detach`：按章节确定性去重；独有内容只在明确选择后处理（adopt 写入 `common/imported.md`，保留原文与来源）；凭据阻止；决定可记忆；事务可 `undo`；`detach --restore-original` 后沙箱逐字节还原。提交 `a27a02f`。
- [x] Phase 4 新 agent 接管：版本戳与 `verify-load` 挑战-应答、配置库 `agents.toml`、`declare`、setup 识别注册表 agent、E1003/E3004/E6001、`detach` 只删除 ai-config 新建的目录；10 个适配器契约用例。提交 `69262fc`。
- [ ] Phase 5 独立配置库：起步模板和 `setup --store` 已编写；DT-02 已把本机建库改为无需 Git，并把设备文件迁至用户数据目录。DT-02 阶段的 `tests/test_store.py` 5 项、全量 273 项通过；后续全量结果见 `docs/acceptance.md`。改动未提交；远端／三机验收仍待完成。
- [ ] Phase 6 文档：README、`docs/getting-started.md`、`docs/advanced.md`、`docs/troubleshooting.md`、`docs/acceptance.md` 已更新，未提交。

历史验证记录：2026-10-01 全量隔离测试 260 通过（`69262fc`，Windows 10 Pro，Python 3.13.14）；该次未包括 Phase 5/6。此后本轮用户要求开始逐项执行 DT 任务：DT-01 store 测试 5 passed；DT-02 定向 133 passed、全量 273 passed（项目虚拟环境 Python 3.13.14，Windows，当前未提交工作区）。详见 `docs/acceptance.md` 第四、五节。

待办：

- [x] DT-02 阶段运行 `tests/test_store.py` 与当时全量测试：5 项与 273 项通过。后续 DT-03 全量 278 项通过。Phase 5/6 改动未提交，待审查。
- [ ] 在干净的虚拟机或独立系统账户中逐个 agent 执行 `verify-load`：Codex、Claude Code、CodeBuddy（CLI 与 IDE）、WorkBuddy、WorkBuddy AI、TRAE、TRAE CN。WorkBuddy 不通过时把入口改为 `USER.md` 受管区块再测；TRAE 记录实际的 `user_rules` 形态。
- [ ] 核对 WorkBuddy 云同步是否会跨设备复制受管区块。
- [ ] 下一批 L1 候选（Gemini CLI、opencode、Kiro）：先核对官方文档，再在沙箱实测后加入注册表。
- [ ] skills 同步：先确定与 CC Switch 的边界（由谁接管、如何避免互相覆盖）。

## 2026-10-01 桌面客户端与两种同步方式

需求与方案见 `docs/desktop-client-plan.md`。用户确定客户端为全部操作入口；服务器上传／下载和离线全量包均为设计方向。共用包格式、先离线后云端、Tauri 与内置 Python 核心为实施建议，尚未完成实现或功能验收。

- [x] 记录需求、架构职责、迁移范围、目录映射、风险与验收标准；本项只表示方案已记录。
后续每步工作已拆为 DT-01～40，逐项索引见本文件开头，具体工作、依赖、交付物和验收见 `DESKTOP-TASKS.md`。本节保留产品方向的首次记录，不另维护一套粗粒度完成状态。

原方案任务只维护了文档。随后按用户要求逐项执行：DT-01/02 完成本机数据与独立配置库改造；DT-03 建立共用应用服务并完成现有 CLI 接入；DT-04 完成本机 JSON Lines RPC 协议及安全作业控制的定向验收。DT-05 已产出 Windows Tauri/NSIS 原型和 Python 3.14 sidecar，但安装包尚未在干净账户启动验收；DT-06 已有导航和真实只读总览原型，尚未完成窗口交互集成验收。详细边界见 DESKTOP-TASKS.md 和 docs/acceptance.md。尚未连接服务器、导入迁移包或验证真实 agent 会话。

## 执行约束（沿用）


- 保留現有未提交改動，不 reset、不清空工具目錄。
- 先在隔離目錄補回歸測試，再做最小修復；真實記憶不得作為測試輸出。
- 所有覆蓋先預覽、備份；不得以「恢復成功」代替「已整合本機新增內容」。
- 不自動推送到未確認的遠端，不把憑據或完整工具運行資料庫提交到 Git。
- 第一版同一專案依次切換設備；分叉或衝突保留雙方，停止並提供處理方式，不自動選較新內容。
- 逐項更新本文件和 task.md 的狀態，附測試名稱與實際結果；沒有證據不得勾選。

## P0：阻止內容遺失和錯誤成功狀態

### 1. start 必須先保存本機記憶，再整合交接快照

- [x] 檢查並替換 scripts/sync.py 的 start 分支及快照／合併模組。
- [x] 回填前穩定採集本機來源，保存獨立不可變快照，與共同基線、交接快照進行三方比較。
- [x] 一般 start 不使用 `restore_snapshot` 直接覆蓋來源。
- [x] 本機新增文件保留；同文件雙方修改、修改與刪除衝突時停止套用。
- [x] 基線缺失不猜測共同版本；無法由父快照確定時以衝突及人工處理返回。
- [x] 套用後同批更新本機鏡像和基線標記，下一次 memory 操作不復活舊內容。

驗收：`test_start_merges_local_and_remote_then_memory_is_stable` 覆蓋本機新增、遠端修改及連續 start → memory；`test_start_conflict_or_missing_baseline_preserves_local_and_snapshot` 覆蓋雙方修改、刪除／修改及缺基線。衝突時本機原文不變且 pre-start snapshot 可恢復；普通 start 不產生未經確認的本機內容刪除。

### 2. pending／incomplete 不能返回成功退出碼

- [x] 檢查 scripts/sync.py 的 finish、start、doctor、inventory 及傳輸命令。
- [x] 統一使用 `preview`、`ready`、`uploaded`、`pending`、`incomplete`、`conflict`、`error` 語義；預覽的 `status=preview` 不等同 ready。
- [x] 固定退出碼：0＝完成或合法預覽；2＝不具備接續條件；3＝待上傳／網路問題；4＝衝突；1＝其他錯誤。
- [x] finish 上傳失敗保留已生成快照與交接記錄，返回 pending 及非零退出碼；git-memory push 同樣返回 3。
- [x] start 不具備條件時，即使沒有 memory_snapshot 也返回非零；`test_cli_missing_handoff_is_incomplete_exit` 驗證真實子進程退出碼。
- [x] 區分「預覽執行成功」與「可以接續工作」，預覽報告展示阻塞項。

驗收：已用子進程驗證缺交接返回 2；隔離函式及 Git transport 測試驗證 pending／conflict。缺遠端、斷網仍需在真实私有远端环境补一轮 CLI 验收。

### 3. 交接完整性與身份核對

- [x] 修改 sync_core/handoff.py 的 `validate_handoff`、`save_handoff`、`start_report`。
- [x] 必要章節既要存在，也要有內容；純空白、占位符和「none」等明確回答有區分。
- [x] 保存交接 Markdown 的雜湊，start 核對 JSON 與正文相符。
- [x] 檢查快照存在、內容雜湊有效，project ID、scope、tool 與本機來源映射相符。
- [x] 檢查專案登記身份及程式碼 commit／branch／lock 文件，不只靠路徑名稱認定同一專案。
- [x] 快照、交接正文或必要產物缺失時標為 incomplete；完整正確交接的 ready 路徑已在 finish/start_report 隔離測試驗證。

驗收：`test_handoff_template_and_snapshot_identity_are_rejected` 覆蓋空白／占位模板與錯快照身份；正文修改、缺文件由 `start_report` 拒絕；完整正确交接由 `test_finish_publishes_only_after_code_and_memory_confirmation` 通過。

## P1：配置一致性與遠端傳輸

### 4. 配置版本需要可核對、可恢復

- [x] finish 記錄 ai-config commit／remote、共享規則及模板摘要，start 核對 config_version 和完整 config facts。
- [x] 清單記錄配置格式版本、受管欄位選擇及各共享文件摘要。
- [x] 共享配置與本機差異分離；平台路徑在 device.json，不納入可攜配置版本。
- [x] ai-config dirty 或未被遠端確認時標記 incomplete，不只保存一個 hash 後宣告可接續。
- [x] start 核對本機配置，差異列在 checks/errors，不偷偷替換本機設定。
- [x] 共享欄位集中在 `SHARED_CODEX_KEYS`／`SHARED_CLAUDE_KEYS`，保留提供商、MCP 和其他本機欄位。

驗收：`test_configuration_facts_mark_dirty_repository_incomplete` 覆蓋 dirty 配置、`test_finish...` 覆蓋 clean confirmed 配置及 start mismatch；字段保留由 `test_config_preserves_provider_and_mcp` 覆蓋。不同平台真實配置仍需 P3。

### 5. 明確第一版 Git 分叉處理範圍

- [x] 核對並修正 sync_core/transport.py 的 `reconcile_remote`、`push_confirmed`。
- [x] fetch 遠端物件後才判斷祖先關係。
- [x] 正常遠端前進可快進；真正分叉保留本機提交，返回 pending，不 force push。
- [x] 推送確認使用「遠端包含本次提交」，不只要求遠端 tip 等於本次提交。
- [x] 第一版不自動解決真正分叉；提供保留本機提交、人工合併、重新驗證再發布的說明。
- [x] task.md 第 6 節已標明自動整合屬後續功能。
- [x] 待發布文件先經允許清單、UTF-8 和敏感資訊掃描，並掃描可見 Git 歷史。

驗收：`test_transport_fetches_remote_before_fast_forward_and_accepts_remote_ahead` 和 `test_transport_preserves_local_commit_on_true_divergence` 覆蓋兩 clone＋bare remote 的快進與分叉；推送期間遠端競爭、斷網與重試仍需實際遠端補測。

## P2：來源覆蓋與文件交接

### 6. 核對所有實際記憶來源及工具讀取方式

- [x] inventory 列出已知預設根目錄、候選 agent／subagent 根及顯式 additional_sources；不把有命令等同於全覆蓋。
- [x] 每個來源標記正常、空、待映射、失聯、未支援或排除，附原因與可選工具版本。
- [ ] Claude 新會話驗證整合索引和主題文件可讀；需真實登入會話，不以模型自述代替證據。
- [x] Codex 明確保持「快照／參考索引」能力，沒有原生導入證據，不宣稱原生記憶恢復。
- [x] 新專案、新來源可由 pending_mapping／additional_sources 顯示並要求映射。

驗收：來源盤點的隔離測試已通過；另一設備新會話讀取指定事實仍是 P3 實機驗收。

### 7. 修正 task.md 的進度與命令說明

- [x] 開頭改為逐項實施狀態，避免概括宣稱 P0–P2 全完成。
- [x] 第 2 節標記歷史問題與目前修復結果。
- [x] 第 7.3 節列出實際命令、預覽／套用參數及限制。
- [x] 第 9 節依隔離驗收證據勾選，未驗證項目保留未完成。
- [x] 補能力表：已實作、隔離驗證、實機驗證、未支援。
- [x] README、配置範例與交接模板已同步。
- [x] 增加 `quick` 快速盤點／套用入口；預設只讀，`--apply` 才建立本機配置並套用公共規則，不啟用記憶同步。

驗收：文件中的完成狀態與測試及實際程式相符；接手者不需查聊天歷史才能知道下一步。

## P3：需要使用者提供的資訊與三機驗收

### 使用者待提供

- [ ] ai-config 遠端地址。
- [ ] ai-memory 私有遠端地址，確認可見性與三台設備的存取權限。
- [ ] 獨立加密備份目的地，例如外接硬碟、NAS 或具有歷史版本的儲存服務。
- [ ] 三台設備的盤點結果：工具版本、來源目錄和專案映射；可在接入時生成，不要求事先手工整理。

不需要再讓使用者決定內部函式、雜湊或事務格式。缺少上述資訊仍可完成隔離修復，不得因而停止 P0–P2。

### 三機驗收

- [ ] Windows A → Windows B → Mac → Windows A 完成一次真實任務交接。
- [ ] 每次確認程式碼 commit、配置版本、記憶快照、交接內容、下一步一致。
- [ ] 測試中文名稱、大小寫／Unicode 碰撞、換行及 Windows 路徑限制。
- [ ] 測試離線修改後重連，衝突必須可見且原文可恢復。
- [ ] 從獨立備份恢復至空目錄，校驗全部雜湊。
- [ ] 記錄已排除／未支援的來源，不能宣稱「全部同步」而省略例外。

完成三機驗收前，不啟用背景自動回填，也不宣告零遺失或完整原生會話恢復。

## 下一位執行者的交付要求

1. 先執行現有測試，記錄基線；依 P0 → P1 → P2 → P3 推進。
2. 每項提供修改文件、回歸測試、測試結果及剩餘限制。
3. 執行敏感資訊檢查；若需要提交，遵守倉庫的提交前檢查要求。
4. 最後更新 task.md、TODO.md 和 README，提供真正可用的三機接入步驟。
5. 如仍缺遠端或實機權限，清楚列出外部待辦，不把未完成階段標為完成。

## 2026-10-01 桌面无外部条件推进

已按 DT 顺序补本地扩展、云端实现和发布/部署文件；逐项范围以 DESKTOP-TASKS.md 与 docs/desktop-local-implementation.md 为准。用户要求实现阶段不自测，最后仅挑选核心功能集中测试；最终核心选择 20 passed／1 skipped，上传字节一致性补测 1 passed，不执行全量 pytest。Windows 版权文本归档 322 项，缺失 0。实机、真实服务器、签名、跨平台／服务端许可证审核和正式发布继续待验收，不因代码或文件存在勾选完成。上文“下一位执行者先执行基线”的历史要求不用于覆盖本轮用户明确的测试时机。
