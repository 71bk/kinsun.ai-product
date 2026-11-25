# 真實公開問答驗收 — 2026-10-13

基準為本機 `main` 的 `efd6ab8`，保留上一輪尚未提交的兩份導覽 CSS 與 QA 文件。本次補做真實 Gemini／PostgreSQL、真實帳密 BFF 及瀏覽器操作，修正結構化回答的 token／外層長度預算。**仍未完成真人語音、完整語意品質或正式上線驗收。**

## 各輪結果

| 執行範圍 | 結果 | 解讀 |
| --- | --- | --- |
| 修正前固定 16 題 | 10 SUCCESS／5 NO_DATA／1 FAILED | 喘息題為 provider HTTP 504；兩題用藥負例由 SAFETY_GATE 阻擋 |
| 修正前表格 8 題 | 4 SUCCESS／3 NO_DATA／1 FAILED | CA07 回覆 finish_reason=MAX_TOKENS，JSON 被截斷 |
| 修正後真實 BFF 整批 | 34／35 檢查通過 | 課程角色／品質時數題回 UNAVAILABLE，Agent 記錄 CITATION_REJECTED；失敗保持原紀錄 |
| 修正後真實瀏覽器 | 家屬申請流程、照服員 CA07 兩項通過 | 實際輸入與點擊送出，無 HTTP fixture 或模型 mock，答案與引用渲染、無 pageerror／水平溢出 |
| 修正後表格 8 題整批 | 5 SUCCESS／3 NO_DATA／0 FAILED | 完整重跑同一題集；不与修正前、BFF 或其他單題合併重算 |
| Agent 回歸 | 911 passed | 原 899 案例與 12 個新增 provider 邊界案例；新增案例涵蓋三個 adapter |
| lint／format／契約／CI 規則 | 全部通過 | 靜態契約、Agent ASGI live verifier、CI instrumentation／impact 工具均通過 |

SUCCESS、引用定位與字串配對不是語意準確率。provider 504、引用拒絕與同一題後來成功是分開的觀察，不能宣稱間歇錯誤已消失。

## 實際修正

長表格回答的 JSON 包含重複的長 chunk ID 和 span ID。CA07 首輪只有 2,048 token 預算，輸出 3,614 字元便以 MAX_TOKENS 結束，留下不完整 JSON。

- `models/prompting.py` 對 server-built grounded context 提供 4,096 token 下限；一般陪伴仍使用原設定。
- Gemini、OpenAI-compatible、Bedrock adapters 把 structured envelope 套用既有 parser 的 20,000 字元上限；一般文字維持 4,000 字元。Bedrock 同時補上這個文字上限。
- 解析後的 answer_text 仍最多 4,000 字元，來源、引用 ID／span、答案形狀與安全驗證維持；沒有新增重試、替代模型或放寬引用。
- 新回歸能通過超過 4,000 字元的合法長 ID envelope，並拒絕一般文字超長、envelope 超長、答案超長與不存在的 span。

真實 provider 僅驗證 Gemini；其他兩個 adapter 的證據為 mock 回歸。4,096 是有界輸出預算，不是固定用量；實際費用、負載與效能門檻尚未驗收。

## 真實登入與瀏覽器

獨立 QA 埠為 frontend 3110、Core 8110、Agent 8111，使用 development 的 Gemini／Supabase 與既有合成 demo 帳號。確認 current release 為 `knowledge-v009-5046fa3d59c4`，713 projections／vectors 的 profile／hash 對應通過唯讀 preflight。

BFF 檢查包含兩角色的匿名拒絕、真實登入、session／actor type、跨角色拒絕、caller audience 注入、CSRF、申請／法條／時效缺口／醫療拒答／個人資料拒答，以及家屬不得取得專業表格。照服員另外驗證 CA07、CB01 與三個訓練時數題；每次結束都登出，並以舊 cookie 確認已失效。

初次 HTTPX harness 沒有套用瀏覽器對 localhost Secure cookie 的例外：登入成功但後續請求 401。沿用既有 loopback QA 的方式，明確傳送伺服器核發的 cookie，之後重新跑完整 35 項。初次紀錄保留，不歸因為產品登入失敗。

瀏覽器以兩個新 context 載入真實核發的短暫 session，實際送出公開問題。登入本身由真實帳密 HTTP 完成，沒有在瀏覽器重新輸入密碼；因此不是完整「UI 登入表單起點」E2E。查詢、BFF、Core、Agent、DB 與 Gemini 均未攔截。目標寬度 390，Windows 實際 innerWidth=391、document clientWidth=376（含捲軸差）；兩頁 scrollWidth 等於 clientWidth。使用 reduced-motion，代表截圖已目視核對。

瀏覽器 context／tabs 已關閉，兩份暫存 session 已撤銷並刪除。QA 服務由本輪啟動，收尾先因 launcher／listener PID 不同而停止清理，核對 Windows venv 啟動器與 listener 的父子關係後才終止本輪程序；三個 QA 埠已釋放。子程序結束時一個 launcher 自行退出，後續 stop 的「程序不存在」訊息不代表仍有服務存活。

## 答案內容與來源抽查

- CA07 題沒有限定唯一照顧問題；修正後回覆分開列出個人修飾、移位、走路各列的碼值與人員，不把所有 CA07 列套成一份相同名單。已核對本次選取的實體頁 163、172、174；沒有套用題集 notes 的頁 156 作固定答案 gate。
- CB01 回覆保留主要人員與不同問題面向的適用差異，不把名單說成介入優先順序。
- 三個訓練正例的五組課名／時數配對，與凍結手冊實體頁 137／141 及 [10-07 來源診斷](rag-training-diagnostics-20261007.md) 一致。簡單配對檢查僅用於診斷，不取代逐項語意審查。
- 原不受支援課名、家屬 CA07／訓練對照三題均回 NO_DATA；不把整本 A 手冊 source_id 當專業限定，既有家屬准入片段維持。
- 固定 16 題的 `high-burden-family-coverage` 回覆一般求助管道，但標記 SUFFICIENT，與題集 partial_or_no_data 預期不符。來源支持求助管道；對「尚未評估」條件的完整性仍列為待覆核，不改預期或 prompt 使分數變綠。

2026-10-13 線上抽查：本輪申請流程與 [衛福部官方申請頁](https://1966.gov.tw/LTC/cp-6533-70777-207.html) 相符；第 3 條家庭照顧者定義與第 9 條服務方式內容與 [全國法規資料庫](https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode=L0070040) 相符。只核對這些項目，未更新全庫現行性或將來源標記為人工 verified。2023 手冊的時數／碼值仍是指定歷史版本觀察，不代表 2026 的全部現行規定。

## 安全、環境與限制

每個直接檢索交易先明確設定 READ ONLY 與 timeout。沒有 migration、reset、TRUNCATE、資料匯入、release activation 或 `.env` 修改。BFF 真實登入會建立／撤銷合成帳號的正常 auth session／稽核紀錄；不能把整輪 BFF 描述成零資料庫寫入。

所有測試依序執行、BelowNormal，沒有同時跑多套 suite。首次 priority 設定因 Windows handle 型別錯誤，在 DB／provider 呼叫前停止；已修正。新增 envelope fixture 初版長度僅 3,967 字元，三項新測試的前置條件失敗；補足合成句長後完整 911 項回歸通過。既有 dotenv line 3 解析警告保留，沒有列印原始設定或修改使用者環境。

修正後 8 題仍有 23.3／34.4 秒的 NO_DATA 回應；這是一輪觀察，不是負載測試或正式 SLO。共享 development 沒有可丟棄 integration DB，未執行破壞性 fixtures。

未完成項目：provider／引用輸出可靠性的多輪量測、題意完整性人工驗收、[真人／真機語音清單](../runbooks/manual-voice-acceptance.md)、正式 hosting／region／成本決策，以及 production 安全與監控準備。全庫 needs_review／production 未核准狀態維持；本次沒有 commit／push。

## 本機證據

下面都是 ignored 本機工作材料，不隨 Git 交付；報告本身已保留結果與限制。

- `.rag-work/acceptance-20261013/fixed-16.json`、`layout-8.json`：修正前兩批。
- `.rag-work/acceptance-20261013/public-bff.json`：34／35 的整批；初次 cookie harness 另存 `public-bff-initial-cookie-harness.json`。
- `.rag-work/acceptance-20261013/after-fix/layout-8.json`：修正後完整 8 題。
- `.rag-work/acceptance-20261013/pair-checks.json`、`live-ui.json`：五組配對與兩頁真實瀏覽器。
- `.qa/local/acceptance-20261013/`：執行器、checks／logs 與兩張公開合成回答截圖；session 憑證暫存已清除。
