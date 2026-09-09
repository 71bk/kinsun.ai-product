# 居服今日行程最小預覽

日期：2026-09-09。分支：`feat/home-care-schedule`，基於 `origin/main` 的 `8f03402`。
狀態：PR #37 已合併（`5e9f142`），PR CI `34303327254`／main CI `34304691991` 全過。
下方保留本機驗證與首次 CI 修正歷史；不是完整 US-C01 或 production 完成。

## 產品決策與邊界

Owner 在本次對話確認服務前的最小預覽：今日已確認派案可顯示長者姓名、時段、派案狀態；
摘要、事件與完整長者資料仍由原有服務時段內授權控制。此窄例外只適用新預覽 endpoint，
不把未開始派案加入 `/me/authorized-elders`，不修改 `ElderAccessPolicy`。

- `GET /api/v1/me/home-care-schedule`：僅 ACTIVE HOME_CARE_WORKER，本人派案與當前 tenant。
- 同次 SQL 重查 ACTIVE Actor／Tenant／Elder／CareUnit、有效同角色 membership；membership
  限定 care unit 時須匹配派案 care unit。需同一派案同時含 `assignment:read`、`elder:basic:read`。
- 僅 CONFIRMED／IN_PROGRESS 且 `service_end > now`。IN_PROGRESS 不允許未來開始。
  DRAFT／COMPLETED／NO_SHOW／CANCELLED／EXPIRED 與已過時段的 CONFIRMED 全部排除。
- 日期是每位 Elder.timezone 的「今日」，並含跨午夜仍未結束的服務。未來開始須落於今日，
  不接受 client 指定 actor／tenant／today；無效 persisted timezone 不退回 UTC。
- Metadata 僅 assignment/elder UUID、姓名、起訖、status、timezone、local_date；另有 as_of、
  opaque cursor page（最多 100、預設 20）。沒有 scope、地址、內容、summary ID 或全域 total。
- Cursor 只是 `(service_start, assignment_id)` 位置；每一頁重新套用全部 live filters。
  日期／權限／派案修改後不承諾歷史一致快照，重新整理回第一頁；UI 換頁不保留舊頁姓名。
- 查詢是 read-only，沒有 migration、狀態轉移、outbox、排班建立或通知。

## UI 與失效時效

`HomeCareSchedule` 只掛在居服 Dashboard，和目前授權長者卡片分開。預覽沒有詳情連結或
start/complete 指令；既有授權長者列表仍是詳情入口，preview 不會提前抓摘要／事件。
收到 401／403／404 時清掉整個 Dashboard，人工 retry 才重新授權，避免無限 refetch。
換頁／refresh／背景化先清舊資料；request sequence 防止 late response 復活。回到頁面重查。

Server 在下一次 request 即排除取消、到期或撤權派案。Browser 在服務結束時清除、正常可見
狀態每 30 秒重查；非即時推播，外部取消到畫面更新有輪詢／網路／瀏覽器排程延遲。
時間使用 server as_of 加 performance elapsed，請求延遲採保守估計；不使用瀏覽器時區授權。
新 preview 的輪詢不等於既有所有長者卡、派案頁已有即時撤權機制。

## 驗證證據

- Core unit 全套：`1215 passed`；新 schedule 單元測試 9 個。
- Frontend 全套：`502 passed / 55 files`；新 schedule API／UI 測試 25 個，包含分頁／背景化回歸。
- Core lint／format、Frontend ESLint／typecheck／production build 通過。
- 靜態 contract 全過；Core live verifier `89 runtime operations`、新 GET 無 credential 401 全過。
- DB integration 新增 4 個參數案例：UTC、台北午夜、紐約春／秋 DST。包含未來預覽但 profile
  404、同 scope gate、其他 actor／tenant／elder、非法狀態、過期、取消後 cursor replay、
  inactive elder／unit／tenant、membership 到期與角色拒絕。Identity 檔共 `37 tests collected`，
  未在本機 DB 執行。預覽與 profile route 同步凍結測試時鐘，避免服務時段測試隨執行時間漂移。
- 沒有獨立 disposable TEST_DATABASE_URL，不啟動 Docker、不重建 Supabase；新 DB 案例需 CI。

## 合成 Browser QA

使用 production build + localhost:3106，全部 API 由合成 fixture 攔截，無真實長者資料或 DB write。
截圖保留在 ignored `.visual-qa/home-care-schedule-20260909/`：

- zh-Hant：375／390／430／768／1024／1440；en：390／768。手機實際 innerWidth 為
  376／391／431，其餘與要求相同；各點 scrollWidth = clientWidth，兩張卡無重疊裁切。
- `focus-reduced-en-390.png`：Tab／Shift+Tab 回到 refresh，實線焦點、48px 目標；reduced-motion
  已啟用後重設。`loading`／`empty`／`denied` 三張：Skeleton、無行程、403 後無姓名。
- `daycare-no-preview-en-390.png`：日照無 preview 標題與 schedule request。
- `text200-en-390.png` 是局部巢狀百分比放大 stress check，部分時間文字會複合放大，
  不是 OS／全頁 200% 證據；沒有水平溢出。
- 初次 QA 的 callback 沒有全域 URL，改用已知本機 URL 字串；loading 的 role=status
  同時匹配 EmptyState，改限在 schedule 區域的 aria-busy。均是 harness 問題，不是產品 bug。
- 本次沒有 QA 驅動產品 CSS 修改。未做真實登入 Browser→DB、真機、完整鍵盤旅程或 Lighthouse。
- QA 專用分頁、攔截與語系 cookie 已清理；本次 Next.js server（PID 16488、port 3106）已停止。

## 後續

### PR #37 CI 修正紀錄

首次 CI `34302409354` 的 Core integration 為 `158 passed / 4 failed`；四個 schedule
參數案例都在最後的角色拒絕斷言預期 403，但既有 `AuthorizationDeniedError` 映射是 404。
前面的行程、分頁、取消與失效檢查已執行通過；aggregate 因 core-db failure 正確阻擋。
修正斷言並驗證 `RESOURCE_NOT_FOUND_OR_FORBIDDEN`，補 OpenAPI 404；不更動 runtime
權限邏輯。既有 5 個角色單元案例擴充真實 router／error handler 的 DB-free HTTP 檢查，
schedule unit `9 passed`。修正後完整 DB 結果仍以新 CI 為準。

既有 `/home-care/assignments` 的日期／清單與 command UI 保持不變，不以本次窄預覽證據宣稱
完整派案中心已收斂。上次服務摘要、自動排程／發布、完整 US-C01／US-B02 仍待後續。
原有 14 個 schema dirty files 與其他 QA artifacts 保留、不納入本次交付。
