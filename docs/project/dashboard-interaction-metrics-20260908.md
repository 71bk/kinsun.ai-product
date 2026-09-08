# US-C01 今日互動次數／最後互動 — 2026-09-08

分支 `feat/dashboard-interaction-metrics`，基於 PR #34 合併後 `3b48bea`。
狀態：本機實作／驗證完成，尚未 commit／push／新 PR／CI，不代表完整 US-C01／Wave 2 結案。

## 定義與邊界

- Persona：日照／居服專業照護者；US-C01 日照 overview thin slice，非居服行程／摘要實作。
- 一次互動＝一個 COMPLETED ConversationSession，且有同 tenant／elder／session 已完成的
  SUCCESS／BLOCKED／HUMAN_REVIEW AgentRun。安全拒絕／降級算已回應互動，技術失敗、取消、
  未完成、只有手動完成沒有 Agent 結果、未來結束時間不算；不表示已播放或聽完 TTS。
- 同 Session 多筆 AgentRun 以 EXISTS 不重複計數；HTTP 重播不建立第二個 Session 就不增加。
  不同 Session 即使文字相同仍是不同互動，不以內容猜測／去重。沒有讀取或新增逐字稿。
- 今日依 Elder.timezone 的日曆日，以 ended_at 歸日；跨午夜回合歸完成日。
  PostgreSQL timezone 處理 DST；invalid timezone 讓請求失敗，不靜默改成 UTC。
- 回傳 optional nullable `interaction_metrics`，內含 today_count、last_interaction_at、local_date、
  timezone、as_of。歷史最後互動是最大 ended_at，與今日零次不衝突；UTC 傳輸，UI 依同一時區顯示。
- null／缺欄位＝不可用；有權限且無歷史＝today_count 0、last_interaction_at null。
  API 錯誤不假裝成 0；UI 顯示日期、時區和截至時間，非即時訂閱，切 UI 語言不改統計日期。
- 只對 professional role＋live `voice_session:read` 開放，沿用既有 session metadata gate。
  家屬即使意外收到 object 前端也丟棄；沒有新增 scope／放寬既有 assignment／relationship。
  BASIC_VOICE 歷史 metadata 讀取與既有 session endpoint 相同，不改 Consent／retention 規則，
  不對受限逐字稿或模型內容提供另一條讀取路徑。
- Core 逐筆重驗當頁最多 100 elders，之後單次 tenant／allowed IDs GROUP BY。
  沒有瀏覽器逐長者請求、跨頁／tenant 總數、新 migration、counter table、notification 或 CI job。
  查詢／授權開銷未實測，不宣稱效能收益。

## 驗證紀錄

- Core focused 21 passed；全量首輪 1196 passed／1 既有 Hypothesis timing FlakyFailure：
  `test_property_daycare_three_way_any_missing_denies` 首次 544ms 超過 200ms，重現 2.93ms；
  單獨重跑 1 passed。未修改 deadline 或 policy。
- 第二次全量同樣 1196 passed／1 timing FlakyFailure，這次是 `test_property_daycare_three_way_all_present_allows`
  首次 250.22ms、重現 3.25ms。整個 `test_policy_properties.py` 隔離執行 17 passed，沒有改動
  測試設定／deadline。QA／build 結束後最後一次完整 Core suite 為 **1197 passed in 41.93s**；
  前兩次全量 timing failure 仍如上保留，不能把隔離重跑描述成前兩次全量成功。
- Frontend focused 33 passed，完整 suite 434 passed／52 files；typecheck、ESLint、production build
  通過（compile 28s、TypeScript 32.3s）。
- Core Ruff lint／format 通過（391 files）；identity integration 29 collected only，其中新增 4 個
  參數案例涵蓋 scope、family、撤權／過期、0／105、歷史、重複 run、失敗／未完成、跨範圍、
  台北跨日與紐約 23／25 小時日。未在本機執行 DB 測試，沿用 core-db disposable PostgreSQL CI。
- 修改後 static contracts 全數通過；Core live verifier 的 88 operations、readiness、未登入拒絕
  probes 全部通過。它不驗證已登入後的 DB 計數；既有 `.env` 第 3 行 parse warning 未改動。

## 視覺 QA

依 `playwright-visual-qa`，以 production build＋僅限本機的 synthetic Browser API fixtures 驗證，
沒有登入真實帳號或寫入 Supabase。親自檢視 `.visual-qa/interaction-metrics-20260908/` 的 13 張 PNG：

- `zh-{375,390,430,768,1024,1440}.png`、`en-{390,768}.png`：105／0／unavailable、
  台北跨日 00:01、明示 local_date／timezone／as_of。語言切換不改日期／次數；卡片沒有截字／重疊。
- `focus-en-390.png`：搜尋框 Tab 到 Open elder record，48px link、solid focus outline 可見；
  reduced-motion 的 matchMedia=true，完成後已復原。
- `card-text-200-en-390.png`：只將第一張卡片的字體逐項放大 200%，自然換行，未水平溢出；
  這不是全頁 OS 字型放大或真機驗證。
- `loading-en-390.png`、`empty-en-390.png`、`denied-en-390.png`：held request 只有 Skeleton，
  空清單顯示 No elders available，403 顯示拒絕＋Retry，均無長者卡片／舊統計。

Requested 375／390／430 的 actual innerWidth 分別 376／391／431，其餘如請求；
所有一般 viewport 的 DOM scrollWidth=clientWidth。QA 的錯誤 auth mock 欄位與 MCP 環境無 URL
global 造成的 harness error 已修正後重驗，不是產品缺陷；沒有因截圖而修改既有設計。
沒有驗證真機、正式登入 DB E2E、完整鍵盤流程、全頁 200% 或效能／Lighthouse；
105 是合成 UI 值，不宣稱真實 105 筆 Browser→DB。專用 QA tab／mock 已清除，server PID 18704 已停止。

保留使用者原有 14 個 schema 修改與無關 `.qa` artifacts，未納入這次範圍。
