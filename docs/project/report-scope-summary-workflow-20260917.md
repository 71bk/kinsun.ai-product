# 家屬報表讀取與摘要操作交付紀錄

- 日期：2026-09-17（Asia/Taipei）。
- 基準：`f236e04`，本機分支 `fix/report-scope-summary-workflow-20260917`。
- 狀態：本機程式、隔離測試、production build 與合成資料畫面驗證完成；進入 PR 審查，尚未部署。
- 對應：2026 中華電信準備度審查的家屬報表讀取疑點，以及 Wave 2／B02 的摘要操作增量。

## 實際行為

家屬原本可讀 DAILY 報表，若 relationship 從 `REPORT_ALL` 縮為 `REPORT_WEEKLY`，
新的清單請求會排除該報表，單筆請求回 404。讀取與發布共用報表類型規則，仍須符合
目前有效 Consent、recipient relationship、actor／elder／tenant 及既有讀取授權。
未知報表類型、空 scope 或失效 relationship 不會回退成允許。沒有資料庫結構變更。

照護者可在摘要項目按需展開來源事件，查看目前已覆核的內容、類型、時間與版本；
每次重新展開都重新查詢。來源限同長者與同 event ID，且狀態為 VERIFIED／CORRECTED。
沒有事件讀取權限時不提供來源按鈕；401／403／404 會清除工作區資料，遲到的回應不還原內容。

摘要頁可為目前篩選日期產生草稿，或在摘要卡片重新產生該日期；無日期篩選時使用台北今日。
確認視窗顯示日期與仍需人工覆核的說明，成功後重載摘要。每次確認操作建立獨立
idempotency key，同一視窗失敗重試沿用該 key，並防止重複送出；不自動覆核或發布家屬報表。
STALE 摘要顯示來源已變更提示，超過 32 筆已覆核事件時保留明確超限提示。
歷史日期成功訊息已改為「已產生待覆核摘要」，避免誤稱為今日。

## 驗證證據

| 檢查 | 結果與範圍 |
| --- | --- |
| Core 相關單元測試 | 36 passed：`test_report_read_scope.py`、`test_summary_api.py`、`test_summary_generation.py`、`test_care_event_api.py`；報表新檔含 11 項 |
| Frontend 相關測試 | 74 passed／5 files：events、summaries、staff access、i18n；含來源按需載入／重讀、撤權、歷史日期、重試 key 與重複操作 |
| Frontend TypeScript | `typecheck` 通過；最終 production build 的 TypeScript 檢查亦通過 |
| Frontend build／lint | `npm run build --workspace @elderly-care/frontend`、`npm run lint` 通過 |
| Core Ruff | 2 個產品檔及 2 個新測試檔的 lint／format check 通過 |
| Static contracts | `scripts/validate_contracts.py contracts` 全部通過；只補兩個 family GET operation descriptions，不改 schema |
| Core live contract | `scripts/verify_contract_live.py` 全部通過，93 runtime operations；此結果不等於完整登入／資料庫情境驗收 |
| 新 PostgreSQL 回歸 | `tests/integration/test_report_read_scope.py` collect-only 收集 1 項，未執行 |
| PR 前 CI 規則 | `uv run --with pyyaml python -m unittest discover -s scripts/ci -p 'test_*.py'`：26 passed |

PostgreSQL 案例使用既有 disposable `db_session`，驗證實際 relationship 縮限／恢復與
跨 actor／tenant HTTP 拒絕；身分以 dependency override 注入，repository／authorization
使用實際實作。本機未設定 `TEST_DATABASE_URL`，沒有對共用 Supabase 執行重建或種測試資料。
Core live contract 的 readiness 可做開發資料庫唯讀探測，不能替代上述整合案例。

## 瀏覽器與畫面

使用正式建置 localhost:3106，所有 backend 路由由 Playwright 合成 fixture 攔截，
沒有真實長者資料、正式登入、provider 呼叫或後端寫入。檢查中英文來源展開畫面，
手機、平板與桌面均無水平溢位，文字、完整 ID 與按鈕可讀。

| 設定 viewport width | 實測 innerWidth／scrollWidth | 語系與內容 |
| --- | --- | --- |
| 375 | 376／376 | zh-Hant、en，來源展開 |
| 390 | 391／391 | zh-Hant 來源；en 確認、422、成功、撤權、空狀態 |
| 430 | 431／431 | zh-Hant、en，來源展開 |
| 768 | 768／768 | zh-Hant、en，來源展開 |
| 1440 | 1440／1440 | zh-Hant、en，來源展開 |

窄螢幕 runtime 實測比要求寬 1px，以上保留實際數值。使用 reduced motion；鍵盤 Enter
開啟確認、初始焦點 Cancel、Escape 關閉。422 超限後手動重試使用相同 key，兩次 request
皆為 `summary_date: 2026-09-09`；fixture 成功回應後顯示 v3／NEEDS_REVIEW 與人工覆核按鈕。
此重試用於 transport／UI 驗證，不代表正式超限可靠重試解除。

截圖已逐張檢視，存在本機忽略目錄 `.qa/local/summary-workflow-*.png`，不包含在版本控制中。
錯誤 fixture 已依完整 Core ErrorEnvelopeV1 修正後重跑，明確檢查到 32 筆超限文案；
最終 console 僅有刻意觸發的 422 resource error 與 Next CSS preload warning，無 JS 例外。

## 未交付／待驗收

- 來源內容是目前已覆核事件，**不是原始逐字稿／音訊或摘要生成時的歷史版本快照**。
  現有 `evidence:<UUID>` 尚無本切片可直接使用的安全原文讀取契約，因此 B02 不標為整體完成。
- `summaries/rebuild` 原有行為只標記 STALE；本 UI 使用 `summaries/generate` 實際產生新待覆核版本。
- 新 DB 縮限回歸待隔離 PostgreSQL／CI 執行；本切片仍需真實登入的來源修正→摘要→家屬發布旅程驗收。
- 準備度審查中的 Memory 疑點、語音、AIoT、正式部署及報名行政文件不在本次範圍。

相關：[準備度審查](../competition/cht-2026/readiness-audit.md)、
[Wave 2 traceability](../../.kiro/specs/wave-2-caregiver-loop/traceability.md)、
[既有 B02 後端驗收](b02-summary-acceptance-20260916.md)。
