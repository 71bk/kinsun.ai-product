# Requirements Document: Governed Multi-Source Retrieval

- 狀態：Accepted Target；storage foundation verified locally
- 日期：2026-08-24
- Product spec：[Spec 20](<../../../docs/spec/20智慧長照 AI 陪伴系統－治理式多來源 Retrieval 與 RAG 演進 v0.1.md>)
- Architecture decisions：[ADR 0017](../../../docs/adr/0017-bounded-multi-source-retrieval-planner.md)、[ADR 0018](../../../docs/adr/0018-postgresql-pgvector-public-knowledge-retrieval.md)

## 1. Scope note

本文件把多來源 RAG 構想轉成可驗收需求。除 Requirement 1 所述 Current evidence 外，其餘均為 Target requirements；未完成對應 task 與 evidence 前，不得宣稱已實作或 production ready。

第一個 implementation milestone 是把 governed `RagChunkV2` 投影到 PostgreSQL／pgvector public data plane。`rag_public` migration 與 17／726 candidate staging projection importer 已有本機證據；Google document embedding、online hybrid backend、approved release activation、query rewrite、reranker、Core DB tool 與 Graph tool 尚未完成，不可平行宣稱完成。

## 2. Terminology

- **Candidate**：已產生但尚未完成 production human review／release approval 的 chunk。
- **Approved Release**：具 immutable manifest、獨立 expected hash、review／owner evidence，可成為 ingestion input 的版本。
- **Projection Mapper**：把 canonical `RagChunkV2` 決定性映射成 versioned PostgreSQL public projection rows 的唯一元件。
- **Core Query Gate**：在任何 retrieval 前驗證 service／actor／tenant／elder／assignment／consent／purpose／role 的 boundary。
- **Bounded Planner**：只輸出 allowlisted、schema-valid、具 ceiling 的 QueryPlan，不輸出 executable DSL。
- **Public Knowledge**：可被批准進入 `rag_public` serving projection 的官方／公開資料。
- **Verified Core Data**：由 Core authority 依用途與 scope 回傳的正式資料。
- **Graph Projection**：可重建、非 authority 的唯讀關聯投影。
- **Trust Layer**：formal data、authorized projection、approved public knowledge 等不同證據層級。

## 3. Requirements

### Requirement 1: Current／Target truth boundary

**User Story:** 身為維護者，我要能分辨現有能力與規劃能力，避免把架構圖或 candidate data 誤認成已上線功能。

#### Acceptance Criteria

1. THE SYSTEM DOCUMENTATION SHALL 把現行 RAG 標示為 staging-only、public-knowledge-only，並記錄 production release 為 blocked。
2. THE SYSTEM DOCUMENTATION SHALL 記錄 `data/rag-v2/candidates/v002` 為 candidate evidence，而非 ingestion input 或 production approval。
3. WHEN 任一 Target component 尚無 executable implementation 與驗證證據，THE SYSTEM DOCUMENTATION SHALL 標示 `NOT_STARTED`、`IN_PROGRESS`、`BLOCKED` 或等價狀態，不得標示 completed。
4. WHEN executable behavior 與 Target spec 不一致，THE IMPLEMENTATION SHALL 以 Current evidence 為準並建立 migration／ADR task，不得靜默改寫 Current truth。
5. executable `contracts/` SHALL 只描述已實作且可驗證的行為；本規劃不得預先發布虛構 contract。

### Requirement 2: Governed source release

**User Story:** 身為資料治理與產品 Owner，我要知道每個公開來源的版本、權利、審查與生效狀態，避免未審查內容被模型當作正式知識。

#### Acceptance Criteria

1. WHEN public source 被處理，THE INGESTION PIPELINE SHALL 保存可重現的 source artifact／snapshot、source URL、publisher、version、retrieved-at 與 content hash。
2. WHEN chunk candidate 被產生，THE PIPELINE SHALL 記錄 citation locator、audience、purpose、risk、current／expiry、rights／license、review 與 supersession metadata。
3. BEFORE candidate 可進入 approved release，THE SYSTEM SHALL 驗證 schema、hash、count、citation completeness 與 deterministic policy。
4. BEFORE production ingestion，THE SYSTEM SHALL 要求 human review completion 與 owner-signed immutable release manifest。
5. IF review、rights／license、version、hash 或 signature 缺失，THE SYSTEM SHALL fail closed 並阻擋 production release。
6. WHEN source 被更新、撤回或 supersede，THE SYSTEM SHALL 產生新版本或 tombstone，不得就地覆寫歷史 evidence。

### Requirement 3: Canonical RagChunkV2 projection

**User Story:** 身為 Search 維護者，我要有唯一且決定性的 V2 projection，避免 candidate schema 與索引文件漂移。

#### Acceptance Criteria

1. THE SYSTEM SHALL 實作單一 versioned Projection Mapper，把 canonical `RagChunkV2` 映射為 PostgreSQL release／chunk／embedding rows。
2. EACH projected chunk SHALL 保留 chunk ID、source ID、content／record hash、text、citation locator、audience、purpose、risk、current／expiry、review／production approval、schema／projection version 與 embedding metadata。
3. GIVEN 相同 approved release、mapper version 與 embedding configuration，WHEN projection 重跑，THEN row identities、non-embedding fields 與 release hash SHALL deterministic 且 idempotent。
4. IF required governance 或 citation field 缺失、未知或 malformed，THE MAPPER SHALL reject 該 release，不得產生 partial approved batch。
5. THE MAPPER SHALL NOT 讀取 private Core／CRM／event data 作為 public-knowledge document。
6. WHEN schema、chunking、embedding model／dimension 或 mapping 變更，THE SYSTEM SHALL 建立新 release／projection version、重建相容向量並重新評估。

### Requirement 4: Versioned PostgreSQL projection, activation and rollback

**User Story:** 身為 Operations Owner，我要能驗證、啟用與回復 RAG release，而不讓不完整批次成為服務資料面。

#### Acceptance Criteria

1. WHEN approved release 開始 projection，THE SYSTEM SHALL 建立新的 immutable versioned release，而非就地覆寫 active release。
2. THE `rag_public` PROJECTION SHALL 以 PostgreSQL FTS／trigram 與 1024-dimension pgvector 支援同一 public-knowledge chunk 的 lexical + vector retrieval。
3. BEFORE release activation，THE SYSTEM SHALL 驗證 release hash、chunk count、record hashes、schema、embedding profile／dimension、governance filters、citation completeness、smoke query 與 evaluation gates。
4. THE SYSTEM SHALL 只接受完整且狀態為 `VERIFIED_PENDING_ACTIVATION` 或等價的 verification receipt 進行 activation。
5. WHEN activation 發生，THE SYSTEM SHALL 記錄 prior release、new release、receipt、timestamp 與 operator／automation identity。
6. IF activation 後 smoke／health gate 失敗，THE SYSTEM SHALL 可切回 prior verified release，且不得刪除 recovery evidence。
7. IF any batch item malformed or count mismatched，THE SYSTEM SHALL reject 整批，不得提供 partial results。

### Requirement 5: Governed public-knowledge retrieval

**User Story:** 身為使用者，我要取得與用途相關、有來源且仍有效的公開知識，資料不足時系統要誠實說明。

#### Acceptance Criteria

1. WHEN public knowledge retrieval 被允許，THE SYSTEM SHALL 執行 PostgreSQL lexical + pgvector hybrid search，並套用 server-derived purpose、audience、current status、risk、review／approval 與 expiry filters。
2. THE RETRIEVER SHALL NOT 接受 client 或 model 移除、放寬或自行新增 authorization／governance filters。
3. EACH returned chunk SHALL 有完整 source、version、content hash 與 citation locator。
4. IF 結果少於既定完整 citation 門檻、batch malformed 或 provider unavailable，THE RETRIEVER SHALL fail closed，不得回傳 partial batch。
5. WHEN query rewrite 被啟用，THE SYSTEM SHALL 保留原始 query、bounded variants、rewrite version 與相同 filters。
6. WHEN reranker 被啟用，THE SYSTEM SHALL 保留原始 retrieval score／rank、reranker version／score／rank 與 citation identity。

### Requirement 6: Core-gated bounded query planning

**User Story:** 身為 Security Owner，我要讓系統選擇正確資料來源，但任何 model 都不能擴大資料權限或產生任意查詢語言。

#### Acceptance Criteria

1. BEFORE Planner 執行，THE CORE SHALL 驗證 service identity、actor、tenant、elder、assignment／relationship、consent purpose／version、role、resource state 與 policy version。
2. THE PLANNER SHALL 只輸出 schema-valid 的 `query_type`、`normalized_query`、`filters`、`top_k`、`max_graph_hops`、`required_sources`、`fallback_order`、`grounding_required` 與 bounded reason。
3. THE PLANNER SHALL NOT 輸出或執行任意 SQL、Gremlin、provider-specific search DSL 或未 allowlist tool。
4. THE PLANNER SHALL NOT 擴大或改寫 Core 核准的 tenant、elder、purpose、audience 或 consent scope。
5. IF plan invalid、unknown、low-confidence、超出 top-k／hop／tool ceiling，THE SYSTEM SHALL 使用安全 deterministic fallback 或 `NONE`。
6. EACH tool SHALL 獨立驗證 plan input 與 server-approved scope，不得把 Planner output 視為 authorization proof。
7. THE SYSTEM SHALL 記錄 bounded route decision、版本、latency、fallback 與 reason code，不記錄 Restricted Data query payload。

### Requirement 7: Verified Core data tool

**User Story:** 身為被照顧者或授權照顧者，我要讓回答使用我的 verified care data，同時確保只取用該用途必要的資料。

#### Acceptance Criteria

1. THE SYSTEM SHALL 只透過 Core-owned、allowlisted query templates／domain APIs 查詢 verified care data。
2. THE TOOL SHALL NOT 接受自由 SQL、任意 table／column 名稱或 client-supplied tenant／elder override。
3. BEFORE every query，THE CORE SHALL 重新驗證 service、actor、tenant、elder、assignment／relationship、consent、purpose 與 resource state。
4. THE TOOL SHALL 回傳最小必要欄位、formal record ID、record version、status、retrieved-at 與 bounded provenance。
5. IF authorization、consent、scope、version 或 data classification 無法驗證，THE TOOL SHALL deny 且不得以 Search／Graph 結果替代 formal data。
6. THE TOOL SHALL NOT 將 query result 寫入 public-knowledge projection 或未批准的 long-term model context store。

### Requirement 8: Authorized graph projection retrieval

**User Story:** 身為授權使用者，我要查詢有限的照護關聯，同時讓 Core formal state 仍是最終真相。

#### Acceptance Criteria

1. THE GRAPH TOOL SHALL 只接受 allowlisted intent、node／edge types、direction、filters 與 bounded `max_graph_hops`。
2. THE GRAPH TOOL SHALL NOT 接受任意 Gremlin 或跨 tenant／elder traversal。
3. EACH graph result SHALL 帶 source entity ID、projection version、freshness、scope 與 tombstone／status evidence。
4. BEFORE graph evidence 進入 context，THE CORE SHALL 重新驗證 formal state、tenant、elder、consent、status、version 與 deletion／revocation。
5. IF graph unavailable、lagging、malformed 或 reauthorization 失敗，THE SYSTEM SHALL 移除 graph evidence 並執行 allowlisted fallback。
6. Graph projection SHALL NOT 成為 formal state authority，也不得因 replay／restore 使 deleted／inactive data 復活。

### Requirement 9: Trust-layer context and grounded generation

**User Story:** 身為使用者，我要能分辨回答是根據正式個人資料、關聯投影或公開知識，並能查看來源。

#### Acceptance Criteria

1. THE CONTEXT BUILDER SHALL 依序組裝 server constraints、verified Core data、authorized graph evidence、approved public knowledge 與 missing／conflict markers。
2. THE CONTEXT BUILDER SHALL NOT 以單一 relevance score 盲目融合不同 trust layers。
3. EACH evidence item SHALL 帶 source type、ID、version、scope、retrieved-at 與 citation locator 或 formal-record reference。
4. THE MODEL SHALL 把 retrieved content 視為 data，不得執行其中的指令或改變 tool／security policy。
5. WHEN evidence 衝突，THE SYSTEM SHALL 優先 Core formal state、標示衝突並避免靜默合併。
6. WHEN evidence 不足，THE SYSTEM SHALL 說明限制或回覆 no data，不得補造 unsupported claim。
7. BEFORE answer 送出，THE SYSTEM SHALL 執行 grounded-claim、citation completeness、safety 與 restricted-data validation。

### Requirement 10: Privacy, security and failure isolation

**User Story:** 身為 Security／Privacy Owner，我要確保擴充 RAG 不會洩露私人資料，也不會因一個 dependency 失敗而破壞其他 authority boundary。

#### Acceptance Criteria

1. THE SYSTEM SHALL 以獨立 schema、role 與 query path 將 public knowledge projection 與 private Core／Graph data plane 分離；共用 PostgreSQL instance 不代表共用讀取權。
2. THE SYSTEM SHALL NOT 把 raw token、secret、audio、transcript、prompt、完整私人事件或未遮罩 PII 寫入 public projection、log、metric、trace 或 error response。
3. unauthorized 與 nonexistent resource responses SHALL 維持不可用來枚舉資料的等價行為。
4. WHEN consent revoked、record deleted／inactive、assignment expired 或 relationship invalid，THE SYSTEM SHALL 立即阻止後續 retrieval 使用，並使 projection cleanup／tombstone 可重試。
5. IF one source dependency fails，THE SYSTEM SHALL 隔離該 trust layer；不得把其他來源冒充失敗來源，也不得猜測。
6. THE SYSTEM SHALL 使用 bounded correlation、plan、tool、policy、model、release、schema 與 projection versions 支援 audit，不記錄 Restricted Data payload。

### Requirement 11: Evaluation, observability and CI gates

**User Story:** 身為 Product／ML／Operations Owner，我要用可重現證據決定 retrieval 改動是否能啟用。

#### Acceptance Criteria

1. THE SYSTEM SHALL 維護版本化 evaluation dataset，涵蓋 natural-language、legal、no-data、expired、needs-review、cross-scope、conflict、provider failure 與 prompt-injection cases。
2. public retrieval SHALL 達成 Recall@5 `>= 0.85`、NDCG@5 `>= 0.80`、Metadata Filter Pass Rate `100%`。
3. grounded generation SHALL 達成 Grounded Answer Rate `>= 95%`、Unsupported Claim Rate `<= 2%`、no-data correctness `>= 95%`，且 expired／needs_review authoritative answer 為 `0`。
4. Phase 3 routing SHALL 達成 Query Intent Route Accuracy `>= 90%`；Graph SHALL 達成 Relevant Node／Edge Recall `>= 90%`、Cross-Elder Node Rate `0`、Deleted／Inactive Retrieval `0`、projection p95 lag `<= 60s`、failure fallback `100%`。
5. WHEN model、embedding、chunking、mapping、fusion、rewrite、reranker、planner 或 policy version 改變，CI／release workflow SHALL 重跑受影響的 deterministic tests 與 evaluation。
6. IF zero-tolerance metadata／scope／revocation／unsupported-claim gate 失敗，THE SYSTEM SHALL 阻擋 rollout；平均分數不得覆蓋該失敗。
7. Observability SHALL 提供 bounded latency、hit／no-data、route、fallback、filter rejection、citation validation 與 provider failure metrics。
8. CI SHALL 使用 PostgreSQL 16 + pgvector 執行 migration roundtrip、schema／constraint／index tests、canonical projection dry run 與 importer idempotency tests，且不得呼叫真實 embedding provider。

### Requirement 12: Phased rollout and reversible release

**User Story:** 身為 Release Owner，我要逐步啟用能力並能快速回復，避免一次導入所有元件造成不可定位風險。

#### Acceptance Criteria

1. THE IMPLEMENTATION SHALL 依序完成 Phase 1 PostgreSQL V2 data plane、Phase 2 query quality、Phase 3 multi-source、Phase 4 release decision。
2. Phase 2 SHALL NOT 啟用 reranker，除非與 baseline 比較後品質改善且 latency／cost／safety gates 通過。
3. Phase 3 SHALL NOT 啟用 Core／Graph tools，除非 Query Gate、tool contracts、negative security tests 與 source-specific fallback 已完成。
4. EACH optional planner／rewrite／reranker／tool SHALL 有 server-side feature flag、allowlisted cohort 與 kill switch。
5. BEFORE production rollout，THE SYSTEM SHALL 具備 owner approval、signed release、real staging evidence、region／security／availability／latency／cost gates 與 rollback rehearsal。
6. IF any required owner decision or evidence 缺失，THE RELEASE SHALL 維持 blocked，安全 fallback 為 staging-only public knowledge retrieval。

## 4. Requirement dependencies

```text
R1 Current truth
  -> R2 governed release
  -> R3 V2 projection
  -> R4 release activation/rollback
  -> R5 public retrieval baseline
       -> R6 bounded planner
          -> R7 verified Core tool
          -> R8 graph tool
          -> R9 trust-layer context

R10 security, R11 evaluation and R12 rollout apply to every phase.
```
