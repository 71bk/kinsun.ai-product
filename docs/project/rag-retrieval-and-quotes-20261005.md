# V3 口語檢索與連續原文引用修正

本次接續 [第 4 批](rag-simplification-phase4-20261002.md) 的兩個剩餘問題：長者口語求助
找不到申請流程，以及專業高負荷題引用不連續的 PDF 文字。只修改本機程式與測試，
使用既有 `knowledge-v008-aae34e5095e6` 做唯讀實測；沒有資料庫寫入、重新產生 document
embedding、修改 `.env`、服務重啟或 activation。

## 原因與變更

### 候選排序

10 月 5 日的兩題基準仍為 1 NO_DATA／1 FAILED。口語申請題的完整流程是 dense 第一名，
cosine 約 0.6895；因缺少字面匹配，融合分數只有 0.6，被繼承的 0.7 門檻排除。
反而 raw trigram 只有 0.0323 的資格／額度資料，被 min-max lexical 正規化推到前面。
這是候選排序與門檻的問題，不是資料庫缺少流程，也不是角色 gate 拒絕。

V3 改用上限為 1 的 raw lexical 分數配合既有 dense 正規化與混合權重。融合分數用於排序，
不再把 legacy 0.7 當作 V3 的回答信心門檻；兩路各取最多 50 筆，再經同一套角色／用途、
官方來源、風險、現行性、release／profile／hash 檢查，最多 5 筆進入生成。
無相關候選仍不生成；有候選不等於能回答，生成仍須回報問題涵蓋範圍與資料缺口。
這會讓一些弱相關資料進入候選，因此必須驗證範圍外／缺資料的拒答；並非新的準確率保證。
V1／V2 的 SQL 與 relevance floor 不變。

### 原文定位與排版歧義

專業題的兩段失敗 quote 不是單純空白差異：診斷顯示它們由 4–5 個非連續 source blocks
拼成，來自雙欄 PDF 的左右欄交錯。只加 prompt 指引仍會失敗。

新增 request-local `quote_spans`：程式依保守 layout-normalized text 的句界／換行切出
連續片段，以 `s<start>:<end>` 標記。模型輸出 `chunk_id`＋`span_id`，parser 只能查該來源
已建立的選項，不能按模型任意 offsets 切字或接受模型自寫原文。來源全文仍保留，過長片段
不作選項，總 context budget 不變。這是生成內部協定；公開 API、引用數量與回覆狀態不變。
舊 `quote` 形狀仍接受原本的精確／保守排版比對，不提供 fuzzy 修復或失敗重試。

第一次片段版的原 16 題是 11 SUCCESS／5 NO_DATA，另 6 題改述／負例為 4 SUCCESS／2 NO_DATA。
但覆核發現模型仍用交錯文字回答，故這兩份中間結果不代表最後版本。
最終再加保守排版排除：一個來源有至少三行含非空字元間的三格以上空白／tab／全形空白，
視為疑似交錯欄位；整筆來源不送入生成、不允許引用。只剩這類來源時直接 NO_DATA。
不重排欄位、不合併不連續文字、不改原始 chunk 或 hash。正常段首縮排不觸發。
這是 heuristic，可能排除尚未正規化但原本有效的表格；也不保證偵測所有 PDF 排版問題。

片段 ID 正確只證明來源定位，不能證明語意支持、資料最新或人工已覆核。
本次仍保留 `needs_review`。實測報告只增加經 parser 通過的來源片段 ID，
不保存原始模型輸出、完整 prompt 或 secret。

## 驗證

- 最終程式的定向單元測試：194 passed，涵蓋 public policy／retriever、PostgreSQL adapter、
  grounded answer、Gemini 與實測工具。含來源／角色／hash 拒絕、最多五筆、任意／偽造 span、
  多欄排除、所有來源排除時不呼叫模型，以及舊引用格式仍拒絕拼接。
- 所有本機測試／實測單工、BelowNormal；沒有重跑完整套件或執行破壞性 DB integration。
- 真實驗證逐交易明確 READ ONLY＋timeout，preflight 驗證 658 projections／658 vectors。
- 另跑 service、既有 V1／V2 retrieval 與 in-process RAG API 回歸：107 passed。
- 最終原固定 16 題：**11 SUCCESS／5 NO_DATA／0 FAILED**；14 次 query embedding、14 次生成。
  口語題取得申請流程；專業高負荷題只引用完整流程來源 `_0003` 的兩段連續原文。
  未來補助、即時地方聯絡／名額、天氣與兩題用藥安全仍拒答；兩題用藥在 provider 呼叫前阻擋。
- 最終額外 6 題：**4 SUCCESS／2 NO_DATA／0 FAILED**；6 次 query embedding、6 次生成。
  兩題長者改述取得申請管道／1966，兩題專業改述使用完整流程來源；即時高鐵與日照名額拒答。
- 本次覆核兩個目標題、四個改述的答案及其連續來源片段，沒有把「來源 ID 存在」當作語意評分。
  原題集中家屬高負荷題的舊 expectation 是 `partial_or_no_data`，最終答案的兩支專線有來源；
  沒有修改 expectation 來提高通過數。以上狀態數不是正確率，也不把中間輪次拼成新分數。
- Agent live contract verifier（in-process ASGI，合成來源／provider）全數通過；
  修改的 10 個 Python 檔 Ruff lint／format check 與 `git diff --check` 通過。

## 工作產物與限制

- 原因診斷：`.rag-work/remaining-baseline-20261005.json`、`remaining-diagnostics-20261005.json`。
- 中間固定題集：`.rag-work/knowledge-evaluation-v008-20261005.json`。
- 最終固定題集：`.rag-work/knowledge-evaluation-v008-final-20261005.json`。
- 額外 6 題：`.rag-work/knowledge-paraphrases-20261005.json`，最終結果
  `.rag-work/knowledge-paraphrases-final-20261005.json`；與原固定 16 題分開報告。

`.rag-work` 為 ignored 的本機診斷產物。這些小型 developer smoke 不是獨立、人工標註的
品質基準。未測真人語音、瀏覽器完整 E2E、production 或服務 activation／rollback。
本次沒有 commit／push，也沒有整理或刪除使用者既有的未追蹤產物。

## 同日後續：版面盤點與實際服務驗收

上述為第一輪完成狀態；使用者接著授權盤點、整理 PR、隔離服務驗收，並以整合通過為日常切換條件。

- 全量 658 筆原始資料中，原寬空白規則會排除 77 筆。加入編號清單，以及漢字段落內短英數標籤的
  窄空白例外後，排除 70 筆：A 單位附錄 54、家庭照顧者支持手冊 16。Tab、全形寬空白與
  其他表格／雙欄仍保守排除；這不是 PDF 閱讀順序或表格正確性的完整判定。
- 依 `evaluate_public_knowledge` 的 `general_information` 准入實際計算：長者 97 筆、家屬 136 筆
  均未被版面規則排除；專業 464 筆中排除 55 筆。這些角色集合互相重疊，不可加總。
  JSONL 的舊 `retrieval_eligible` 欄位不是 V3 最終准入結果。
- 新增六項版面回歸案例；同一組 Agent 測試現為 200 passed，CI 工具測試 28 passed；
  前端 production build 通過。均單工、BelowNormal 執行。
- 隔離服務使用 localhost:3110／8110／8111，綁定 v008、V3 及 Core router v2；未修改 `.env`。
  BFF 初測長者、家屬、專業合成帳號登入成功；未登入 401、跨長者 404、CSRF 403、用藥 BLOCK。
  家屬及專業測試帳號無一般 voice-session 權限，均 404；現有 UI 沒有獨立公共知識問答入口。
  不新增 scope 或以長者 session 假裝完成另兩角色的問答 E2E。
- 兩個長者 BFF 問句初測 `RAG_EVIDENCE_FAILED`，相同問句獨立 CLI 為 2 SUCCESS，正在定位服務差異。
  未來補助在 Core 對外契約為 `SAFE_FALLBACK / RAG_EVIDENCE_INSUFFICIENT`，不是直接透傳 Agent 的 NO_DATA。
  未達整合完成條件，日常切換與 rollback 演練尚未執行；v004 保留。

本機證據：`.rag-work/layout-audit-20261005.json`、`.qa/v008-bff-result.json`、
`.rag-work/bff-diagnostics-20261005.json`。新 review worktree 從 origin/main 建立，帶入 PR #67
的三個必要前置提交；僅複製明列的 16 個修正檔案，既有 untracked 產物未加入。

## 整合完成及本機開發切換

後續加入的本機診斷只記固定分類、耗時及 token 數，不記問句、prompt、模型原始輸出或 DSN。
相同 BFF 問句複測、兩輪真實瀏覽器問答均成功；初次兩次 `RAG_EVIDENCE_FAILED` 的原因未再重現，
不能宣稱已定位或修復該偶發問題。既有 fail-closed 行為保留，未增加自動重試或放寬引用驗證。

- 最終版面例外後，完整 16 題重新執行：**11 SUCCESS／5 NO_DATA／0 FAILED**，14 次 query embedding、
  14 次生成；仍不是語意準確率。兩個目標題的答案及來源片段另行檢視，申請流程及未評估先評估的
  支持來源均保持。報告：`.rag-work/knowledge-v008-post-layout-20261005.json`。
- BFF 複測各項通過：三角色合成登入／登出、未登入、跨長者權限、CSRF、長者申請／法條、
  未來補助備援、用藥攔截；報告 `.qa/v008-bff-result.json`。初次報告另存
  `.qa/v008-bff-initial-result.json`，沒有覆蓋失敗紀錄。
- 實際瀏覽器由登入表單進入文字陪伴，送出問句並展開官方來源連結。回答檢查 375×812、390×844、
  430×932、1440×900；兩種拒答各檢查 390×844。六張 `.qa/v008-{oral|unknown|medication}-{width}.png`
  已目視覆核，DOM `scrollWidth == clientWidth`。初次圖片的浮動連結位置為捲動後 full-page 截圖假象，
  角色空白為影片未就緒的瞬態；等待 media ready 並捲回頂端後重拍正常，沒有 UI 程式修改。
  既有拒答提示仍泛稱高風險／醫療安全，對資料不足題不夠精準，列為後續文案改善。
- `8807785` 程式提交的 PR #68 Gate 1 十項 checks 全過。PR 仍為 draft，依賴未合併的 #67，
  沒有合併 main，也沒有關閉 #67。原工作區保留，審查 worktree 為 `D:/Hackthon/kinsun-rag-20261005`。
- 在使用者授權的本機 development 執行 v008 → v004 → v008。日常 3000／8000／8001 的 v008
  申請與法條問答成功；回退到原 v004／原 flags 後，登入、權限與法條問答成功。
  `.qa/v008-bff-3000-daily.json`、`v008-bff-3000-rollback.json`、`v008-bff-3000-final.json`
  記錄各次驗收。日常服務保留，隔離 3110／8110／8111 與暫時診斷 wrapper 已停。

最終只修改本機 `.env` 的 `RAG_POSTGRES_RELEASE_ID`、`RAG_EVIDENCE_V3_ENABLED`、
`KNOWLEDGE_ROUTER_V2_ENABLED` 三個非秘密設定；未寫入新知識資料、重建向量或更動 v004。
`.rag-work/v008-development-rollback.json` 只保存這三個設定原值／是否不存在，沒有複製任何 secrets。
日常 PID 記錄在 `.qa/development-stack-pids.json`，停止腳本先核對監聽埠與程序父子關係。

需要回退時，在原專案根目錄依序執行（本機 ignored 操作輔助檔，不是 production 部署介面）：

```powershell
.qa/stop_recorded_stack.ps1 -RecordName development-stack-pids.json
services/agent-runtime/.venv/Scripts/python.exe .rag-work/local_v008_config.py rollback
.qa/start_v008_stack.ps1 -Everyday -UseEnvironment
services/core-api/.venv/Scripts/python.exe .qa/v008_bff_smoke.py 3000 rollback
```

恢復 v008 使用相同流程，將 `rollback` 設定動作改為 `activate`，smoke 模式改 `final`。
啟動／回退前若設定或 PID 與記錄不符，腳本拒絕操作，應先檢查而非停掉其他服務。
真人語音、真機、Lighthouse、三角色獨立問答介面與 production 仍未在此次驗收範圍。

## 2026-10-05 合併整理與常駐失敗診斷

使用者授權收尾後，PR #67 已合併（main `fdb3562`）。由該 main 建立乾淨分支，僅 cherry-pick
#68 的兩個增量提交，再補此診斷；#68 不再依賴未合併 PR，舊工作區及歷史證據保留。
GitHub 上 #68 的最新 checks／合併紀錄為最終狀態依據。

`EvidenceService.retrieve_v3` 現在於失敗邊界輸出一筆 warning JSON，event 為 `rag_v3_failure`。
日常 Uvicorn logger 可直接呈現，不需 `.qa` wrapper 或另外開啟診斷 flag。欄位只有：

- `request_tag`：request_id 的 SHA-256 前 16 碼；排查時可對已知 request_id 計算同值，並非原始 ID。
- `stage`：safety／retrieval／context／generation／validation／response。
- `code`：對應階段的 FAILED／TIMEOUT，或 CONTEXT_REJECTED、JSON_REJECTED、
  CITATION_REJECTED、VALIDATION_REJECTED、PIPELINE_FAILED、DEADLINE_EXCEEDED、REQUEST_CANCELLED。
- `elapsed_ms`：本次 V3 服務處理耗時；不是整個 BFF 請求耗時。

只依 exception 型別及最多八層明確 cause 鏈辨識 TimeoutError／httpx timeout；沒有 typed cause
的 SDK 錯誤仍為一般失敗，不解析上游訊息猜測原因。30 秒服務 deadline 與外部取消分開，
取消保持向上傳遞。JSON／引用錯誤採固定集合分類，未知理由不輸出原文。正常無資料與安全拒答
不當成基礎設施失敗。未加 retry，未放寬來源、權限、引用或回應契約。

離線合成故障驗證：203 項相關回歸、28 項 CI 工具測試、Agent Ruff check／format 通過；
涵蓋 retrieval／generation／context／response 失敗、wrapped timeout、JSON／引用拒絕、
deadline／取消、併發 context 隔離及敏感文字不出現在日誌。此次沒有重跑真實 16 題，
也沒有用合成測試宣稱前述兩筆偶發備援已查明或修復。
