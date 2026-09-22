# Demo 第一輪驗收（2026-09-21）

- 工作區：D:/Hackthon/kinsun.ai；基準 main / 0cf52920a366b8861fe0344d95738dba109102c1。
- 範圍：當前環境 preflight、真實表單／BFF／Core／Supabase／Gemini 文字流程，以及有界 rollback SQL 回歸。
- 結論：管理員邀請與平板文字陪伴、本人文字記憶生命週期可在本機展示；完整照護到家屬報表旅程與語音尚未驗收。
- 本次沒有修改產品碼、既有設定或 schema，沒有發送 Email／LINE，也沒有部署。

## 1. 環境與 CI

| 項目 | 本次結果 |
| --- | --- |
| PR #58 CI | [35314028964](https://github.com/71bk/kinsun.ai-product/actions/runs/35314028964)：10 jobs 全部 success |
| 當前 main CI | [35314553899](https://github.com/71bk/kinsun.ai-product/actions/runs/35314553899)：10 jobs 全部 success，head SHA 與本機相同 |
| 開發 DB revision | 唯讀查詢 public.alembic_version = c7e9f1a3b546；未執行 migration |
| Core Settings | 驗證成功；development、真實 App Session、fake auth 關閉 |
| 前端建置 | npm run build --workspace @elderly-care/frontend 通過，含 TypeScript |
| 服務 | 本次啟動 Frontend 3000、Core 8000、Agent 8001，health / ready 都是 200；Core database=connected |
| 開發設定 | native auth、staff invitations、assisted sessions、evidence-aware / personal memory 已啟用；BFF/Core handoff secret 比對相等（不輸出值） |
| 語音設定 | Voice Ticket、ASR Gate、speech synthesis capability 關閉；根設定缺少 Voice Ticket / ASR 簽章金鑰；Speech 8002 未啟動 |
| 獨立測試 DB | 未設定 TEST_DATABASE_URL；未執行一般 integration conftest、schema rebuild 或 downgrade |

背景服務使用既有 .qa/start_law_repair_stack.ps1，啟動 PID 為 frontend=21312、core=24164、agent=31700。服務暫留供 Owner 本機操作；PID 只屬本次工作站快照，停止前先核對程序身分，不按 image name 終止所有 Node/Python。

啟動器仍回報 python-dotenv 的第 3 行解析警告。設定驗證與本次流程皆成功，未檢視或輸出該行秘密內容，也未自動改寫 .env；此項保留為環境整理待辦。

## 2. 真實瀏覽器驗收

使用 production build、隔離 Chrome context、真實表單登入與同源 BFF，沒有攔截或 mock backend 回應。管理員使用既有 synthetic demo 身分；新照服員與平板長者是本次新建合成資料，沒有恢復舊 retired campaign。

| 流程 | 本次證據 |
| --- | --- |
| 管理員登入與導向 | 工作人員登入表單成功導向 /admin |
| 邀請／啟用 | 由 UI 發出日照照服員邀請 201；/join 讀取 fragment 後清除；設定密碼與啟用 200 |
| 新照服員登入 | 真實表單登入到 /staff，Core 確認 DAYCARE_CARE_WORKER 及單位歸屬 |
| 無帳號長者／交付 | /staff/elders/new 建立 201、發配對碼 201、平板啟用 200 |
| 平板說明與陪伴 | 合成長者確認使用說明後送出文字；真實 Agent 回覆 SUCCESS |
| 平板停止 | 二次確認停止後回到使用說明；選擇現在不要使用後回到 /elder/pair |
| 權限反例 | 新照服員讀 admin invitations = 404；已使用配對碼重播 = 401 |
| 本人記憶同意 | 既有、仍有效的 personal-memory-20260917 合成帳號由 UI 開啟新版長期記憶用途 |
| 保存／回想 | 輸入每天早餐喝豆漿，收到 1 筆 Core receipt；新 session 回想豆漿 |
| 修改 | UI 改為牛奶；新 session 回答牛奶、不引用豆漿 |
| 刪除 | UI 刪除後，新 session 明示無紀錄、不引用牛奶或豆漿 |
| Receipt 撤銷 | 保存散步偏好後撤銷；新 session 不再回想散步 |
| 同意撤回 | 再保存豆漿後停止長期記憶；新 session 不讀取豆漿，新音樂偏好也不產生 receipt |

記憶旅程共 9 個文字回合全部 HTTP 200 / SUCCESS，使用不同 session。這是一輪含多種生命週期案例的驗收，**不是三次完整主 Demo 重演**。

驗收腳本中曾遇表單 label 精確比對、BFF /api/v1 路徑、配對頁需明確按啟用，以及 fetch Response.status 屬性使用錯誤；皆屬 harness 假設錯誤，修正後以上結果已重新核對，不列產品故障。記憶清理 DELETE 已在 harness 回傳格式錯誤前完成，另以 DB 讀回確認 DELETED。

## 3. 畫面範圍

本人文字回覆狀態在 375、390、430、1440 CSS px 的 clientWidth / scrollWidth 各自相等；另檢查 reduced-motion。截圖已逐張開啟檢視，回覆文字及輸入區沒有水平裁切。截圖是回覆區的捲動位置，不代表整頁所有狀態、所有角色或真機手感驗收。

本機忽略目錄的證據：

- .qa/local/demo-0921-memory-{375,390,430,1440}.png
- .qa/local/demo-0921-memory-reduced.png
- .qa/local/demo-acceptance-20260921.json
- .qa/local/demo-preflight-20260921.json

這些檔案只存在當前工作站，不承諾 clone 後可用；私有 bootstrap 不納入交付或版本控制。

## 4. PostgreSQL rollback 回歸

直接載入已檢查的測試函式，未載入 integration conftest。每個案例自行建立新的 synthetic UUID，完成後在 finally rollback，沒有 schema 操作或 commit。

- test_personal_lifecycle_real_sql：TEXT、ALLOWED、CONFIRMED 三項通過。
- test_current_share_scope_controls_list_and_detail：一項通過；REPORT_ALL 縮為 REPORT_WEEKLY 後，DAILY 單筆 404、列表排除；恢復 DAILY 可讀，跨 actor / tenant 拒絕。

語音案例是合成 ASR evidence 的資料庫生命週期驗證，不代表真實麥克風辨識、Speech Gateway、聲音播放或完整語音 E2E。

執行：services/core-api/.venv/Scripts/python.exe .qa/local/demo_acceptance_ops_20260921.py rollback-checks。
結果：.qa/local/demo-0921-sql-evidence.json，四項全部通過、all_writes_rolled_back=true。

## 5. 退場與保留

- 本次新照服員標示 INACTIVE，2 筆會員資格及 1 筆長者關係到期，登入 credential / identity / session 撤銷。
- 平板 session 已結束，配對碼已消耗；沒有留下本次可用的照服員或平板憑證。
- 新照服員既有 cookie 再讀 /me 得到 401，確認撤權生效。
- 本次記憶測試資料已刪除，長期記憶同意維持停止；保留該既有 synthetic 帳號原有的基本陪伴用途與原到期日，不延長會員資格。
- 最後持有的管理員、照服員與記憶帳號 browser context 已執行登出，該驗收 browser 已關閉。新照服員 bootstrap 的密碼／邀請／配對 token 已移除。
- 合成長者、已接受邀請及業務稽核保留；沒有刪除既有帳號、清空表或重設 development DB。
- 原先 5 個未追蹤提案檔保留不動。

退場結果：.qa/local/demo-0921-retirement.json。

## 6. 尚未閉合的主 Demo

1. **語音環境未就緒。** 需補齊既有 Speech provider／Core service identity／Voice Ticket／ASR／TTS 配置，再以已知合成錄音及實機操作驗收。不要直接開 flags 或以合成 ASR 測試冒充現場語音。
2. **無帳號平板不能串成照護事件與記憶故事。** 這是既定授權邊界：只有基本陪伴用途，不能用照服員登錄或平板 acknowledgement 代替本人的記憶／事件同意。展示必須分成平板陪伴與本人帳號兩條路徑。
3. **家屬報表缺少前端建立／發布操作。** 已確認 Core 有草稿／publish／withdraw API，前端目前只有家屬列表／詳情讀取；照護頁提供摘要產生／覆核，未找到報表建立或發布的 UI caller。完整純 UI 照護→摘要→家屬報表劇本不能宣稱通過。
4. **事件擷取用途不是目前同意頁的選項。** 同意頁只顯示基本陪伴、長期記憶、家屬分享。新的本人帳號若要從空白狀態演示事件→覆核，還需要明確的 CARE_EVENT_EXTRACTION 啟用流程，或事先明示的合成 fixture 前置；不能把基本陪伴同意當成事件用途。
5. **完整三次重演尚未執行。** 本次沒有新建跨角色照護／家屬 campaign，也沒有重跑事件→待辦→摘要→報表的真實登入全程。既有 CI 與 rollback 測試不替代這項。

## 7. 下一個可交付切片

先補齊「照護者從已覆核摘要建立家屬報表草稿→檢查收件範圍→明確覆核發布→家屬讀取」的操作流程，再建立新的短效 synthetic 跨角色 campaign。實作前核對現有 report contracts / authorization / safety_review_passed 的語意及可用收件關係 API；不要自行跳過人工覆核，也不要自動發送通知。

事件擷取用途的本人同意入口需同時納入劇本規劃。以上完成後才能訂為一條從新帳號開始的完整 UI Demo，並執行三次重演。

## 2026-09-22 後續

第 6 節的事件同意 UI 缺口已在本機功能分支補齊，實作與驗證見 [本人照護事件同意入口](care-event-consent-20260922.md)。本報告保留 9 月 21 日的歷史結果；報表建立／發布 UI、語音與完整三次重演仍未完成。

## 2026-09-22 日報操作切片完成

照護端日報草稿、人工覆核發布及撤回已在本機實作，詳見 [照護端家屬日報工作流](staff-family-report-workflow-20260922.md)。已通過定向測試、真實 SQL rollback 與 fixture 視覺驗證；以上歷史結果保留，完整真實登入跨角色旅程與三次重演仍待執行。

## 2026-09-22 三輪真實文字主流程驗收

三位新合成長者已完成真實登入的事件→摘要→日報發布→家屬讀取→撤回，各階段 UI 與 API 結果通過。發現並修正家屬有內容報表遺漏資料缺口提示。帳號／分享關係為明示 fixture 前置，並非邀請碼 onboarding；語音未驗。完整範圍、修正與退場證據見 [跨角色文字日報三輪驗收](cross-role-demo-acceptance-20260922.md)。
