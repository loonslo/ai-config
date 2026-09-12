# 三機同步交接待辦

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

供下一位執行者直接接手。本文件列出上一輪審查後的逐項狀態。2026-09-12 已以本機隔離測試 39 項通過；三台實機、私有遠端及完整上下文接續尚未驗收。勾選只代表目前程式與測試已有證據，不代表 P3 已完成。

## 執行約束

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
