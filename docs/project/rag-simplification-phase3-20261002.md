# RAG 簡化第 3 批：自然問句 Hybrid 與來源回答

使用者同意分批收斂後，本批完成本機 runtime、SQL、生成與契約調整。先將第 2 批獨立提交為
`2d946ce`，再由三位 GPT-6.1 Sol subagents 分工准入／backend、生成／provider、契約／測試；
主代理負責整合、完整路徑覆核與最終驗證。第 3 批變更尚未 commit 或 push。

## 實際行為

新路徑為自然問句 → 角色／用途及來源准入 → pgvector dense＋PostgreSQL FTS／trigram
Hybrid → 最多 5 筆完整來源 → 一次模型生成 → 引用與輸出檢查。
沿用既有混合權重與 0.7 relevance floor，沒有新增 learned sparse embedding 或另一個搜尋服務。

- 不再需要精確題目清單、人工 support sets、固定答案或最低 3 筆來源。
- 模型只使用已檢索來源；完整回答回 `SUFFICIENT`，部分有據回 `PARTIAL` 並列出缺少的面向。
- 證據不足／待澄清有固定 fallback；不在無資料時讓模型補猜。上游或輸出格式錯誤回 `FAILED`。
- 每個引用 ID 必須來自檢索結果，且至少附一段該來源正文的完全相同原文錨點；URL 由伺服器附加。
- 生成前後皆保留既有安全檢查，包含部分回答的缺口文字。Context 保留來源全文，不為通過長度限制截斷條件；超出預算則 fallback。
- Bedrock、Gemini、OpenAI-compatible 共用此 prompt；只有伺服器建立的 grounded 回合使用至少 2048 output tokens，一般回合保留原設定。

原文錨點驗證只能確認引用確實出現在來源，**不能證明回答每個句子的推論正確**。
這批沒有加入第二個語意判官、逐筆人工工作台或新封存鏈。

## 資料准入

SQL 與 Retriever 共用同一份固定規則；保留 release／embedding profile、完整匯入 receipt、
embedding 文字 hash、正文 hash、官方 URL、角色／用途、stop 及風險限制。
review metadata 如實保留，staging 的 needs_review 不再單獨構成新路徑的拒絕原因。

- unknown 現行性只可用於一般資訊，並附明確提醒；法律用途及命中現行性詞彙的問題要求 current。
- 現行性詞彙判斷是有限的中文 heuristic，不是完整語意分類，也沒有上網重驗資料日期。
- assessment 為 null 時不改原始資料；回答採保守評估提醒，不宣稱無需評估。
- 空 audience／purpose、非官方、高風險、stop、其他未退役封鎖原因仍不得搜尋。
- `older_adult` 與 `elder` 視為同義；不猜測 `caregiver` 是家屬或專業人員。
- 四個已有公開專案使用證據的官方來源，允許保留歷史 `internal/internal_knowledge` 標記進入此內部端點；仍逐筆驗原 audience／purpose，不放行其他 internal 或 restricted。

四來源為 A 單位手冊、其附件、居督手冊表單附件及長照法。
相容 catalog 在 `public_knowledge_policy.py`，證據對應舊
`data/rag-v3/governance/source-family-policy/candidates/v002/source-family-policy-map.json` 的
`OWNER_REVIEWED_PUBLIC_USE`／`RECORDED_LICENSE_EVIDENCE`、`STAGING_PROJECT_USE`。
這是四個來源的歷史分類相容，不依賴 554 筆 chunk 清單，也不需要新增人工表格。

以第 2 批 658 筆本機候選套用新規則，准入結果如下；同一筆可符合多個角色，不能加總。

| 角色 | 一般資訊，可含 unknown | 一般資訊，要求 current | 法律參考，要求 current |
| --- | ---: | ---: | ---: |
| 長者 | 97 | 28 | 21 |
| 家屬 | 135 | 39 | 21 |
| 專業人員 | 464 | 245 | 71 |
| 管理員 | 50 | 50 | 50 |

以上是 metadata 准入數，尚未套用實際問句的 ranking／分數篩選，**不是搜尋命中率**。
71 筆低風險法條均可供專業人員檢索；高風險／stop 那筆仍排除。
長者與家屬只有 21 筆符合法條原始角色範圍，沒有沿用舊 overlay 統一放行四角色的做法。
角色標記是否過度限制，留待實際失敗問題定位後修資料，不能把 658 筆都宣稱可供所有人查詢。

## 啟用與相容性

`RAG_EVIDENCE_V3_ENABLED` 仍預設 false。本批未改 `.env`、資料庫、真實 provider 或 release。
V3 只支援非 production 的 staging PostgreSQL，需有效 release/profile 與 provider，不能搭配 all-audience override。
啟用時不讀舊 evidence policy 或 source-family policy 的檔案／SHA，也不會因殘留舊檔路徑而失敗。

V1／V2 保留原 3–5 筆契約及一般嚴格准入；V3 關閉時仍載入既有 source-family overlay。
V3 啟用時它們共用新設定的 retriever，沒有另建一組舊 release 連線，因此不承諾同時維持舊 overlay 的結果集合。
AgentRun／Core／前端回應契約不增新狀態；V3 的完整／部分回答由現有 reply_text 顯示，失敗走既有 fallback。
私有端點的服務身份驗證、Core 的 Consent／角色授權、使用者記憶和照護資料權限不變。

## 驗證與剩餘工作

| 檢查 | 結果 |
| --- | --- |
| Agent Runtime 全套 | 805 passed，36.25 秒 |
| 靜態 schemas／examples／OpenAPI | `validate_contracts.py contracts` 全數通過 |
| Agent live contract verifier | 全數通過；in-process ASGI、合成來源／provider，包含 V3 實際 service 路徑 |
| 既有 Core → Agent 合成 HTTP 邊界 | 5／5 passed；mock provider，未測 Core 授權或真實 RAG |
| Ruff lint／format | Agent Runtime 及兩支 contract scripts 通過，122 個檔案格式檢查通過 |
| 本機 658 筆准入盤點 | 各角色統計如上；未連資料庫或 provider |
| Git diff whitespace | `git diff --check` 通過 |

覆蓋自然改述、單筆／兩筆／五筆引用、PARTIAL 缺口、unknown 提醒、法律 current、空資料不生成、
惡意來源指令、偽造引用／原文、錯誤內容 hash／release／profile、provider 失敗、timeout、
安全拒答、V3 開關兩側與既有 V1／V2 契約。這些測試不是實際模型的答覆品質評測。

覆核另外修正 SQLAlchemy 將 POSIX regex 的 `:spac` 誤認為 bind 的問題，並以實際 PostgreSQL
dialect 編譯與參數集合回歸；查詢向量拒絕全零、boolean、非數值與 NaN／Infinity。
這些檢查仍沒有在真實 PostgreSQL 執行新 SQL。

第 4 批從小型真實問題集開始，涵蓋申請流程、服務碼、法條、跨來源、資料缺口與時效問題；
量測檢索命中、引用與答案是否受支持、拒答、延遲，針對失敗的長表格或角色 metadata 修正。
先準備 embedding reuse／import 的可檢查差異與回復方式，再進行獲授權的真實 provider／DB 實測及環境切換。
不要求先完成 1,055 qrels，不以本批測試通過數冒充回答品質評分。
