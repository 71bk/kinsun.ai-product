# Service record submission and visit completion

日期：2026-09-11。分支 `feat/service-record-complete`，基於 `origin/main` `79c2a5a`。
狀態：本機實作、單元／契約與 synthetic Browser QA 完成；本切片提交 PR 審查，新增 DB 整合測試交由 PR 的 disposable PostgreSQL CI 執行，尚未部署。

## 交付範圍

居服員在本次服務紀錄表單勾選「提交紀錄時，同時完成本次服務」，二次確認後由單一
`POST /api/v1/home-care/assignments/{assignment_id}/service-record/complete` 處理。
選項預設不勾選，原有分開提交紀錄／完成派案的操作保留，沒有新增「必須有紀錄才能完成」規則。

- 沿用人工 SERVICE_NOTE、1–4,000 字、assignment version 與 Idempotency-Key；身分、範圍與狀態由 Core 決定。
- 同一 request transaction 包含不可變正式紀錄、派案 COMPLETED／version + 1、兩筆既有 domain outbox events，以及 idempotency receipt。任一步驟失敗應全部回滾，service 不自行 commit。
- 必須是本人有效 IN_PROGRESS 派案，且同一派案同時具備 `assignment:read`、`service_record:write`、`assignment:complete`。每次 gate 重查有效 worker、tenant、elder、care unit、同角色 membership 與服務時窗。
- 成功 201 僅回傳 record ID、assignment ID、assignment version、COMPLETED；receipt 與 outbox 不含紀錄本文。紀錄保存提交前 assignment version，receipt 保存完成後版本。
- 完成後原紀錄讀寫權限結束；重送成功 key 也先過 live gate，因此回不可探測 404。若回應遺失，前端只顯示無法確認／無權存取，不能把 404 推定為已完成。
- 前端成功即清除本文並重載派案清單；結果不明時鎖定內容、完成選項及同卡的獨立完成／關閉按鈕，重試沿用同一 key／payload。401／403／404 清除卡片；409 清除草稿並要求重查。

併發檢查另發現既有派案命令把 target state 直接轉成 scope，產生契約沒有的
`assignment:in_progress`／`assignment:completed`。已依 `AssignmentScope` 修正為
`assignment:start`／`assignment:complete`，並抽出共用 `AssignmentAccessService`，確保開始／完成
命令檢查指定派案本人與即時範圍，不借用同長者另一派案的授權。舊命令與新整合命令一致先鎖
assignment 再 claim idempotency；transition 等鎖後 refresh 版本，避免以舊 ORM snapshot 覆寫。

本切片無 migration、Supabase 業務寫入、scope grant 或 runtime principal 切換。已存在正式紀錄時
新命令回 409，仍可走原有獨立完成操作；沒有草稿、修改／刪除、補登寬限或歷史紀錄授權。

## 驗證

| 檢查 | 結果 |
| --- | --- |
| Core 全部 unit | 1,359 passed；完整 Ruff lint／format 通過 |
| Frontend | 全套 544 passed；最後 scope 修正後直接相關 3 files／41 tests 通過；typecheck、ESLint、production build 通過 |
| Contracts | static validator、Core live verifier（92 operations）、Agent live verifier 均通過；Agent schema consistency 260 passed |
| CI instrumentation | 26 passed |
| 新增 DB integration | 9 cases 已收集，尚未執行：3 rollback、3 concurrency、3 exact-scope denial |
| Browser | production build + Playwright MCP，BFF 全部 mock、僅合成資料；詳見下表 |

DB rollback cases 在真實寫入 record outbox、assignment outbox、receipt 後分別注入失敗，斷言
record／outbox／claim 全無、派案不變，再以同 key 成功。Concurrency cases 包含同 key、不同 key、
獨立 complete 競爭，要求只一個成功且無部分紀錄。另有同長者另一派案具完整 scope 仍不得借權的案例。
這些案例必須在 disposable PostgreSQL 執行，不能將單元 mock 當成交易隔離的實證。

本機沒有 5432 listener，Docker daemon 未運行；依 AGENTS 不自行啟動本機 PostgreSQL／compose，
未將 `TEST_DATABASE_URL` 指向 Supabase development。Core live verifier 的 `/ready` 只做 SELECT 1；
新的受保護 POST 檢查為無憑證 401，沒有觸發業務寫入。既有 dotenv 第 3 行 parse warning 仍存在，
不影響此次 live checks，未讀取或改寫秘密設定。

## Browser 證據

| Locale／requested viewport | 已驗證 |
| --- | --- |
| zh-Hant 375×812、390×844、430×932、768×1024、1440×900 | 勾選表單、二次確認、一次 POST 完成、清除內容／清單重載 |
| en 390×844、768×1024 | 同上，包含英文長文與按鈕換行 |
| en 390×844 | 網路失敗重試、409、403、已提交但回應遺失後重試 404、無 complete scope |
| en 390×844 reduced-motion | Cancel 初始焦點、Tab 到確認、Escape 回 Review；零 POST |

每組 DOM `scrollWidth === clientWidth`，checkbox label 高 48 CSS px，確認窗完整在 viewport 內。
Windows 小數縮放使 requested 375／390／430 的 innerWidth 為 376／391／431；768／1440 一致。
成功每組 1 POST，後續 0 textarea／article；retry 2 POST 的 key／payload 相同。409 只保留中性派案卡，
403 與 lost receipt → 404 後 0 textarea／article，皆無成功提示。無 scope 與 keyboard case 零 POST。

本機 `.qa/service-completion-browser-qa.js` 與 `service-completion-browser-states.js` 為可重跑的合成
Browser 腳本；`service-completion-{form|confirm|success}-{locale}-{width}.png` 及
`service-completion-state-*-en-390.png`、`service-completion-*-pending-en-390.png` 已開啟檢視並對照 DOM。
全頁截圖沿用既有 QA 的回頂重拍方式，避免離屏 SkipLink 的截圖繪製差異。
沒有聲稱真機、完整 screen reader、永久循環 focus trap 或 real-auth Browser → Core → DB write E2E。

## 上次服務摘要：下一切片的待定規則

目前 DailySummary 是不同資料來源，不能代替上次人工服務紀錄。以下為提案，尚未變成授權或 API：

1. 以本次有效 IN_PROGRESS 派案作為讀取入口，另設明確 history scope；不延長上一筆已完成派案的權限。
2. 先限制同 tenant、elder、care unit，取本次開始時間以前最近一筆正式完成紀錄；跨 worker 交接是否允許須明確定案，不能由現有 service_record:read 自動擴權。
3. 確認呈現的是人工原文節錄、人工覆核摘要或 AI 候選。第一版建議使用可追溯的人工交接內容，顯示服務日期與來源，避免生成新事實。
4. 定義服務前能否讀取、資料保留與撤權後畫面清除、來源不可用的中性提示，以及排序 tie-break／時區。

待上述範圍定案後，再新增 request／response contract、deterministic authorization 與跨 worker／
tenant／時窗／撤權負向測試；本次未開放任何歷史資料。
