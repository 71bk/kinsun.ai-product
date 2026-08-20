# RAG Metadata 修正計畫

- 文件狀態：Approved / PR 1 實作中
- 建立日期：2026-08-19
- 適用範圍：`data/rag-chunks/`、`data/rag-manifest/`、`contracts/schemas/rag/`、
  `services/rag-ingestion/`、`services/agent-runtime/src/agent_runtime/rag/`
- 前置目標：先修正 metadata contract、fail-closed retrieval 與引用完整性，再評估
  PostgreSQL／Supabase `pgvector` migration
- 約束：本文件是實作計畫，不代表 schema、資料、provider、index 或 production RAG 已完成

## 1. 結論摘要

目前 17 個官方公開知識來源、726 個 current Chunk 已具備來源、版本、風險、審查與
Allowlist 治理基礎，但資料存在兩種 metadata 形狀，且 runtime 對部分缺失欄位採 fail-open。
在切換到 Supabase PostgreSQL＋`pgvector` 前，應先完成下列三個可獨立審查與回復的 PR：

1. 缺少 scope、purpose、risk 或必要治理欄位時，retrieval 一律 fail closed。
2. 建立嚴格、版本化且 provider-neutral 的 `RagChunkV2`，以 successor artifacts 正規化
   既有 726 個 Chunk，不改寫舊版資料。
3. 補齊受治理的引用資訊與 staging／production gate，讓呼叫端能安全顯示來源。

完成這三步後，向量儲存層才改成 provider seam，並另開 Issue／PR 實作 `pgvector`。

## 2. 現況證據與問題

### 2.1 資料集與治理狀態

- `data/rag-chunks/approved/` 目前包含 17 個來源、726 個 Chunk。
- 目前 Allowlist 為 v002；`human_source_review=NOT_COMPLETED`、Owner 尚未簽署，
  `production_status=BLOCKED`。
- 726 個 Chunk 的 `review_status` 均為 `needs_review`，不得自動改成 `verified`。
- 36 筆 `risk_level=high_red_line`、35 筆 `stop_normal_rag=true`；舊資料說明只排除這兩類後
  記錄 630 筆可進一般 Agent context。
- Issue #10 preflight 進一步確認只有 420 筆 `current_status=current`；同時要求 current、
  low／medium risk、非空 scope 與兩個 assessment Boolean 後，只有 143 筆可安全標記為
  staging `retrieval_eligible=true`。
- 16 筆網頁 Chunk 沒有頁碼，引用必須依賴 `source_locator` 或官方頁面 URL。

### 2.2 Contract drift

- 661 筆使用巢狀 `metadata`，65 筆使用 top-level flat fields。
- 僅 72 筆帶 top-level `schema_version=chunk_v3`。
- [`rag-chunk.schema.json`](../../contracts/schemas/rag/rag-chunk.schema.json) 要求
  `schema_version=1.0.0`、hash 與巢狀 metadata；目前 ingestion validator 沒有完整執行
  這份 schema，因此資料與 executable validation 已產生 drift。
- `current_status=needs_verification` 同時承擔版本狀態與驗證狀態，語意混合。
- `data_classification=internal` 出現在公開來源上，混合了來源資料分類與發佈範圍。
- `language` 同時出現 `en`、`zh-Hant`、`zh-TW`；`locale` 則使用 `en-US`、`zh-TW`。
- direct source URL、official source page URL、license evidence URL 與 storage URL 尚未完整分離。

### 2.3 不完整治理欄位

目前盤點到的缺口如下；同一 Chunk 可能同時缺少多個欄位，因此不可直接把各列數字相加：

| 欄位 | 現況 |
| --- | --- |
| `allowed_audiences` | 65 筆缺少、10 筆為空陣列 |
| `allowed_purposes` | 65 筆缺少 |
| `risk_level` | 5 筆缺少 |
| `requires_official_assessment` | 5 筆缺少 |
| `requires_professional_assessment` | 225 筆缺少 |
| `human_source_review` | 579 筆未在 Chunk 層明列 |
| `production_gate` | 539 筆未在 Chunk 層明列 |

`human_source_review` 與 `production_gate` 可在有明確 Allowlist 證據時以 deterministic join
取得；其他缺值不得由 LLM 或程式猜測。無法由現有證據確定的欄位必須保留為待人工審查，
並阻擋 retrieval eligibility。

### 2.4 Runtime fail-open 與引用缺口

- [`filters.py`](../../services/agent-runtime/src/agent_runtime/rag/filters.py) 目前把缺少或空的
  audience／purpose scope 視為 unrestricted。
- ingestion 將缺少的 risk 正規化為 `unknown`，但 retrieval 只排除 `high`、`critical`、
  `high_red_line`，因此 `unknown` 可能通過。
- index document 已有 `source_locator`，但目前 retrieval projection 與
  `RetrievalResultV1` 沒有完整回傳。
- index document 帶有 `requires_human_review`，但 retrieval filter／projection 沒有完整執行。
- `review_status`、`license_status`、`production_gate` 尚未成為完整的 retrieval gate。

## 3. 修正原則

1. **Fail closed**：缺少或不認得的治理值一律不可進 Agent context。
2. **舊版不可變**：現有 JSONL、manifest、schema、review 與 delivery artifacts 先鎖定
   path、byte size、SHA-256；不得原地修改。
3. **Successor version**：metadata、schema、ID 或 hash 改變時建立新版本、version diff 與
   ID-to-ID crosswalk。
4. **不自動驗證**：不得自動設定 `review_status=verified`，不得推定 license、官方資格、
   專業判斷或正式 referral。
5. **來源與治理分離**：`text` 保持官方原文，`embedding_text` 只做保義的檢索清理；
   audience、purpose、risk、assessment 與 review gate 留在 metadata。
6. **Staging 與 production 分離**：未人工覆核資料只可在明確 staging override 下測試，
   且必須回傳 `production_approved=false`；production 仍保持封鎖。
7. **Provider-neutral**：metadata 與 retrieval contract 不綁定 Bedrock、OpenSearch、Gemini、
   Cohere 或 `pgvector`。
8. **公開知識限定**：不引入任何真實長者資料、健康資料、對話、記憶、Consent 或授權狀態。

## 4. Issue／PR 1：缺失 metadata 一律 fail closed

建議 Issue／PR 標題：

```text
fix(rag): fail closed on incomplete retrieval metadata
```

### 4.1 目標

先封住目前 runtime 的安全缺口，不等待完整資料遷移。此 PR 不修改既有 JSONL bytes，
也不呼叫 Bedrock、OpenSearch、Supabase 或其他外部服務。

### 4.2 預計修改

- 調整 `services/agent-runtime/src/agent_runtime/rag/filters.py`：
  - 缺少 audience／purpose → deny。
  - 空 audience／purpose → deny，不再代表 unrestricted。
  - 缺少、空白或未知 `risk_level` → deny。
  - 一般 RAG 只允許 contract 明列的低／中風險值。
  - `stop_normal_rag=true` 與 high／critical／high_red_line 持續排除。
- 調整 ingestion normalization／index document：
  - 不把 `unknown` 當成可檢索風險。
  - 產生 deterministic `retrieval_eligible` 與受控
    `retrieval_block_reasons`，供測試與除錯使用。
  - `retrieval_eligible` 只代表必要 metadata 完整且通過 staging retrieval 規則，
    不代表 human verified 或 production approved。
- 補 negative tests：missing、null、空陣列、unknown enum、大小寫錯誤與額外欄位。
- 保持查無足夠合格來源時回 `NO_DATA`／安全 fallback，不讓 Agent 猜測。

### 4.3 驗收條件

- 目前 65 筆缺少 scope、10 筆空 audience、5 筆缺少 risk 的 Chunk 不可通過一般 retrieval。
- 缺少必要 assessment metadata 且無 evidence-backed deterministic rule 的 Chunk 也不可通過。
- 缺值不會被默認成 public、low risk、無需 assessment 或 unrestricted。
- `text`、`embedding_text` 與既有 formal artifacts 完全不變。
- Agent Runtime 與 RAG Ingestion 受影響測試、Ruff、contract validation 及
  `git diff --check` 通過。

## 5. Issue／PR 2：建立 canonical `RagChunkV2`

建議 Issue／PR 標題：

```text
feat(rag): canonicalize public knowledge metadata v2
```

此 PR 依賴 PR 1。

### 5.1 Preflight 與 immutable lock

正式產生 successor artifacts 前：

1. 凍結 validation input inventory，列出選定的 17 個來源、726 個 Chunk、Allowlist、
   schemas、config、validators、fixtures 與 tests。
2. 對每個既有 formal artifact 記錄 path、artifact kind、source/version、byte size 與 SHA-256。
3. 確認新輸出路徑不會覆寫既有 release。
4. 實作、測試與 final gate 使用同一份 inventory；任一輸入變更即使先前證據失效並重跑。

### 5.2 `RagChunkV2` 欄位群組

最終 JSON shape 以 schema review 為準，概念上分為：

| 群組 | 內容 |
| --- | --- |
| `identity` | `chunk_id`、`source_id`、`chunk_file_id`、`chunk_index`、schema/version |
| `content` | `text`、`embedding_text`、`char_count`、content hashes、content type |
| `citation` | title、publisher、page range、`source_locator`、中性來源 URL、官方專用 URL、license 與 storage URL |
| `retrieval_policy` | audiences、purposes、risk、assessment flags、safety route refs、eligibility |
| `governance` | review、version check、license、embedding、ingestion、production gate |
| `provenance` | parser/chunker version、source version/date、last verified、artifact lineage |

所有 controlled object 採 `additionalProperties=false`；global ENUM 只收錄在 current-selected
正式 artifacts 中確實觀察到、型別正確且有證據的非空值。

### 5.3 正規化規則

- 將 661 筆 nested metadata 與 65 筆 flat metadata 轉為單一 canonical shape。
- 分離：
  - `current_status` 與 `version_check_status`／`verification_status`。
  - `language` 與 `locale`。
  - `data_classification` 與 `distribution_scope`。
  - 中性的 direct source／source page，以及僅供官方來源使用的 direct official source／official source page、license evidence、storage URL；研究來源不得填入官方專用欄位。
  - source human review 與 runtime `requires_human_review`。
- 只做 deterministic、evidence-backed mapping；不使用 LLM 推定缺值。
- 可由 Allowlist 以 source／chunk identity 精確 join 的治理值，保留 evidence reference 後帶入。
- 無法確定的 audience、purpose、risk 或 assessment 值進入 human review worksheet，並保持
  `retrieval_eligible=false`。
- `text` 與 `embedding_text` 的 UTF-8 bytes 必須與來源版本一致；不得為 metadata 遷移改寫內容。
- `char_count`、content hashes 與 whole-file SHA-256 由 deterministic tooling 重算。

### 5.4 版本產物

- 新版 `RagChunkV2` JSONL 與獨立版本 JSON Schema；既有 schema bytes 不覆寫。
- 新版 Source Manifest、Chunk File Manifest 與候選 Allowlist v003。
- prior-version immutable lock。
- version-difference summary。
- 舊 ID → 新 ID 的 crosswalk；狀態改變只列 human-review recommendation。
- human review worksheet，列出每筆缺值、來源證據與 blocking reason。
- validation input inventory、validation report 與 SHA-256 清單。

所有新資料維持 staging／`needs_review`／production blocked；若未實際上傳，
`storage_target` 不得標記為 `google_drive`。

### 5.5 驗收條件

- 726 筆 successor Chunk 全數通過 `RagChunkV2` schema 與 duplicate-key／blank-line 驗證。
- ID 唯一、index 連續、page／locator 可追溯、Boolean 為原生 JSON Boolean。
- `char_count`、content hash、whole-file hash 與 manifest 記錄一致。
- 每個缺少必要治理證據的 Chunk 都明確被阻擋，沒有 silent default。
- 舊版 protected artifacts 的 path、size、SHA-256 在前後兩次驗證完全一致。
- 新舊 `text`／`embedding_text` 內容 bytes 相同，metadata 差異可由 version diff 與 crosswalk 追蹤。
- 沒有任何資料被自動標為 verified、embedded 或 production approved。

## 6. Issue／PR 3：回傳完整且受治理的引用

建議 Issue／PR 標題：

```text
feat(rag): return complete governed citations
```

此 PR 依賴 PR 2。

### 6.1 預計修改

- 新增 `RetrievalResponseV2`／`RetrievalResultV2`，至少回傳：
  - `chunk_id`、title、publisher。
  - page start／end 或 `source_locator`。
  - direct official source URL 與 official source page URL。
  - source version／publication evidence 與 `last_verified_at`（有證據才填）。
  - `review_status` 與 `production_approved`。
- storage URL 不回傳給一般 retrieval caller。
- 16 筆無頁碼網頁 Chunk 必須能由 `source_locator`＋官方頁面 URL 定位。
- staging 只有在明確 override 下可回傳 `needs_review` Chunk，且回應必須標示
  `production_approved=false`。
- production 必須同時通過：current、verified、license、source version、schema/hash、
  human source comparison、embedding、Golden Query、高風險與授權測試。
- V1 先保留相容期；V2 完成 live verification 後，才另行規劃 V1 deprecation。

### 6.2 驗收條件

- 每筆回傳結果都有可顯示且可追溯的 citation；資料不足時整批 fail closed。
- 16 筆無頁碼網頁 Chunk 可被明確定位。
- 不完整 citation、缺少 retrieval policy 或 production gate 不符的 Chunk 不會被回傳。
- Pydantic、JSON Schema、OpenAPI、valid／invalid examples 與 live verifier 一致。
- 錯誤與 fallback 不回填查詢內容、source text、storage URL、secret 或內部 trace。

## 7. PR 依賴與合併順序

```text
PR 1：先封住 fail-open
  ↓
PR 2：建立 V2 schema 與 successor artifacts
  ↓
PR 3：切換完整 citation contract
  ↓
另開 PR：EmbeddingProvider／VectorStoreProvider seam＋pgvector migration
```

每個 PR 都從最新 `origin/main` 建立獨立分支，不沿用其他功能分支，也不直接 push `main`。
建議分支名：

- `issue/<id>-rag-metadata-fail-closed`
- `issue/<id>-rag-chunk-v2`
- `issue/<id>-rag-citation-v2`

## 8. 驗證矩陣

### 8.1 每個 PR 都要執行

```powershell
git diff --check
git status --short
```

### 8.2 Agent Runtime

```powershell
cd services/agent-runtime
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

### 8.3 RAG Ingestion

```powershell
cd services/rag-ingestion
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### 8.4 Contract 與資料驗證

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
```

另需驗證：

- JSON／JSONL duplicate key、blank line、UTF-8、LF-only、no BOM。
- unique ID、continuous index、page range、locator、Boolean／null type。
- `char_count`、per-chunk hash、whole-file hash。
- source／page／license／storage URL 分離。
- prior-version immutable lock 前後一致。
- version diff、crosswalk 與 manifest path 完整。
- missing／empty／unknown audience、purpose、risk、assessment 的 negative tests。
- staging override 與 production gate 的 positive／negative tests。
- high-risk、`stop_normal_rag`、no-data、provider failure 與 citation completeness tests。

測試報告必須從實際 log 解析 PASS／FAIL／SKIP／ERROR、exit code、執行時間、命令、
test files 與 log SHA-256，不可在文件或程式中硬編測試總數。

## 9. 回復與風險控制

- PR 1 只改 runtime／normalization 行為；若出現 recall regression，可回復程式版本，
  不需改資料。
- PR 2 只新增 successor artifacts；舊版保持 immutable，可由舊 manifest／Allowlist 回復。
- PR 3 保留 V1 相容期；V2 有問題時可切回 V1，但不得繞過 PR 1 的 fail-closed 規則。
- 任一 finalizer 失敗都不得留下 discoverable half-built artifacts。
- 不執行 Supabase migration、AWS ingestion、embedding、OpenSearch alias cutover、Drive 同步或
  production enablement，除非另有明確 Issue、審核與使用者授權。

## 10. 本計畫不包含

- 不建立 `pgvector` table、index、migration 或 RLS policy。
- 不產生新 embedding，也不重建 OpenSearch index。
- 不選定最終 `EmbeddingProvider` 或 `VectorStoreProvider`。
- 不變更既有官方 source text 或 `embedding_text`。
- 不自動補齊缺失 audience、purpose、risk、assessment、license 或日期。
- 不執行 Google Drive／管理表同步。
- 不處理真實長者資料，不做診斷、正式資格判定或自動 referral。

## 11. 待 Owner 審核的四個決策

1. 同意先以 3 個 Issue／PR 完成 metadata、安全 gate 與 citation，再做 `pgvector`。
2. 同意舊版 artifacts 全部 immutable，只新增 `RagChunkV2` successor artifacts。
3. 同意缺少 scope、purpose、risk 或必要 assessment 證據時一律阻擋，不由程式或 LLM 推定。
4. 同意未人工覆核資料僅能在明確 staging override 下使用，production 持續 blocked。

Owner 已於 2026-08-19 核准開始，第一階段追蹤於 GitHub Issue #10，並從最新
`origin/main` 建立 `issue/10-rag-metadata-fail-closed`。
