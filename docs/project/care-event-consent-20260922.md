# 本人照護事件同意入口（2026-09-22）

基準：main 0cf52920a366b8861fe0344d95738dba109102c1；工作分支 feat/elder-care-event-consent-20260922。此切片補齊第一輪 Demo 驗收的事件擷取同意入口，尚未完成整條照護到家屬報表旅程。

## 行為與邊界

- 本人登入的 /elder/consent 新增「照護事件整理」，摘要同步顯示第四項用途；沿用既有 CSS tokens 與確認視窗。
- 開啟只提交 CARE_EVENT_EXTRACTION、明確 actor_confirmation 與當前 policy_version，share_scopes 為空；不連帶授予 BASIC_VOICE、LONG_TERM_MEMORY、TRANSCRIPT_STORAGE 或 FAMILY_SHARING。
- 文字明示候選待人工覆核，不是診斷或正式紀錄。撤回只操作該 consent，request_deletion=false；刪除既有資料是另一項流程。
- 仍由同源 BFF / Core 判斷本人身分、當前同意與授權。無帳號平板的 BASIC_VOICE acknowledgement 不受此改動影響，也不能取得事件用途。
- zh-Hant/en 字串均已登錄；長者端維持既有中文介面。沒有修改後端產品邏輯、API schema、migration 或現有環境檔。

## 驗證證據

| 層級 | 結果 |
| --- | --- |
| 前端定向測試 | 4 files / 45 tests：新面板 7、既有 API 8、ElderSurface 18、語系 12 |
| 後端單元測試 | test_companion_service.py 15 tests；新增只有 extraction consent 失效的反例，保留 actor permission / 其他用途，Agent 不收到擷取要求，主動回傳候選也不寫入 |
| 靜態檢查 | 修改的前端檔案 ESLint、後端測試 Ruff、git diff --check 通過 |
| 正式建置 | npm run build --workspace @elderly-care/frontend 通過，包含 TypeScript |
| 真實 UI → BFF → Core → 開發 DB | 既有短效 personal-memory-20260917 合成帳號：取消不新增；開啟 201、重新整理仍開啟；撤回 200、重新整理維持關閉；其他 consent ID/status/version 完全相同 |
| 畫面 | 375×812、390×844、430×932、768×1024、1024×768、1440×900 的同意摘要及新面板；每種 clientWidth = scrollWidth，面板截圖已目視檢查 |
| 互動變體 | 390px 開啟／撤回確認視窗與已開啟 reduced-motion 面板；確認內容、按鈕與狀態可讀 |

真實 UI 驗收使用 production build、隔離 Chrome context，沒有攔截後端。獨立服務使用 3104，僅該程序設定 FRONTEND_ORIGIN=http://localhost:3104；初次沿用 3000 origin 被 CSRF 拒絕屬 QA 設定問題，正確設定後重驗通過，未放寬來源檢查。

驗收結束已透過 BFF 登出（200）並關閉隔離 browser context。正式版驗證服務保留於 http://localhost:3104/elder/consent 供本機檢查，啟動 PID 29840；此 PID 僅代表本次工作站快照，停止前需重新核對。

合成帳號的此次新授權已撤回；保留撤回稽核、既有 BASIC_VOICE、原到期日與其他設定，未延長身分有效期。此次沒有產生照護事件候選或發送外部通知。撤回後停止擷取的證據為上述後端單元測試，不宣稱本次執行了真實 Gemini 事件擷取 E2E。

本機忽略目錄證據（僅此工作站可用）：

- .qa/local/care-consent-20260922-evidence.json
- .qa/local/care-consent-20260922-panel-{375,390,430,768,1024,1440}.png
- .qa/local/care-consent-20260922-summary-{375,390,430,768,1024,1440}.png
- .qa/local/care-consent-20260922-{grant-dialog,revoke-dialog,active-reduced}.png

未驗：真機手感、200% 字級、英文長者畫面、Speech Gateway / ASR / TTS、完整跨角色事件→摘要→家屬報表三次重演；沒有可銷毀的 TEST_DATABASE_URL，未執行 integration conftest 或 schema reset。此次未推送或部署，既有 CI 結果不代表本分支已通過遠端 CI。

## 下一個切片

補上照護端「從已覆核摘要建立家屬報表草稿 → 檢查收件範圍 → 人工確認發布」操作，再以新的短效合成跨角色 campaign 驗證家屬讀取。先核對現有 report contracts、授權及 safety_review_passed 語意；不得自動發布、通知或放寬家屬讀取限制。

## 2026-09-22 日報操作切片完成

照護端日報草稿、人工覆核發布及撤回已在本機實作，詳見 [照護端家屬日報工作流](staff-family-report-workflow-20260922.md)。已通過定向測試、真實 SQL rollback 與 fixture 視覺驗證；以上歷史結果保留，完整真實登入跨角色旅程與三次重演仍待執行。
