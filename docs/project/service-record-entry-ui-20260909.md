# Service record entry UI — local acceptance

日期：2026-09-09。分支 `feat/service-record-entry-ui`，基於合併後 `origin/main` `9caf7cc`。
狀態：本機 implementation／synthetic Browser QA 完成，提交 PR 審查；遠端 CI 以 PR checks 為準。

## Bounded delivery

- 派案清單透過同一筆 assignment 的 `assignment:read` 與 `service_record:read/write`
  推導 UI capabilities；不靠 scope 數量、不借其他派案授權。僅 IN_PROGRESS 顯示入口。
- 讀取與人工提交沿用 BFF／HttpOnly session。提交僅帶 assignment version、SERVICE_NOTE、
  人工內容與 Idempotency-Key；worker、elder、tenant、日期、狀態由 Core 決定。
- 原生表單檢查空白／長度，提交前二次確認；成功後唯讀。紀錄提交、完成派案、已覆核事件
  是三件不同的事；完成派案前明確提示其後無法讀寫紀錄，沒有新增原子 complete 整合。
- 結果不明時鎖定內容，人工重試保留原 key 與 payload；422 明確拒絕則可修改並重新確認；
  409 停止寫入並提示重新讀取，不自動重送。GET 404 保持「未提交或不可讀」的模糊性。
- POST 401／403／404 清除紀錄、草稿、確認窗與整張派案卡；只容許明確重查清單。
  日期切換、頁面隱藏／重新取得焦點會卸載卡片；sequence guard 忽略過時讀取／命令回應。
- UI 時窗到期清除內容，已顯示 server record 每 30 秒重查以限制保留時間；Core 每次請求
  仍以 server clock 重新授權。這不是即時撤權推播；不把本機時間當安全授權來源。
- 中英文文案、CSS Modules／semantic tokens、48px 操作目標；草稿不寫入 browser storage。

## Executable checks

- Frontend：58 test files，**527 passed**；typecheck、ESLint、production build 通過。
- 新增 25 cases：API 5、Panel 13、派案頁 lifecycle 4、scope mapper 3。
  涵蓋 exact-key retry、422 correction、409、401/403/404、expiry、hidden late response、
  read-only、雙語、切換日期與 focus 後 late command 不恢復已卸載卡片。
- 收尾獨立 typecheck 發現新測試混用了 Playwright `exact` 選項，已移除；再次 typecheck、
  ESLint 與 5 個直接相關檔案的 45 tests 全過，`git diff --check` 通過。
- 此切片不改 Core API、migration 或 CI jobs；PR #38 的 DB／main CI 與已套用的 development
  migration 證據見 [API report](assignment-service-record-20260909.md)。

## Production-build visual QA

依 `playwright-visual-qa`：build + 隱藏的 Next start :3106，Playwright MCP mock BFF，僅合成資料。
最後 rebuild 後使用 `?qa=v5-*` 重新導航，各圖均開啟檢視並配 DOM 檢查，不是只保存截圖。

| Locale / viewport requested | Verified states |
| --- | --- |
| zh-Hant 375×812、390×844、430×932、768×1024、1440×900 | 入口、空紀錄中性提示、人工表單、長文換行與雙流程提示 |
| en 390×844、768×1024 | 同上；英文長按鈕與文案換行 |
| en 390×844 | 確認窗、成功唯讀、網路結果不明後 exact-key retry、409、403、expired、loading、empty list、無 scope |
| en 390×844 reduced-motion | media query 已生效；Cancel 初始焦點、Tab 至確認、Escape 關閉並返回 Review，零 POST |

本機小數縮放造成 requested 375／390／430 的 `innerWidth` 讀為 376／391／431；768／1440
一致。每組 `scrollWidth === clientWidth`，沒有水平溢出；不是用 CLI window-size 模擬。
可見表單操作按鈕高度 48 CSS px。沒有聲稱真機、完整螢幕閱讀器或 Lighthouse 驗收。

本機截圖（未作為 source files 提交）位於 `.qa/`：

- `service-record-final-{zh-Hant|en}-{width}.png`：上述 7 組 final rebuild 表單。
- `service-record-viewport-{zh-Hant|en}-390.png`：手機實際 viewport，無內容遮擋。
- `service-record-{confirm|saved|retry|conflict|denied|expired|loading|empty|noScope}-en-390.png`。

Browser 互動證據：正常確認 1 POST；uncertain retry 2 POST 的 key／body 完全相同，成功後 0 textarea；
409 只有 1 POST、0 textarea；403 只有 1 POST、0 article／textarea。expired／loading／無 scope／
空清單均未 POST。預期 mock 404、409、403 與網路 abort 會有 browser console network errors。

### Findings / limitations

- 初版把正常可能無紀錄的 GET 404 顯示為大幅錯誤狀態，改成中性說明；422 不再永久鎖定原文。
- 新入口原沿用 Link 樣式而帶入原生 button 背景，新增 semantic surface／font／cursor 樣式。
  以上都已 rebuild 後回歸各寬度。
- 初輪已捲動頁面的 full-page screenshot 出現離屏 Skip link；DOM 顯示未 focus、bottom=-8，
  回頂重拍與實際 viewport 均不再出現，判定截圖繪製差異，沒有修改共用 SkipLink。
- Native dialog 允許 Tab 進入瀏覽器 chrome；回到頁面會觸發 focus revalidation 並清除草稿。
  已驗證前兩個焦點／Escape，**未宣稱永久循環 focus trap**。這是目前防止離開後保留文字的
  操作限制；不為保存草稿而放寬重新授權，也不偷偷加入 localStorage。
- Synthetic mock QA 不是本功能的 real-auth Browser → Core → Supabase write E2E。
  真實授權／DB 已由 PR #38 disposable integration 證明部分邊界，但不等同 UI 全鏈路部署驗收。

## Remaining / next handoff

1. Review 本切片的英文 PR 與選擇性 CI；原有 14 個 schema dirty files 不納入提交。
2. Owner 核准後另交付 least-privilege runtime principal／連線切換與 synthetic real-auth E2E。
   目前 configured DB principal 高權限，不能宣稱 runtime SELECT／INSERT-only 已落實。
3. 完成派案原子整合、補登寬限、上次服務摘要授權仍未定案；不得以 DailySummary 代替服務紀錄，
   不自行擴權、回填、建立歷史摘要或實作修改／刪除指令。
