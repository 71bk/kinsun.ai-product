# 居服工作台真實登入驗收 — 2026-09-15

US-C01 工作台整合已完成本機 real-auth Browser → BFF → Core → Supabase 驗收。
產品起點為 PR #46／`ac9f2c9`，本次包含下述重疊派案修正。尚非 production activation。
機器可讀證據：[驗收 JSON](home-care-workbench-real-auth-20260915.json)。

## 實際流程

使用重新建置的 production frontend、本機 Core 與既有 Supabase development database
（revision `e3a5c7d9f102`）。新 campaign `workbench-real-auth-20260915` 建立兩個隔離的
synthetic HOME_CARE_WORKER、tenant-level／unit membership（上限四小時）、六筆派案、
一筆人工交班 fixture 與三筆人工待辦 fixture。沒有沿用或恢復前次帳號，也沒有 schema rebuild。

| 檢查 | 結果 |
| --- | --- |
| 兩個帳號真實表單登入 | 正確 `/me` principal；無 fake auth、cookie 注入或 API response mock |
| 開始前交班／待辦 | CONFIRMED 派案的兩種讀取均 404 |
| 非本人／跨 tenant／已完成派案 | 404，公開 code／message 與不存在資源一致 |
| 缺 history／task scope | 讀取 404，工作台不顯示入口；不借用其他派案 scopes |
| 今日行程 → 指定派案 → 開始 | 實際 POST 200，IN_PROGRESS v2；其他工作台與行程分頁同步重讀 |
| 交班與待辦 | 跨 worker 人工原文、source ID 相符；三筆 OPEN／IN_PROGRESS／POSTPONED 均可見；no-store |
| 中英文畫面 | en 1440／390／768、zh-Hant 375／390／430／768；DOM 無水平 overflow，七組圖片均檢視 |
| 紀錄提交＋完成 | 實際二次確認按鈕提交，POST 201、最小 receipt、COMPLETED v3 |
| 完成後 | 本頁清除原文／待辦／表單；另一工作台也清除；行程移除該派案，直接重讀三個 endpoint 均 404 |
| 最後撤權 | writer 原文、三筆待辦與未送出的表單先可見；撤銷後定期重查 401，三者全部移除 |

Reader 完成的是指定派案 `a233ae48-950f-5925-8f76-00cee35afcbb`；新紀錄
`34aa98c1-dee6-425a-93af-57f8a918f322` 為 reader 作者、正式 v1。
DB 核对三筆 outbox：`care.assignment.started.v1`、`care.service_record.completed.v1`、
`care.assignment.completed.v1`，aggregate 與 receipt 相符。完成服務沒有自動結案待辦。

## 實測發現與修正

第一輪真實登入後，`GET /me/authorized-elders` 回 500，今日行程無法顯示。
唯讀診斷只輸出 exception type 與 frame 位置，確認
`CareAssignmentRepository.find_valid_for_worker()` 的 `scalar_one_or_none()` 遇到同一
worker／elder 的多筆有效派案，拋出 `MultipleResultsFound`；不是登入或缺 scope 的 fixture 錯誤。

修正將 elder-level 查詢限制最多兩筆，只有唯一來源才返回授權派案；多筆時 fail closed，
Dashboard 對未授權指標顯示 unavailable，而非 500。沒有任選第一筆、聯集 scopes 或更改
指定派案的 `AssignmentAccessService`。一般 DB 故障仍向上拋出，不偽裝成缺資料。
其限制是：同長者多筆有效派案期間，未指定派案的 elder-level 操作會拒絕，仍可使用指定工作台。

已補 repository ambiguity／operational failure 單元回歸，以及 disposable DB 案例，驗證
Dashboard 200、模糊讀取 404、指定授權派案 200、指定缺 scope 派案 404。修正後重啟 Core，
同一 campaign 的完整流程成功；沒有為了通過而刪除重疊派案。

## 畫面證據的範圍

Real-auth Playwright CLI 在程序內讀 git-ignored 私密 fixture，密碼不進命令／工具輸出。
主流程 `.qa/workbench-real-auth.cjs` 產生 11 組通過檢查與 13 張截圖；真實登入讀寫證據
沒有 route interception。第一輪失敗另留 `.qa/workbench-real-flow-attempt1.json`。

`workbench-real-confirm-en-390.png` 的即時 viewport 擷取為空背景，**不採用為確認視窗的
像素證據**。帳號撤銷後，另以 MCP、相同 production build 的隔離 synthetic responses，
將 viewport 回到頂端並等待 dialog 幾何／動畫穩定，補驗確認視窗：
`.qa/workbench-confirm-visual-confirm-en-390.png`；按鈕／文案完整且無裁切。
這張只是補充視覺 QA，不冒充第二次 real-auth 提交。真實提交成功由 HTTP receipt 與 DB 證明。

長頁截圖上的 skip link 位置與既有 full-page capture 現象相同；MCP DOM 補驗非 focus 時
top 約 -56、bottom 約 -8，正常位於 viewport 外，未因此修改產品 CSS。

## 驗證與收尾

- Core unit：**1,416 passed**；完整 Ruff check、修改檔案 format 通過。
- Frontend production build／其內 TypeScript 檢查通過；本次沒有前端程式變更。
- Static contracts 與 Core live verifier：通過，93 operations。
- CI instrumentation／impact：26 tests passed；首輪 Core 環境缺 PyYAML，改用含 pyyaml 的
  uv 工具環境後通過，未更動應用依賴。
- 新 disposable DB 測試本機僅收集，完整執行交由 PR CI；不在 Supabase 做 integration rebuild。
- Campaign 全部 membership、credentials、sessions 已撤銷，私密 fixture 已移除帳密。
  正式紀錄與 outbox 保留供稽核；撤權前後 bounded digest 相同。
- 獨立新連線讀回再次確認撤銷已提交；本次 Core／frontend PID 11412／24652 已停止，
  3000／8000 無 listener。
- source note SHA-256：`c4cc756678fd2c9364be2bd53fc6c1490a330b50a251d5ab74ef66ea60f031cb`。
- task SHA-256：`3669f6fd1f053e7e928b97281081e4a47384a00c945cc47e7440861a516d4732`，自建立至撤權不變。
- records＋outbox SHA-256：`24e23dc26e31717aa6633afe548045771185d24e6fe1387f70026b1828bb76a6`，撤權前後一致。

未驗真機、現場使用者、screen reader 全流程、負載或 production；本次沒有重新執行完整
keyboard／reduced-motion 矩陣。正式部署、runtime least privilege、retention／deletion 與先前
暫緩的 development auth rotation 仍各自追蹤。本次未更改既有登入設定。
