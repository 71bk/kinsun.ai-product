# US-C01 居服工作台整合 — 2026-09-14

## 範圍與驗收

Persona：居服員；User Story：US-C01 的今日行程、上次人工紀錄與待追蹤事項，銜接 US-C02
既有授權資料入口。Owner 已確認開始本次流程整合。Domain state 沿用 CONFIRMED → IN_PROGRESS
→ COMPLETED；不新增正式資料、migration、scope、provider 或部署設定。

- 今日行程的連結只帶 assignment ID，`prefetch=false`；由 Core 重新判定能否開啟。
- 新工作頁 `/staff/assignments/[assignmentId]` 只載入那筆派案，無結果不改開另一筆。
- 開始後依本次 scope 按需展開上次人工紀錄及 Care Action OPEN／IN_PROGRESS／POSTPONED 清單。
  待辦每頁取既有 API 上限 100 筆，換頁替換內容，每次帶相同 assignment ID，沒有本機持久化。
- 填寫本次紀錄、二次確認與原子完成沿用既有服務紀錄 API；成功後清除工作區、顯示完成提示。
  開始／完成都發出不含 domain data 的 invalidation，行程重新向 Core 取得狀態；回到前景亦重驗。
- 完成服務不會自動結案 Care Action；本次待辦區只讀，處置仍走既有待辦頁流程。

## Security / Contract

`GET /home-care/assignments/{assignment_id}` 原本借用 elder 層級授權，這次改用現有
`AssignmentAccessService`：精確 tenant、worker、assignment、有效時窗、live Actor／Tenant／
Elder／Care Unit／membership、CONFIRMED 或 IN_PROGRESS 與本次 `assignment:read`。
未到服務時間的 schedule preview 可以存在，工作頁仍回一致 404。

`GET /elders/{elder_id}/care-actions?assignment_id=...` 新增 optional UUID query；提供時由同一
service 查詢前後核對 IN_PROGRESS 與本次 `assignment:read`／`care_action:read`，並核對 elder。
不能借另一派案的 scope，不能因拒絕退回舊 API 授權。省略參數的既有長者工作頁維持原規則。
兩個 GET 都回 no-store。OpenAPI 只改這兩個 operation，沿用既有 response schemas；新增
live fail-closed probes，沒有重排其他 contract。

UI 在 hidden、pagehide、focus 重驗、到期、拒絕、完成或切換派案時清除舊內容；交班與待辦
每 30 秒先清除再重驗。晚到回應不能恢復另一筆派案或失效內容。分頁同步排除自己發出的
BroadcastChannel 訊息，避免開始後重新載入並丟失表單。

## 本機驗證

| Gate | 結果 |
| --- | --- |
| Core unit | 1,408 passed，新增 20 個 exact-visit HTTP／scope／狀態／expiry／撤權測試 |
| Frontend | 594 passed（63 files），含工作台 9、待辦 11、同步與行程更新回歸 |
| Core Ruff | check 與 format --check 通過 |
| Frontend | ESLint、typecheck、production build 通過 |
| Contract | static validator、Core live verifier（93 operations）通過 |
| CI 工具 | 26 tests passed |
| Disposable DB | PR CI：20 migration／212 integration passed，包含新增 8 個隔離案例；本機未執行重建 |

Browser 使用 production build 與 route-intercepted synthetic responses，沒有新增帳號／派案、
沒有實際 Core 寫入，不能稱為這次功能的 real-auth E2E。

七組完整路徑：zh-Hant 375／390／430／768／1440；en 390／768。每組都從行程點進指定派案、
開始、查看交班及待辦、輸入紀錄、二次確認提交完成、確認內容消失、返回空行程。
另有 en 390 的 empty／error／loading／denied／noScope／keyboard／reduced-motion 七種狀態。
DOM 均未見橫向 overflow；Windows Chromium 在 mobile viewport 有 scrollbar／小數像素差，
innerWidth 約設定寬度 +1，並非內容超寬。full-page screenshot 的 skip link 位置是假象：
viewport 截圖與 DOM 量測確認非 focus 時 bottom=-8，正常在畫面外；沒有為截圖改產品 CSS。

本機證據：`.qa/workbench-browser.js`、`.qa/workbench-states.js`、
`.qa/workbench-{schedule,handover,confirm,completed}-*.png`、`.qa/workbench-state-*.png`、
`.qa/workbench-viewport-en-390.png`。已檢視中英文手機、桌面、確認與撤權畫面。

## PR / CI

[PR #46](https://github.com/71bk/kinsun.ai-product/pull/46) 的程式／測試版本 `44d87ca` 已通過
[CI 34830767622](https://github.com/71bk/kinsun.ai-product/actions/runs/34830767622) 全部 10 jobs，
涵蓋八個 worker 與 aggregate。第一輪 run `34830019424` 的 DB gate 也已通過
20 migration／212 integration；唯一失敗是新增 Vitest cleanup hook 的回傳型別，修成 block
body／void 後，本機 typecheck、對應測試與上述完整 CI 皆成功。此後只回填驗證文件。

## 尚未驗證

2026-09-15 更新：[新工作台真實登入驗收](home-care-workbench-real-auth-20260915.md) 已完成，
包含重疊派案 500 修正、跨分頁更新、DB／outbox 與撤權；以下保留原切片的驗證邊界。

本次未重跑 real-auth Browser→Core→Supabase 全鏈路；
上一切片已撤銷的 QA 帳號沒有恢復。未做 production activation、真機與現場使用者測試。
development 驗證設定輪替由 Owner 接受風險後暫緩，維持獨立待辦。
