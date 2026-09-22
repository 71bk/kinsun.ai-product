# 照護端家屬日報工作流（2026-09-22）

基準 main 0cf52920a366b8861fe0344d95738dba109102c1；工作分支 feat/elder-care-event-consent-20260922。此切片補上照護端從正式摘要建立 DAILY 草稿、人工覆核發布及撤回。實作與驗證均為本機，未推送、部署或變更資料庫 schema。

## 可操作流程

照護者在長者詳情的「家屬報表」分頁選取正式摘要，預覽來源內容並明確勾選收件家屬，再建立草稿。發布確認視窗完整呈現內容與收件人；安全覆核勾選預設為空，未勾選不能送出。已發布日報可經二次確認撤回。

- 分頁需 summary:read 與 family_report:draft:create；發布／撤回各依 exact scope 顯示，不替既有照服員增加權限。
- Core 僅接受摘要 ID、預期版本及收件關係 ID，由正式摘要建立內容；禁止客戶端注入文字、tenant 或 actor。
- 建立與發布重驗 FAMILY_SHARING、CARE_EVENT_EXTRACTION；發布重驗目前摘要版本／狀態、來源事件有效性與收件關係。來源摘要版本在不可變 report_version 初次 INSERT 時保存。
- 寫入皆有 Idempotency-Key；發布／撤回帶 expected_version。重試不另建草稿，狀態切換不接受失效版本。
- 收件關係限當前同意、有效家屬 Actor 與 DAILY／ALL scope；最多 32 名，來源項目及來源事件各最多 64 筆。
- 家屬讀取沿用 live relationship／share_scope／consent guard。草稿不可讀、撤回後不可讀，內部摘要版本 metadata 不進入家屬 DTO。
- 401／403／404 清除前端既有報表與摘要內容；中英文均有操作及錯誤提示。未直接串接通知寄送。

## 實作與追溯

| 邊界 | 檔案 |
| --- | --- |
| 照護者角色／exact scope／idempotency | services/core-api/app/api/staff_reports.py |
| 正式摘要轉日報／來源版本保存 | services/core-api/app/services/staff_report_service.py、report_service.py |
| live 收件關係／鎖定／列表 | services/core-api/app/repositories/report_repo.py |
| UI 與同源 API | packages/frontend/src/components/care/StaffReportPanel.tsx、src/lib/api/staff-reports.ts |
| 頁面入口／權限控制 | packages/frontend/src/app/staff/(app)/elders/[elderId]/page.tsx |
| 公開契約 | contracts/openapi/core-api.v1.yaml；CreateReportFromSummaryRequestV1、StaffReportWorkspaceV1、StaffReportWorkspaceEnvelopeV1 |
| 可執行測試 | StaffReportPanel.test.ts、staff-reports.test.ts、tests/unit/test_staff_reports.py、tests/integration/test_staff_report_workflow.py |
| 契約同步與匿名拒絕 | scripts/export_core_openapi.py、scripts/verify_contract_live.py |

API 與權限表見 Spec 10 §12.1a。現有 internal system-only 路由未改成公開入口。

## 驗證證據

| 驗證 | 結果 |
| --- | --- |
| 前端定向測試 | 76 passed：新面板 7、API client 3、家屬 guard 16、照護頁 access 38、語系 12 |
| 後端定向單元測試 | 41 passed：test_staff_reports.py、test_report_read_scope.py、test_summary_generation.py |
| 靜態檢查 | 修改檔案 Ruff、ESLint 與 git diff --check 通過 |
| 契約檢查 | 靜態 validator 通過；live verifier 確认 102 operations 一致，四個新路由匿名請求皆 401 且符合 ErrorEnvelopeV1 |
| Production build | 通過，含 TypeScript 檢查 |
| PostgreSQL rollback 工作流 | 通過；workspace→建立→重送→人工覆核發布→家屬讀取→撤回→拒絕讀取；全部寫入 rollback |
| SQL 反例 | 內容注入、錯誤摘要／報表版本、非正式或更新後摘要、來源事件失效、分享／擷取同意撤回、收件 scope 縮減、照服 scope 撤回、角色與跨 tenant 拒絕、未勾安全覆核、撤回後重新發布 |
| 瀏覽器操作 | production build＋合成 API fixtures；建立／確認／發布／撤回，未勾選安全覆核的送出請求數為 0 |
| RWD | zh-Hant 375／390／430／768／1024／1440；en 390／768；各 clientWidth = scrollWidth |
| 互動變體 | 中英文 390px 確認視窗、reduced-motion；無 pageerror 或未處理 fixture API |

SQL 測試使用新合成 tenant／actor／assignment／consent／relationship／event／summary，注入 ActorContext 與 transaction，實際執行 Core 授權及 SQL repositories；不是表單登入或 BFF E2E。專用 runner 直接載入單支測試，不載入 integration conftest，不執行 migration／schema reset，不 commit，也沒有發出外部通知。

瀏覽器驗證使用攔截回應，驗證版面與互動；真實 SQL 驗證另行完成，兩者不能合併宣稱完整真實 UI→BFF→Core 跨角色 E2E。截圖已目視檢查手機／平板／桌面代表尺寸與確認視窗。

本機忽略目錄證據只存在此工作站：

- .qa/local/staff-report-sql-20260922.json
- .qa/local/staff_report_rollback_20260922.py
- .qa/local/staff-report-visual-20260922.json
- .qa/local/staff-report-final-{zh-Hant,en}-{width}.png
- .qa/local/staff-report-final-draft-{zh-Hant,en}-{width}.png
- .qa/local/staff-report-final-dialog-{zh-Hant,en}.png

本次 3106 QA server 與隔離瀏覽器已關閉，保留既有開發服務。

## 未完成與下一步

目前既有 8000 程序未重啟至本切片，不代表現行 localhost 全套服務已有新 API。正式操作需啟動本版 Core／Frontend，並使用確有上述 scope 的有效照服員；不可自動擴權或延長既有合成帳號期限。

下一步是建立新的短效合成跨角色 campaign，以真實登入串起本人事件同意→事件擷取與人工覆核→正式摘要→照服員草稿／發布→家屬讀取／撤回，完成三次主 Demo 重演與退場。真實 Gemini／語音、實機手感、200% 字級、週／月報建立及外部通知不在此次通過範圍。遠端 CI 尚未執行，既有 main CI 不代表這批本機變更。

## 2026-09-22 三輪真實文字主流程驗收

三位新合成長者已完成真實登入的事件→摘要→日報發布→家屬讀取→撤回，各階段 UI 與 API 結果通過。發現並修正家屬有內容報表遺漏資料缺口提示。帳號／分享關係為明示 fixture 前置，並非邀請碼 onboarding；語音未驗。完整範圍、修正與退場證據見 [跨角色文字日報三輪驗收](cross-role-demo-acceptance-20260922.md)。
