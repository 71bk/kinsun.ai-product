# US-C01 今日摘要狀態／查看入口 — 2026-09-08

分支 `feat/dashboard-summary-status`，基於 PR #35 合併後 `origin/main`（`0d0d294`）。
狀態：本機實作與驗證完成，尚未提交／push／新 PR／CI；不是完整 US-C01 或 Wave 2 結案。

## 實作與安全邊界

- 授權長者清單新增 optional nullable `daily_summary`，只取 Elder.timezone 的當地今日
  PROFESSIONAL_DAILY metadata。沒有拿昨日摘要冒充今日，也不讀逐字稿、summary version
  content、來源事件 IDs；沒有新增 endpoint、migration、counter、CI job、自動生成或發布流程。
- 專業角色先逐筆 live `summary:read`，再檢查 `summary:review`。正式 READY／PUBLISHED
  對 reader 可見，其他既有狀態只對 reviewer 可見，與摘要 API 共用 visibility constants。
  家屬一律 null，前端另拒絕 family payload。沒有變更既有 Consent／retention 規則。
- 外層 null／缺欄位／非法 metadata＝資訊不可用；有 read scope 的 snapshot 內 summary=null
  表示當日沒有可查看摘要。隱藏草稿與不存在列回應一致，不透露私有狀態是否存在。
- 僅一次 tenant／當頁 allowed elder IDs 的 outer join，沿用 elder/date/type 唯一鍵；沒有
  前端逐長者 API fan-out／跨頁總數。scope 檢查仍是 sequential，未實測其延遲，不宣稱效能收益。
- as_of 固定日曆日，摘要 status/version 是查詢當下值，不是跨查詢歷史快照或 capability。
  invalid timezone 不 fallback 到 UTC；前端驗證日期、時區、帶時區 timestamp、UUID、狀態與版本。
- 卡片沿用 StateCard 的 workflow 圖示／形狀／文字與雙語字典。連結
  `?tab=summaries&date=YYYY-MM-DD` 選取既有摘要 tab 與日期，仍重查 workspace 和 summary API。
  非法／重複日期不作為 API filter，既有 pending-review 入口優先。可清除日期查看歷史列表。
- 日期入口沒有自動生成摘要；日期篩選期間不顯示原本「生成今日」按鈕，清除篩選後仍可沿用。
  現有生成按鈕的 Asia/Taipei 日期規則未修改，不宣稱本次完成跨時區摘要生成。
- 無 summary:read 不請求摘要；401／403／404 先卸載所有 elder surfaces 再重查，不能把
  resource 404 當永久 elder-wide denial。序號捨棄晚到回應；錯誤不顯示為空摘要。

## 驗證

- Core 重點 dashboard／summary API：34 passed；完整 unit suite **1206 passed in 52.17s**。
- Core Ruff check 全過；format check **393 files already formatted**。
- Frontend 新 snapshot／dashboard／card 重點測試 66 passed；詳情入口／權限 28 passed。
  完整 suite **477 passed／53 files**；ESLint、typecheck、production build 全過。
  Build compile 24.4s、TypeScript 24.3s；不當成部署效能量測。
- Static contracts 全過，含禁止 summary content 的 invalid example；Core live verifier 的
  88 runtime operations、ready 與 fail-closed probes 全過。它不驗證已登入 DB metadata 查詢。
  既有 `.env` 第 3 行 parse warning 未改；SQL bind parameters 維持隱藏。
- Identity integration **33 collected only**，其中新增 4 個参数案例：daycare／home-care／family、
  缺 read／review-only、正式／非正式所有狀態、隱藏草稿與空值一致、跨 elder／tenant、錯誤
  summary tenant、其他 summary type、昨日／明日排除、台北午夜與紐約春秋 DST、撤權／過期。
  本機沒有獨立 disposable TEST_DATABASE_URL，不執行 destructive fixtures，不啟動 Docker，
  不重建 Supabase development database。這些案例仍需新 PR 的 core-db CI 執行。

## 視覺 QA

依 `playwright-visual-qa` 使用 production build＋localhost synthetic API fixtures，21 張 PNG
保存於 ignored `.visual-qa/summary-status-20260908/`，每張均親自檢視並對照 DOM。

- `zh-Hant-{375,390,430,768,1024,1440}.png`、`en-{390,768}.png`：待覆核／已發布／當日
  無可查看摘要／不可用四張卡；正常寬度 scrollWidth=clientWidth，無水平溢出／文字裁切。
  requested 手機寬度實際 innerWidth 為 376／391／431，平板與桌機相符。
- `card-focus-en-390.png`：searchbox Tab 到摘要連結，solid focus ring，目標高度 48px。
- `detail-en-390.png`、`detail-zh-Hant-390.png`、`detail-en-768.png`：實際點擊卡片後摘要
  tab selected=true，API date=2026-09-09 並依 review scope 包含狀態；日期未被 locale 改動。
  英文手機 tab 自身可橫捲是既有設計意圖，不是 body overflow；焦點 skip-link 也是既有設計。
- `card-{DRAFT,STALE,WITHDRAWN}-en-390.png`：既有 workflow 形狀、精確狀態文字與日期。
- `card-text200-en-390.png`：只將第一張卡片文字放大 200%，換行未溢出；不是 OS／全頁 200%。
  Reduced-motion 用 matchMedia 確認開啟並重設；本增量沒有新動畫。
- `loading-en-390.png`、`empty-en-390.png`、`denied-en-390.png`：request held 的 Skeleton、
  無授權長者與 403 狀態，都無舊 elder cards。`summary-denied-en-390.png`：模擬摘要 404 後
  重新取得只有基本資料權限的 workspace，無摘要內容／操作；不是全 elder 權限失效證據。
  `summary-empty-en-390.png`：指定日期無摘要，保留日期／清除篩選入口。
- 初次 loading QA 用小寫 CSS class selector 造成 timeout；DOM 已有 Skeleton。改用實際
  role=status 後通過，屬 harness selector 錯誤，不是產品故障；地雷補進 AGENTS／CLAUDE。
  沒有發現須修正的畫面 bug，因此無 QA 驅動產品 CSS 變更／額外 rebuild。
- 專用 tab、API mocks 與 locale cookie 已清除，reduced-motion 已重設；本次 server PID 21176
  已停止。未動其他 Node 程序或真實長者資料。

## 尚未驗證／未涵蓋

新 PR／main CI、真實登入 Browser→DB 摘要查詢、真機、全頁字級 200%、完整鍵盤旅程與
效能／Lighthouse 尚未驗證；合成 UI 不代表真實資料全鏈路或 production deployment。
居服行程／派案狀態、完整 US-C01／US-B02、摘要自動排程／發布不是本次範圍。
原有 14 個 schema 工作樹修改與無關 QA artifacts 保留，不納入本次交付。

## PR 首輪 CI 追蹤

PR #36（`77869c5`），run `34209282481`：8 個檢查成功；Core integration
`154 passed / 4 failed`，aggregate 正確阻擋。新增 4 個案例在建立 fixture 時修改
`DailySummary.tenant_id`，觸發既有 `TenantImmutabilityError`，尚未完成後段狀態驗證。
修正為刪除 synthetic 錯租戶 row、flush 後建立正確租戶 row，保留租戶不可變更保護；
此操作只存在 disposable DB 測試中。修正後的 DB 執行結果待後續 CI，不以首輪成功項目
宣稱整體通過。上方「新 PR CI 尚未驗證」為提交前的歷史狀態。

2026-09-09 查證：修正 commit `085c664` 的 PR CI `34210026829` 全 10 項成功，
PR #36 已於 2026-09-08 合併為 `8f03402`，main CI `34211153156` 亦成功。
上方待 CI 敘述是歷史快照；不代表真實登入 Browser→DB 或 production 已驗證。
