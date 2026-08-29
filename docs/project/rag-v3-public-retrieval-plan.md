# RAG v003 公開知識與後端風險控管計畫

- 文件狀態：Owner approved / implementation started
- 建立日期：2026-08-25
- Project owner：`IanHsu`
- 前一版：`data/rag-v2/candidates/v002/`
- 目標 artifact version：`v003`
- 目前 Chunk schema version：`3.1.0`
- 環境：staging；Production 持續 blocked

## 1. Owner 決策

Owner 已透過互動指示確認：來源皆為公開資料，已人工看過並核准專案使用。
v003 將把這項決策記錄為獨立、可追溯的 owner review evidence；來源 URL、官方來源頁、
license evidence URL 與 storage URL 仍分欄保存，不以 owner 決策覆寫來源證據。

Owner 同意的 retrieval 方向如下：

1. 一般公開知識允許 `elder`、`family_caregiver`、`care_professional`、`system_admin` 使用。
2. 角色開放與風險開放分離；all-audience 不得繞過 risk、purpose、assessment 或
   `stop_normal_rag` gate。
3. 高風險資料可保留 embedding，但一般 RAG 不得回傳。
4. 後續若需要角色差異，由後端 policy 收斂，不重做 embedding。
5. v002 保持 immutable，v003 只以 successor artifacts 發布。

## 2. 固定範圍

目前固定 corpus 為 17 個來源、726 個 Chunk：

- 14 個臺灣官方來源，共 651 筆。
- 3 個公開研究／量表來源，共 75 筆。
- 726 筆均已有 `gemini-embedding-001`、1024 維
  `RETRIEVAL_DOCUMENT` embedding。
- v003 不修改 `text` 或 `embedding_text`；沿用條件是
  `embedding_text_sha256` 完全相等。
- 研究來源只標示為 `research_evidence`，不得宣稱為政府官方知識或官方判定依據。

## 3. 官方資料的分批開放基線

下列四組互斥，合計 651 筆官方 Chunk：

| Cohort | 筆數 | v003 處理 |
| --- | ---: | --- |
| current、low／medium、`stop_normal_rag=false` | 307 | 補齊 policy 後可成為第一批一般 RAG 候選 |
| low／medium、`stop_normal_rag=false`，但非 current | 243 | 保留 blocked，完成來源版本核對後再開放 |
| low／medium，但 `stop_normal_rag=true` | 27 | 重新區分「來源知識」與「當下安全事件」，不得自動放行 |
| high／high_red_line／risk 未分類 | 74 | 保留 embedding，一般 RAG 持續 fail closed |

目前 74 筆風險資料包含：

- `high`：33 筆。
- `high_red_line`：36 筆。
- `risk_level=null`：5 筆；必須完成明確分類，不得以預設低風險補值。

## 4. v003 metadata 規則

### 4.1 公開分類

官方來源在有來源與 owner review evidence 時：

- `data_classification=public`
- `distribution_scope=public_knowledge`
- 保存既有 `license_status`、可用的 license evidence 與 Owner staging project-use review；缺少
  license URL 不再是單獨的 staging deny reason，但 Production 仍須另外證明 license permits use
- `production_approved=false`

公開研究來源：

- `data_classification=public`
- `distribution_scope=research_evidence`
- `is_official_source=false`
- 保留原作者、期刊／repository、版本及授權證據

### 4.2 Audience 與 purpose

官方一般知識的 audience 目標值：

```json
[
  "elder",
  "family_caregiver",
  "care_professional",
  "system_admin"
]
```

Purpose 不做全 corpus 單一預設。v003 保留既有有效用途，並依來源家族的 reviewed policy map
補入適用值，例如 `general_information`、`health_education`、`legal_reference`、
`resource_navigation`、`source_lookup`。正式評估、轉介、照顧計畫與表單填寫仍需專用 purpose
及 assessment gate。

### 4.3 Assessment 與 risk

- 缺少 assessment Boolean 不得默認為 `false`。
- `requires_official_assessment=true` 只表示正式資格、等級、額度或主管機關判定。
- `requires_professional_assessment=true` 用於照顧判斷、篩檢、醫療或專業服務建議。
- `requires_human_review` 與 source review evidence 分開保存。
- `risk_level` 只由明確人工作業或既有證據更新。
- 來源文字提到自殺、暴力、虐待或緊急事件，不等於使用者當下正在發生事件；runtime
  safety 必須依目前輸入與 deterministic policy 判斷。

### 4.4 Retrieval eligibility

`retrieval_eligible` 由 deterministic evaluator 重算，不直接批次設為 `true`。一般 RAG 至少要求：

- 官方公開來源，或明確允許的獨立 research route。
- `current_status=current`。
- `risk_level` 為 `low` 或 `medium`。
- `stop_normal_rag=false`。
- audience、purpose 非空且包含呼叫情境。
- assessment 欄位為原生 JSON Boolean。
- project-use authorization 完整；license URL 缺少本身不構成 staging 自動封鎖。
- `retrieval_block_reasons=[]`。

## 5. 新契約與產物

v003 實作預計新增：

1. `contracts/schemas/rag/rag-chunk-v3.schema.json`
2. v003 owner public-use review acceptance schema 與固定雜湊 evidence
3. `data/rag-v3/preflight/v001/` validation inventory 與 v002 immutable lock
4. `data/rag-v3/candidates/v003/chunks/*.jsonl`
5. Source Manifest、Chunk File Manifest、embedding reuse manifest
6. v002 → v003 ID crosswalk
7. policy decision／remaining-review worksheet
8. version difference、validation report、test evidence 與 `SHA256SUMS.txt`

新契約必須支援：

- `review_status` 與人工作證 evidence 的明確關聯。
- `embedding_status` 可表達 hash-verified reuse，而不是錯誤宣稱重新 embedding。
- owner internal/staging approval 與來源 license evidence 分離。
- Production gate 仍固定 blocked／false。

## 6. Embedding 重用與 Supabase 切換

v003 使用新的 version-qualified Chunk ID，因此 Supabase 不直接改寫 v002 row。同步時：

1. 建立新的 v003 release projection。
2. 依 `embedding_text_sha256` 與固定 embedding profile 複製／重用既有向量。
3. 驗證新舊向量 fingerprint、dimension、provider、model 與 task type 完全相同。
4. 先跑 all-role、no-data、高風險、purpose、citation 與 rollback smoke tests。
5. 驗證通過後才切換 staging release ID；v002 保留供 rollback。

本計畫階段不直接寫入 Supabase；外部同步需要獨立執行與 read-back evidence。

## 7. 實作順序

1. 鎖定 v002 bytes、schema、config、tests 與目前 owner acceptance。
2. 建立 RagChunkV3 與 owner public-use acceptance contract。
3. 建立 source-family policy map，列出每個 metadata 決策的 evidence。
4. 產生 v003 candidate、crosswalk、hash、差異與 remaining-review worksheet。
5. 驗證 726 筆 `text`／`embedding_text` hash 與 v002 完全相等。
6. 驗證 74 筆 high／unknown 全部不可進一般 RAG。
7. 驗證第一批最多 307 筆官方 candidate 能通過完整 policy gate。
8. 建立 Supabase v003 import／embedding reuse／rollback runbook。
9. 經 owner 明確授權後，才執行外部同步與 staging release cutover。

## 8. 驗收條件

- v002 immutable lock 在 v003 建置前後一致。
- 726 筆 JSONL 通過 schema、duplicate-key、blank-line、Boolean、ID 與連續 index 驗證。
- `text_changed_count=0`、`embedding_text_changed_count=0`。
- embedding reuse match 為 726／726；不呼叫 embedding provider。
- 69 筆高風險資料在一般 RAG 中均為 deny；5 筆 Owner 判定的一般風險表單範例以 policy overlay
  映射為 `low`，且 assessment 欄位不完整時仍不得回覆。
- all-audience 開放不會繞過 risk／purpose／assessment gate。
- 研究來源不會被標成官方來源。
- staging 回應保留完整 citation 與 `production_approved=false`。
- Golden Query、no-data、high-risk、authorization、citation 與 rollback 測試零失敗。

## 9. 明確不包含

- 不覆寫或刪除 v001／v002。
- 不自動診斷、評定資格、確認 CMS 等級或完成轉介。
- 不因 embedding 相似度啟動危機流程。
- 不將 74 筆 high／unknown 直接改為一般 RAG 可用。
- 不把研究來源改稱政府官方知識。
- 不在沒有外部同步授權時修改 Supabase release。
- 不宣稱 Production 已核准。

## 10. 實行狀態（截至 2026-08-26）

本機 v003 candidate 已產生並完成資料級驗證；Supabase 同步與 staging cutover 仍未執行，不得將本機完成
誤述為已上線。

### 10.1 本地資料與審核產物

- [x] 建立 `data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json`，以固定 hash
  綁定 Owner 的互動授權、v002 candidate、allowlist 與前次 acceptance；專案使用核准不取代逐來源
  license evidence，缺少明確 license evidence 的來源仍須在 source-family policy map 中維持 blocked。
- [x] 建立 `data/rag-v3/preflight/v001/`，凍結輸入檔案清單、17 個來源版本、來源／授權／storage URL、
  檔案大小與 SHA-256；本機沒有 raw source bytes，已明確記錄為不可用而非假裝完成原始檔驗證。
- [x] 建立並驗證 v002 immutable lock，鎖定 local v002 candidate、human-review 與 owner-acceptance
  formal artifacts；目前共 70 個 prior artifact entries。
- [x] 建立 `data/rag-v3/review/acceptance/v002/`，以固定 hash 保存 Owner 對 726 筆人工審核完成、
  來源版本為最新及 13 個公開來源可供本專案使用的明確決策；沒有 license URL 不再被視為單獨否決理由，
  但本批不自動改寫既有 `license_status`。
- [x] 建立 `data/rag-v3/preflight/v002/` 與 `data/rag-v3/audits/v001/preflight/`，分別鎖定建置輸入、
  v002 prior artifacts、格式化後的 validator 輸入及 immutable v003 candidate。
- [x] 後續 runtime policy 測試與 live smoke 文件使 source-family audit v001 的 current-input inventory
  依設計失效；保留 v001 bytes，並建立 `source-family-policy/audits/v002/preflight/` successor，鎖定
  audit v001、既有 policy candidate 與更新後的 29 個 validation inputs。
- [x] 建立 `source-family-policy/candidates/v002/`，逐來源記錄 purpose、assessment、risk、角色與
  project-use 決策；13 個缺少 license URL 的來源不再因 URL 缺少而自動封鎖。
- [x] 依 Owner 的「一般風險值」決策，將 5 筆表單範例以 policy overlay 映射為 canonical `low`；
  v003 Chunk bytes 與既有 `license_status` 均未改寫。
- [x] 2026-08-28 Owner 核准 27 筆 low／medium、`stop_normal_rag=true` 內容可進入「依身份別逐筆確認」的
  條件開放複核；本次不等於直接啟用。v006 acceptance 維持原 Chunk bytes、`stop_normal_rag=true` 與
  current runtime deny，27／27 均標記 audience／purpose review pending，完成 verified successor 前不得檢索。
- [x] 依 Owner 的最新版本確認更新版本狀態：725 筆 `current`、1 筆保留 `superseded`。
- [x] 實作 v003 verified-candidate generator、validator 與命令列執行入口。
- [x] 產生 726 筆 v003（schema 3.1.0）Chunk JSONL；全部 `review_status=verified`、
  `production_approved=false`。
- [x] 產生 Source Manifest、Chunk File Manifest、v002→v003 ID crosswalk、human-review decisions、
  版本差異、validation report 與 `SHA256SUMS.txt`。
- [ ] 若需交付封裝，建立自含式 v003 ZIP，並在封裝後再次驗證 immutable lock 與 checksum。

### 10.2 尚未完成的驗證

- [x] 以 v3.1 schema 驗證全部 726 筆候選資料；17 個 source files、726 筆均通過。
- [x] 驗證全部 `text` 與 `embedding_text` 對 v002 的 hash 相等；變更數皆為 0。
- [x] 以 deterministic policy evaluator 驗證 69 筆 high／high-red-line、stop 與非 current 內容均
  無法進 ordinary retrieval；5 筆 owner risk overlay 的 effective unclassified count 為 0。
- [x] 以 policy-level tests 驗證四種角色可搜尋合規官方候選，但 purpose／assessment 回覆 gate 不會
  被繞過；runtime 尚未接入，仍不得視為 live E2E。
- [x] 2026-08-27 建立並接入 runtime policy v002：554 筆 ordinary retrieval candidates 中有 522 筆
  response-metadata-ready；assessment=true 可回覆一般資訊並由 Runtime 固定附 advisory，空 purpose
  與缺失／非 boolean assessment 仍 fail closed。完整 live backend relevance gate 尚待 E2E。
- [x] 2026-08-27 建立 runtime policy v003 staging successor：以既有 enum 分類 A 單位手冊原本空白的
  32 筆 purpose，並補齊來源層 `general_information` 交集；554／554 筆具備 response metadata，purpose
  gate、高風險與 research 排除保持。32 筆分類仍為 `needs_review`，Production 不因此解鎖。
- [x] 2026-08-28 Owner 已完成人工檢核並核准上述 32 筆 purpose 分類；immutable v006 closeout
  acceptance 將 32／32 記錄為 `verified`、`needs_review=0`。本次沒有改寫 v003 runtime policy；後續若
  發布 runtime successor，必須 hash-bind v006 並維持既有 purpose／assessment gates。
- [x] 執行完整 RAG ingestion 測試：2026-08-27 共 304 項通過；candidate validator、Ruff check／format
  及 contracts 全量 validation 均通過，candidate validation report 為 18 PASS／0 FAIL。
- [x] source-family policy v002 的 schema 單元測試 4 項與 v001／v002 targeted integration 14 項通過；
  policy validation report 為 21 PASS／0 FAIL。
- [x] 執行 10 個離線 Golden policy／advisory／citation cases；no-data、high-risk、角色與 purpose gate
  均通過。live relevance、遠端 activation 與 rollback 測試仍待完成。
- [x] 驗證 embedding reuse 為 726／726，且 provider、model、dimension、task type 與 fingerprint 完全相同；
  本批未呼叫 embedding provider。

### 10.3 Supabase、release 與外部狀態

- [ ] 建立新的 Supabase v003 release；不得覆寫既有 v002 row。
- [ ] 匯入 v003 release projection，並以 hash 驗證方式複製／綁定既有向量。
- [ ] 完成 Supabase 寫入後 read-back 驗證與數量、metadata、vector dimension 檢查。
- [ ] 建立並驗證 import、embedding reuse 與 rollback runbook。
- [ ] 依 v006 對 27 筆 conditional-stop chunks 逐筆完成 audience／purpose 驗證，建立 versioned runtime
  successor；在此之前 current runtime candidate pool 固定維持 554 筆。
- [ ] 取得 owner 對實際 staging cutover 的明確授權。
- [ ] 切換 staging release ID，並保留 v002 作為 rollback 版本。
- [ ] 切換後執行 live smoke tests；通過前不得宣稱 RAG v003 已上線。
- [ ] 尚未進行 Production 核准或 Production 部署。
- [ ] 尚未同步外部管理紀錄或雲端交付資料夾。
- [x] 本次 v003 verified-candidate 實作納入獨立 Git commit；未推送遠端。

### 10.4 已完成的基線（非上線證據）

- [x] 建立本計畫文件。
- [x] 建立 `rag-chunk-v3.schema.json`。
- [x] 建立 `rag-owner-public-use-acceptance-v3.schema.json`。
- [x] v003 schema 契約單元測試 6 項通過。
- [x] contracts 全量 schema validation 通過。
- [x] 建立可重建、拒絕覆寫、原子發布的 v003 acceptance／preflight builder 與 validator。
- [x] 建立 v003 owner acceptance package；`review_status=needs_review`、external sync 未授權、
  Production blocked。
- [x] 建立 v003 preflight v001；17 sources／726 chunks、70 個 prior artifact entries 與完整 input
  inventory 均通過 hash read-back 驗證。
- [x] 建立 v3.1 verified successor contract、Owner human-review acceptance v002、preflight v002、
  v003 candidate 與 audit preflight v001；舊 acceptance／preflight／v002 candidate 均保持 immutable。
- [x] 建立 Owner source-family policy acceptance v003、policy preflight v002、source-family policy
  candidate v002 與 current-input audit preflight v002／v003 successors；audit v001／v002、policy v001 與
  v003 Chunk candidate 保持 immutable。audit v003 鎖定本次 purpose-classification 後的 32 個目前輸入。

目前結論：本機 v003 已完成 726 筆 Owner 人工審核狀態升級、來源版本決策、candidate 產生與資料級完整
驗證，全部為 `verified`；source-family policy v002 也已完成 Owner project-use evidence、四角色 retrieval
方向及 5 筆 canonical `low` overlay。2026-08-28 v006 closeout acceptance 已把 32 筆 A 單位 purpose
分類升級為 Owner `verified`，並記錄 27 筆 `stop_normal_rag=true` 為可進入身份別條件開放複核；27 筆在
逐筆 audience／purpose 驗證完成前仍維持 runtime deny。hash-pinned runtime policy v003、10 個離線
Golden cases 與長者長照法 live smoke 已完成；完整 live relevance Golden Query、runtime successor、
Supabase 同步及 staging cutover 仍尚未實行。Production 固定 blocked；依目前 repository 證據，遠端
Supabase 仍是 v002／`needs_review=726`。
