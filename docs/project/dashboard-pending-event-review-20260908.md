# US-C01 待覆核事件數與入口 — 2026-09-08

狀態：`feat/dashboard-pending-event-review`，基於 main `693850c`。
本機實作／驗證完成，尚未 commit、push、開 PR 或執行本增量 CI；不是完整 US-C01／Wave 2 結案。

## 範圍與授權

- authorized-elders 新增相容選填 nullable `pending_event_review_count`。只計當頁長者目前的
  CANDIDATE／NEEDS_REVIEW 事件，不計版本，也不含 VERIFIED／CORRECTED／REJECTED／EXCLUDED／DELETED。
- 必須是專業角色，且逐筆沿用非正式事件清單相同的 live `care_event:read` AND
  `care_event:review` gate。家屬、任一 scope 不足回 null；真正授權空清單回 0。
  不載入事件內容，不揭露其他長者或 tenant，不產生全域總數，不因資料頁上限截斷數字。
- 每頁至多 100 位長者；新增兩次逐長者 authorization 呼叫與一次 tenant/elder-bounded GROUP BY。
  沒有將共用 AsyncSession 並行使用，也未聲稱常數查詢成本；大頁延遲仍待量測。
- 前端對 null／缺欄位／不合法數字隱藏入口，家屬即使收到數字也不渲染。0 筆可開啟空清單。
  新連結為 `/staff/elders/{id}?review=pending`；query 只決定畫面篩選，不能授予權限。
- 入口沿用既有事件頁，送出 `status=CANDIDATE&status=NEEDS_REVIEW`；Core enum、endpoint、
  migration 均不變。原頁待覆核提示同步使用兩種狀態，仍明示第一頁計數的下限，不能把它當精確總數。
- 清單支援 opaque cursor 載入更多、依 ID 去重且不覆蓋較新版本；改篩選／tab／長者或重查權限後
  不採用舊頁回應。下一頁 401／403／404 會清除 workspace 並重查 live access。
  既有覆核成功流程重載清單；另以 DB regression 驗證 VERIFY 後 overview 計數 1 → 0。

## 驗證證據

- Core unit：1191 passed；dashboard focused：15 passed。Core Ruff lint 與 format check 通過（391 檔）。
- Frontend：418 passed／52 files；新增入口與既有權限 suite 共 18 passed。
  TypeScript typecheck、ESLint、production build 通過。
- Static contracts 通過（正數／null 範例、負數拒絕）；Core live contract verifier 通過。
  Live verifier 只覆蓋 readiness 與未登入拒絕路徑，不是已登入 count DB 行為的證據。
- 新增 3 個 DB 參數案例（日照／居服／家屬）：雙 scope／單 scope／無 scope、0／105、
  排除非待覆核狀態、跨長者／tenant、授權過期；既有 native proposal → VERIFY 測試新增 count 1 → 0。
  identity/workflow 合計 61 tests **只收集**；須由既有 CI 的 disposable PostgreSQL 執行。
  沒有啟動 Docker、重建 Supabase、改權限或寫入開發資料庫 fixture。
- 不新增 CI job；既有 Core／Frontend 路徑規則與 contract 未知路徑全跑涵蓋本增量。
- 修正過兩項測試設定錯誤：英文 tab 的正式文字是 `Care events`；invalid domain example
  須包在 `data` 中。後者已補入 AGENTS.md／CLAUDE.md，沒有放寬 schema 讓範例過關。

## 視覺 QA（合成路由，非真實登入 E2E）

依 `playwright-visual-qa` 使用 production build，mock Browser API 回應且只含合成資料。
親自檢視 `.visual-qa/pending-event-review-20260908/` 的 19 張本機 PNG：

- Dashboard：`dashboard-zh-Hant-{375,390,430,768,1024,1440}.png`、`dashboard-en-{390,768}.png`。
- 清單：`queue-zh-Hant-{375,390,430,1440}.png`、`queue-en-{390,768}.png`、`queue-paged-en-390.png`。
- `review-dialog-en-390.png`、`queue-loading-en-390.png`、`queue-empty-en-390.png`、`queue-denied-en-390.png`。

105／0 顯示正確，null 不顯示；點擊與 keyboard Enter 都選中 PENDING_REVIEW，載入下一頁後
出現候選事件並移除 exhausted 按鈕。覆核沿用原先「展開表單 → Submit review → 二次確認」流程；
只檢查到確認畫面並取消，未從 browser 送出正式覆核。模擬 loading 無舊事件、空結果有 EmptyState；
模擬分頁及重查 access 404 後只顯示 No access，沒有長者名稱或事件內容。

requested 375／390／430 的實際 innerWidth 分別為 376／391／431，其他要求寬度一致。
Dashboard 各尺寸與清單抽查的 scrollWidth 未超過 clientWidth，視覺未見橫向裁切；入口高度 48px，
focus outline 可見。後段清單／empty／denied 在 reduced-motion 下檢查。截圖中的 skip link 為既有
焦點／導覽呈現，非新元件；未修改其樣式。工具曾因猜錯標籤或把展開表單當 dialog 而等待超時，
改依實際 DOM 和原元件流程後完成檢查，沒有據此修改產品。

限制：105 與兩頁清單為獨立 synthetic UI fixtures，不是 105 筆真實 DB 點擊鏈路。
未量測效能、真機、200% 字級、完整鍵盤順序；本機截图不等於 CI browser E2E。

## 交付

保留原有 14 個 contract schema 修改與無關 `.qa` 檔案。僅提交這次 increment，開 PR 後
確認 core-db 與 aggregate，不能用 PR #33 的 CI 代表本次新程式已通過。
