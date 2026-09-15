# Wave 2 後端缺口核對 — 2026-09-15

## 基準與工作隔離

本文件保留實作前的核對快照；後續 B03 程式、契約與驗證進度見
[事件類型／時間修正報告](b03-event-metadata-correction-20260915.md)。

- Worktree：`D:/Hackthon/kinsun-backend`；分支：`feat/wave2-backend`。
- 基準：fetch 後的 `origin/main`，commit `b01c2a9`，已包含 PR #47 的重疊派案修正。
- 原前端目錄 `D:/Hackthon/kinsun.ai` 保留既有分支與工作檔案。本次只在後端 worktree 新增此文件。
- 本次為程式／契約／測試原始碼核對，沒有重跑測試、啟動服務或存取 DB。
- 新 worktree 尚未配置獨立 `.venv`、`node_modules` 或 `.env`。不得把工作目錄分開視為 DB 已隔離。

## 已完成的基礎

[Wave 2 traceability](../../.kiro/specs/wave-2-caregiver-loop/traceability.md) 已記錄
C04/F02 第一切片的 DB、真實登入、Gemini → 人工 VERIFY → 採納待辦及 PR/main CI 驗收。
目前仍限 self-assignment，不能把未提供的轉派、排班或通知能力算入完成範圍。

C01 已有 dashboard 指標、今日行程、指定派案工作台、跨 worker 交班，以及提交紀錄與
完成派案的單一交易。最新 [9/15 real-auth 報告](home-care-workbench-real-auth-20260915.md)
保存開發環境驗收範圍；PR #47 已由本次 fetch 的 main 歷史確認合併。
這些紀錄不代表所有 Wave 2 AC 或正式上線已結案。

## AC 對照與確定缺口

驗收依據為 Spec 02 的 US-B02、US-B03、US-B04、US-A07；產品範圍仍由既有規格約束。

| 故事 | 現有實作 | 確定缺口／仍須驗證 |
| --- | --- | --- |
| B02 每日摘要 | 從同 tenant/elder 的 VERIFIED/CORRECTED 當前事件版本產生 deterministic draft；每項保留 source event IDs；沒有資料的分類寫入 missing_fields；已有覆核與重建 | 不能直接標成完整故事結案。來源片段回查、完整日界與大資料量行為仍需專門驗收；詳見下方限制 |
| B03 修正與覆核 | VERIFY/CORRECT/REJECT/EXCLUDE、reason、expected version；CORRECT 建立新 payload version，保存 reviewer 與時間；相關摘要標記 STALE | **Review request 沒有 corrected event_type/event_time，service 也未更新這兩欄**，因此「可編輯事件類型及時間」尚未實作 |
| B04 事件時間軸 | 同 tenant/elder 查詢；status、event_type、date_from/date_to 在 cursor 分頁前套用；預設只讀正式事件，讀非正式狀態另驗 review scope | **API/repository 沒有來源篩選參數**。未找到生活紀錄摘要匯出 endpoint；完整來源／摘要／修正歷史導覽仍需契約與角色驗收 |
| A07 七日生活回顧 | Companion 已能取得受控記憶及已覆核事件 context，B02 有單日摘要基礎 | 在現行 Core API／Agent 與 OpenAPI 中未找到完整七日回顧能力及驗收證據；一般事件 context 不等於七日有界查詢、逐日缺資料呈現與文字＋語音交付 |

### B02：現有行為與待驗證限制

[`SummaryService.generate_from_verified_events`](../../services/core-api/app/services/summary_service.py)
使用 `Asia/Taipei` 的日界並限制最多 32 筆事件；分類涵蓋飲食、活動、睡眠、用藥陳述、社交與重要事件。
[`care_event_rendering.py`](../../services/core-api/app/services/care_event_rendering.py)
只讀既有文字欄位，缺少時回覆中性「已有紀錄」，不生成診斷。

下一步需確認超過 32 筆時的完整性／截斷告知要求，以及固定台北日界是否符合支援的產品範圍。
這兩項目前是核對出的限制，不在本文件中直接變更契約或宣告所有時區都屬 bug。
原有 evidence refs 是 opaque reference，不得為補「來源片段」就公開完整逐字稿或音訊。

既有測試定位：

- [`test_summary_generation.py`](../../services/core-api/tests/unit/test_summary_generation.py)：
  已覆核來源、source IDs、缺資料分類與不推論 renderer。
- [`test_summary_api.py`](../../services/core-api/tests/unit/test_summary_api.py)：API 層覆蓋。

### B03：修正歷史不能只補兩個欄位

[`ReviewCareEventRequest`](../../services/core-api/app/schemas/care_event.py) 目前僅接受
decision、reason_code、corrected_payload、expected_version，且 `extra=forbid`。
[`CareEventService.review`](../../services/core-api/app/services/care_event_service.py)
目前只允許 CANDIDATE/NEEDS_REVIEW 進行覆核，CORRECT 版本化的是 payload。

[`CareEvent`](../../services/core-api/app/models/care_event.py) 的 event_type/event_time 在主表，
因此要支援修正這兩欄，必須一起規劃前後值稽核、版本、來源失效與同交易 outbox，
不能只 UPDATE 主表而丟失舊值，也不能自行開放已正式事件的再次編輯。
陪伴需求訊號的完整重算不在現行 caregiver-loop 切片中，不以摘要 STALE 代替整套訊號驗收。

### B04：目前的時間与來源語意

[`list_care_events`](../../services/core-api/app/api/care_events.py) 日期參數明確使用 UTC，
filter 比對 `COALESCE(event_time, created_at)`；repository 的排序與 cursor 則使用
`created_at + event_id`。完整「按事件發生時間」的產品預期需另外確認，不能直接改 cursor 語意。

[`CareEventRepository.list_for_elder`](../../services/core-api/app/repositories/care_event_repo.py)
目前沒有來源條件；[`test_care_event_api.py`](../../services/core-api/tests/unit/test_care_event_api.py)
已有日期／類型與租戶範圍測試。新增來源篩選應先固定 MANUAL／CONVERSATION_SESSION 與歷史
資料的判定，不以未知來源自動推論為 MANUAL，也不得增加跨長者來源查詢。
重新摘要不應創建 CareEvent；仍需以專項測試證明重建前後 timeline identity 與分頁不重複。

## 建議實作順序

1. B03：完成「事件類型／時間修正」設計與版本稽核，再補 additive contract／必要 migration、
   service 與 DB regression。先處理正式資料正確性，供後續摘要與回顧使用。
2. B04：補來源篩選契約與分頁前套用的查詢；歷史來源不明時 fail closed／明確分類。
   匯出另外切片，包含角色、資料最小化、範圍上限與非醫療用途標示。
3. B02：補來源回查、日界、超限資料與修正後重建驗收，據實收斂完成標記。
4. A07：先固定七日區間、時區、資料來源與授權；實作有界唯讀查詢及逐日缺資料結果，
   再串 Companion／TTS，保留「語音尚未驗收」直到真實流程通過。

以上為後端交付順序建議，不提前建立未實作的 executable endpoint 或放寬 gate。
前端 session 可繼續既有畫面工作；契約變更完成後，以獨立 commit／PR 提供明確欄位與相容性說明。

## 後續執行與驗證

- 後端命令固定以此 worktree 為 working directory；不要對原前端目錄 pull、rebase 或切分支。
- 實作前在新 worktree 的 `services/core-api` 建立獨立 uv environment；離線單元測試不需要複製真實 `.env`。
- 需要本機服務時使用獨立連接埠並確認前端使用的 Core 指向；共用 Supabase 的 migration／fixture
  寫入仍會影響另一個 session，必須依專案既有規則處理。
- DB integration 只使用 disposable TEST_DATABASE_URL 或 CI，不能重建 development Supabase。
- 本次僅新增核對文件；完成 diff whitespace 與文件連結檢查，未將歷史測試結果當作本次重跑。
