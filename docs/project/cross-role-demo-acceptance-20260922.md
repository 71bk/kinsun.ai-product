# 跨角色文字日報三輪驗收（2026-09-22）

基準 commit 6f3506a，分支 feat/elder-care-event-consent-20260922。使用 production frontend 3106、本版 Core 8016、既有 Agent 8001、Supabase development DB 與真實 Gemini。未攔截或 mock API，沒有略過 App Session／Core 授權。這是本機文字流程驗收，不代表語音或外部部署驗收。

## 前置與範圍

新建隔離 synthetic DEMO tenant、日照據點、三位長者、一位照服員、一位家屬，共五個帳號；會員資格與照護關係限定四小時。沒有修改或延長既有帳號。初始不授予任何 consent，不預建事件／摘要／報表。

三位長者分別以真實 Email／Password 表單登入，在 UI 各自開啟 BASIC_VOICE、CARE_EVENT_EXTRACTION、FAMILY_SHARING。家屬 DAILY 分享關係是專用 bootstrap 在確認本人已由 UI 同意後建立，並綁該筆 consent；不是家屬邀請碼兌換驗收。帳號／派案建立與九筆同意的準備先完成，再逐位執行下面的主流程。

新建 fixture 最初缺 elder:access_context:read，因此照服員總覽可見但詳情 404；只補正該 campaign 三筆 DAYCARE_ASSIGNMENT，不放寬產品 gate。瀏覽器 harness 曾遇登入目的頁、tab／表單 selector、二次確認，以及把 HTML document 誤當 API response 的判讀錯誤；調整為實際 DOM、明確確認及 /backend/core/ response 後重新核對。這些不列產品故障。

## 三輪結果

每輪使用不同合成長者，同一句文字「我今天早餐吃了粥。」；照服員及家屬帳號共用，session 隔離。每輪從本人文字回合開始，未以 SQL 注入照護內容。

| 操作 | 第 1 輪 | 第 2 輪 | 第 3 輪 |
| --- | --- | --- | --- |
| UI 文字回合→真實 Agent | 200 SUCCESS / ALLOW | 200 SUCCESS / ALLOW | 200 SUCCESS / ALLOW |
| 回傳 model_route | gemini-3.6-flash | gemini-3.6-flash | gemini-3.6-flash |
| 待覆核飲食事件→UI 人工驗證 | 200 VERIFIED | 200 VERIFIED | 200 VERIFIED |
| UI 產生摘要 | 201 NEEDS_REVIEW | 201 NEEDS_REVIEW | 201 NEEDS_REVIEW |
| UI 驗證摘要 | 200 READY | 200 READY | 200 READY |
| 選正式摘要、明確勾收件人→建立日報 | 201 NEEDS_REVIEW | 201 NEEDS_REVIEW | 201 NEEDS_REVIEW |
| 家屬讀草稿 | 404，不顯示內容 | 404，不顯示內容 | 404，不顯示內容 |
| 明確安全覆核→發布 | 200 PUBLISHED | 200 PUBLISHED | 200 PUBLISHED |
| 家屬真實讀取 | 200 PUBLISHED | 200 PUBLISHED | 200 PUBLISHED |
| 重建後資料缺口提示 | 顯示 | 顯示 | 顯示 |
| UI 撤回日報 | 200 WITHDRAWN | 200 WITHDRAWN | 200 WITHDRAWN |
| 家屬再次讀取 | 404，原內容消失 | 404，原內容消失 | 404，原內容消失 |

第一輪另驗未勾選人工安全覆核時，只顯示提示，沒有發出 publish 請求。真實登入的家屬讀 staff workspace 回 404；長者讀另一位長者的 consent 回 404。這兩個補充反例由已登入 browser context 的同源 request 執行。

SQL 獨立讀回為三筆 VERIFIED 事件、三筆 READY 摘要、三份 WITHDRAWN 報表。摘要 source_event_ids 與本輪事件相符，報表 source_ids 引用本輪摘要。事件只保留目前支援的結構化早餐陳述，摘要文字為「飲食紀錄：已有一筆人工覆核紀錄。」；沒有宣稱保留逐字稿或粥的細節，也沒有推論缺少的活動、睡眠或用藥資料。

## 發現並修正的產品問題

家屬 ReportCard 原本只有 items 為空時才呈現 Core 的 dataGapNotice。當報表有飲食紀錄、其他生活項目仍缺資料時，家屬看不到這段限制。此次在有內容的卡片下方加入相同提示，保持原文、既有狀態與 token；撤回分支仍不顯示原內容或提示。

變更：packages/frontend/src/components/family/ReportCard.tsx、ReportCard.module.css、FamilySurface.test.ts。新增中英文有內容報表的提示顯示測試，以及撤回後不洩漏提示的測試。

- 定向測試 41 passed：FamilySurface 18、family-guard 16、StaffReportPanel 7。
- 修改檔案 ESLint 通過；production build 通過，包含 TypeScript。
- 初次測試與 lint 在並行建置時逾時；分開重跑成功，以最後結果為準。
- 修正後啟動 production server，以 cache-busting navigation 重驗三份真實報表。
- 家屬詳情 zh-Hant 375×812、390×844、430×932、1440×900：clientWidth=scrollWidth，截圖逐張目視檢查，內容、狀態、提示與版本均可讀。
- en 390×844 與 zh-Hant reduced-motion 390×844 截圖已目視檢查；英文 UI 保留 Core 原始中文內容，未自動翻譯正式報表。reduced-motion 以 matchMedia 確認已啟用。
- 最終瀏覽器證據未記錄 pageerror。未測真機、200% 字級、Lighthouse、語音、週／月報或外部通知。

## 退場

三位合成長者透過 UI 撤回本次九筆同意。資料庫讀回九筆皆 REVOKED。五個 actor 設為 INACTIVE，會員資格與照護／家屬關係到期，PasswordCredential、ExternalIdentity、AppSession 撤銷；每個舊 browser session 再讀 /me 均回 401。

本次 private bootstrap 已移除密碼，browser storage-state 檔已刪除，最後驗收 browser 關閉。3106 frontend 與 8016 Core 停止，既有開發服務保留；沒有 schema reset、migration、刪表、寄送 Email／LINE、push 或部署。事件、摘要、已撤回日報與業務稽核保留。

本機忽略目錄證據僅在此工作站：

- .qa/local/cross-role-20260922-evidence.json
- .qa/local/cross-role-20260922-retirement.json
- .qa/local/cross-role-family-final-{375,390,430,1440}.png
- .qa/local/cross-role-family-final-en-390.png
- .qa/local/cross-role-family-final-reduced-390.png
- .qa/local/cross-role-tests.log

## 後續

這次已完成三輪照護到家屬的真實文字主流程。本次 UI 修正與驗收文件會隨功能 PR 提交，遠端 CI 結果以 PR checks 為準；語音環境與家屬邀請碼加入流程是另行驗收項目。
