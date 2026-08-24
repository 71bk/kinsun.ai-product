# ADR 0018: 以 PostgreSQL FTS + pgvector 取代 OpenSearch 作為公開知識檢索資料面

- 狀態：Accepted Target Architecture
- 日期：2026-08-24
- 決策者：Project Owner／Architecture Owner
- 相關規格：[Spec 20](../spec/20智慧長照%20AI%20陪伴系統－治理式多來源%20Retrieval%20與%20RAG%20演進%20v0.1.md)
- 延伸：[ADR 0017](0017-bounded-multi-source-retrieval-planner.md)

## Context

Current implementation 仍有 OpenSearch adapter、Bedrock document embedding workflow 與 AWS
staging 設定，但 AWS Hackathon 帳號已結束，也沒有可延續的 OpenSearch deployment evidence。
Repository 已有 17 個來源、726 個 `RagChunkV2` candidates，以及 Core PostgreSQL baseline 中的
`knowledge_source`、`knowledge_source_version`、`knowledge_chunk` 與
`knowledge_chunk_embedding`。現有 `knowledge_chunk_embedding` 只記錄 OpenSearch index／document
位置，沒有實際 vector 欄位，也沒有可供中文 lexical retrieval 使用的 serving projection。

同一 PostgreSQL instance 亦承載 `eldercare_ai` 私人正式資料。公開 RAG projection 若直接取得
整個 Core schema 權限，會破壞 ADR 0017 的 trust-layer 與最小權限邊界。

## Decision

1. Target public-knowledge search backend 改為 PostgreSQL 16、pgvector 與 PostgreSQL lexical
   search，不再以 OpenSearch 作為 Phase 1 前置條件。
2. 在同一 PostgreSQL instance 建立獨立 `rag_public` serving schema；`eldercare_ai` 保持 Core
   formal-data authority。兩者邏輯、權限與查詢路徑分離。
3. `rag_public` 使用 versioned release、chunk projection、embedding profile、chunk embedding 與
   ingestion run tables。RagChunkV2 是 projection input，不直接覆寫 Core formal rows。
4. lexical search 同時保存 generated `tsvector` 與 `pg_trgm` GIN index；中文 retrieval 品質仍需
   evaluation，未證明前不宣稱等同 OpenSearch BM25。
5. vector 固定為 `vector(1024)`。每個 release 最多綁定一個 embedding profile；profile 明確記錄
   provider、model、dimension、document task type 與 config version。資料庫 foreign key 與 typmod
   共同阻止不同 provider／model／dimension 混入同一 release。
6. projection importer 必須先完整驗證 candidate、hash、count、identity 與治理狀態，再於單一
   transaction 寫入；任一筆失敗不得留下 partial release。重跑相同 release 必須 idempotent，
   不得默默改寫既有 immutable content。
7. Agent Runtime 後續以 provider-neutral `SearchBackend` 接入參數化、固定模板的 PostgreSQL hybrid
   query；LLM 不得產生任意 SQL。
8. 正式長者／照護資料仍只透過 Core-owned bounded query templates／domain APIs 查詢，不因共用
   PostgreSQL instance 而授予 Agent Runtime `eldercare_ai` 讀取權。
9. CI 使用含 pgvector 的 PostgreSQL 16 image，驗證 migration、constraints、indexes、projection
   dry run 與 fail-closed behavior；CI 不呼叫真實 Google API。

## Rationale

- 移除已無法持續使用的 AWS/OpenSearch 營運依賴，保留未來更換 PostgreSQL provider 的彈性。
- PostgreSQL 可在單一 versioned public projection 支援 relational governance filters、lexical
  search 與 vector search，降低雙資料面同步成本。
- 獨立 schema 與最小權限讓 public retrieval 不必取得 private Core data。
- provider-neutral `SearchBackend` 與 embedding profile 讓搜尋與向量供應商能獨立替換。
- 先建立儲存與 deterministic import，再產生 Google embeddings，可避免付費向量沒有正式落點。

## Consequences

### Positive

- 17 sources／726 chunks 可先以 staging、vector-null 狀態落到可稽核資料面。
- model／dimension compatibility 可由資料庫約束，而不只依賴應用程式慣例。
- release、projection、embedding 與 ingestion receipt 可用 relational evidence 驗證。
- OpenSearch adapter 可保留為 Current／legacy code，migration 期間不必破壞既有 tests。

### Cost and trade-offs

- PostgreSQL FTS 對中文分詞能力有限，因此加入 trigram baseline 並要求 retrieval evaluation。
- pgvector HNSW index、release activation、connection pool 與 read-only role 仍需營運設計與量測。
- 現有 `eldercare_ai.knowledge_chunk_embedding` 是 OpenSearch locator metadata；在完成 verified
  cutover 前不刪除，也不把它誤稱為 vector storage。
- production approved release 仍受 726 candidates 的人工來源、rights、version 與 chunk review
  阻擋；儲存完成不代表 production 可用。

## Alternatives considered

### A. 繼續使用 OpenSearch

不採用作為 Target。帳號與 deployment foundation 已結束，維持它會讓下一階段依賴不可驗證的
外部環境。

### B. 把所有 Core 與 RAG 資料放進同一 schema 並由 Agent Runtime 直接查詢

不採用。物理上可共用 PostgreSQL instance，但權限、authority、retention 與 failure semantics
不同；直接查詢會破壞 Core Query Gate。

### C. 只保存 embedding，不保存原文與治理 metadata

不採用。citation、版本、審核、權限與重建都需要 canonical text、hash 與 provenance。

### D. 先產生 726 個 Google embeddings，再設計 schema

不採用。無法先證明版本相容性、transactional import、idempotency 與可回復性，且可能浪費 API
成本。

## Implementation sequence

1. 建立 `rag_public` schema、pgvector／pg_trgm extensions、tables、constraints 與 indexes。
2. 實作 deterministic RagChunkV2 projection importer，先以 vector-null staging release 驗證
   17 sources／726 chunks。
3. 實作 Google `RETRIEVAL_DOCUMENT` adapter與 embedding compatibility gate。
4. 實作 PostgreSQL lexical + vector fusion `SearchBackend` 與 retrieval evaluation。
5. 完成 human review、approved release activation、rollback與 production decision。

## Revisit conditions

- PostgreSQL lexical／vector retrieval 無法達成已定義的 Recall、NDCG、filter、latency或cost gates。
- 資料量或寫入模式使單一 PostgreSQL serving projection 無法滿足隔離與維運需求。
- PostgreSQL provider 不支援所需 extension、region、backup、PITR或read-only credential controls。
- 中文 lexical evaluation 顯示 `tsvector` + trigram 無法達標，需評估專用 search service。

即使重新評估，LLM 不得成為 authorization authority，private formal data 也不得因共用基礎設施
而進入 public semantic retrieval。
