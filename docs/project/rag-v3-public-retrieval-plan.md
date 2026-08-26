# RAG v003 公開知識與後端風險控管計畫

- 文件狀態：Owner approved / implementation started
- 建立日期：2026-08-25
- Project owner：`IanHsu`
- 前一版：`data/rag-v2/candidates/v002/`
- 目標 artifact version：`v003`
- 目標 schema version：`3.0.0`
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
- `license_status=approved` 或 `open`，並保存實際授權依據與 owner staging approval
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
- license 與 owner review evidence 完整。
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
- 69 筆高風險與 5 筆未分類資料在一般 RAG 測試中均為 deny。
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

下列項目仍為待辦；不得因計畫、schema 或單元測試已存在，就視為資料已產生、Supabase 已同步或 staging 已切換。

### 10.1 本地資料與審核產物

- [x] 建立 `data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json`，以固定 hash
  綁定 Owner 的互動授權、v002 candidate、allowlist 與前次 acceptance；專案使用核准不取代逐來源
  license evidence，缺少明確 license evidence 的來源仍須在 source-family policy map 中維持 blocked。
- [x] 建立 `data/rag-v3/preflight/v001/`，凍結輸入檔案清單、17 個來源版本、來源／授權／storage URL、
  檔案大小與 SHA-256；本機沒有 raw source bytes，已明確記錄為不可用而非假裝完成原始檔驗證。
- [x] 建立並驗證 v002 immutable lock，鎖定 local v002 candidate、human-review 與 owner-acceptance
  formal artifacts；目前共 70 個 prior artifact entries。
- [ ] 建立 source-family policy map，逐來源記錄 purpose、assessment、risk 與 license 決策證據。
- [ ] 人工完成 5 筆 `risk_level=null` 的分類；完成前維持一般 RAG deny。
- [ ] 人工複核 27 筆 `stop_normal_rag=true`；不得自動改成可檢索。
- [ ] 驗證 243 筆非 current 內容的版本狀態；完成前維持 blocked。
- [ ] 實作 v003 generator、validator 與命令列執行入口。
- [ ] 產生 726 筆 v003 Chunk JSONL。
- [ ] 產生 Source Manifest、Chunk File Manifest、embedding reuse manifest、v002→v003 ID crosswalk、remaining-review worksheet、版本差異、validation report、test evidence 與 `SHA256SUMS.txt`。
- [ ] 若需交付封裝，建立自含式 v003 ZIP，並在封裝後再次驗證 immutable lock 與 checksum。

### 10.2 尚未完成的驗證

- [ ] 以 v003 schema 驗證全部 726 筆候選資料；目前尚無 v003 candidate 可驗。
- [ ] 驗證全部 `text` 與 `embedding_text` 對 v002 的 hash 相等，目標變更數皆為 0。
- [ ] 驗證 69 筆高風險及 5 筆未分類資料在一般 RAG 中全部 fail closed。
- [ ] 驗證 all-audience 設定不會繞過 purpose、assessment、risk 與 stop gate。
- [ ] 驗證第一批最多 307 筆 current、low／medium、`stop_normal_rag=false` 的官方內容可依完整 policy gate 檢索。
- [x] 執行完整 RAG ingestion 測試：2026-08-26 共 271 項通過；另有 v003 acceptance／preflight
  validator、9 項針對性測試及 contracts 全量 validation 通過。
- [ ] 執行 Golden Query、no-data、high-risk、authorization、citation 與 rollback 測試。
- [ ] 驗證 embedding reuse 為 726／726，且 provider、model、dimension、task type 與 fingerprint 完全相同。

### 10.3 Supabase、release 與外部狀態

- [ ] 建立新的 Supabase v003 release；不得覆寫既有 v002 row。
- [ ] 匯入 v003 release projection，並以 hash 驗證方式複製／綁定既有向量。
- [ ] 完成 Supabase 寫入後 read-back 驗證與數量、metadata、vector dimension 檢查。
- [ ] 建立並驗證 import、embedding reuse 與 rollback runbook。
- [ ] 取得 owner 對實際 staging cutover 的明確授權。
- [ ] 切換 staging release ID，並保留 v002 作為 rollback 版本。
- [ ] 切換後執行 live smoke tests；通過前不得宣稱 RAG v003 已上線。
- [ ] 尚未進行 Production 核准或 Production 部署。
- [ ] 尚未同步外部管理紀錄或雲端交付資料夾。
- [ ] 尚未建立本次 v003 實作的 Git commit。

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

目前結論：v003 已完成計畫、資料契約、Owner staging public-use acceptance、preflight 與 v002
immutable lock；source-family policy map、人工風險／版本複核、726 筆資料產生與資料級完整驗證、
Supabase 同步及 staging cutover 均尚未實行。
