# ADR 0017: 採用受限多來源 Retrieval Planner，而非 LLM 直接路由資料權限與查詢語言

- 狀態：Proposed Target Architecture
- 日期：2026-08-24
- 決策者：Project Owner／Architecture Owner／Security Owner（release 前須完成簽核）
- 相關規格：[Spec 20](../spec/20智慧長照%20AI%20陪伴系統－治理式多來源%20Retrieval%20與%20RAG%20演進%20v0.1.md)
- 搜尋儲存決策：[ADR 0018](0018-postgresql-pgvector-public-knowledge-retrieval.md)

## Context

目前系統已有 staging-only 公開知識 RAG：Bedrock embedding、OpenSearch Serverless BM25 + vector hybrid search、purpose／audience／governance filters、citation completeness 與 fail-closed behavior。另有 17 個來源、726 個 `RagChunkV2` candidates；它們已有本機 PostgreSQL staging projection evidence，但尚未完成 production human review、document embedding 或 online cutover。

長期產品需要回答三類資料問題：

1. 公開官方知識與服務指南；
2. Core 授權後的 verified care data／formal state；
3. 有限關聯查詢的 Graph projection。

原始構想以 LLM／Router 選擇 `search_docs()`、`query_database()` 與 `search_graph()`。若直接照圖實作，LLM 可能被誤用為授權層、產生任意 SQL／Gremlin／OpenSearch DSL、混合不同信任層的結果，或讓公開 index 承載私人資料。

## Decision

採用「Core Query Gate + Bounded Query Planner + source-specific tools + trust-layer context builder」：

1. Core 在 Planner 前驗證 service／actor identity、tenant、elder、assignment／relationship、consent、purpose、role 與 policy version。
2. Planner 只能輸出 schema-valid、allowlisted、具 ceiling 的 `QueryPlan`；不可輸出任意 executable DSL，也不可擴大 Core scope。
3. 公開知識使用單一 versioned search projection 同時執行 lexical + vector retrieval；Target backend 依 ADR 0018 改為 PostgreSQL FTS／trigram + pgvector，不強制拆成獨立 Vector Index 與 Search Index。
4. 正式結構化資料只透過 Core-owned query templates／domain APIs 查詢，不提供自由 SQL tool。
5. Graph 只提供 read-only、allowlisted edge／intent、bounded hops 的 projection query，採用結果前由 Core reauthorize。
6. Context Builder 依 formal Core data、authorized graph evidence、approved public knowledge 的信任層組裝，不做跨層盲目 score fusion。
7. Reranker 是 evaluation-gated、feature-flagged 的後續優化，不是第一階段必備元件。
8. 第一優先是完成 `RagChunkV2` human-review successor、approved-release mapper、Google document embedding、PostgreSQL release activation／rollback 與 evaluation evidence。

## Rationale

- 授權與 consent 屬 deterministic security boundary，不能交由概率式 model 決定。
- Core formal state、Graph projection 與 public knowledge 的 authority、freshness、scope 與 failure semantics 不同。
- 同一 versioned public projection 可同時支援 lexical 與 vector search；分拆實體資料面會增加同步、營運與一致性成本，現階段沒有收益證據。
- bounded plan 仍可取得 intent／rewrite／routing 的產品效益，同時保留可測試、可稽核與 fail-closed 行為。
- 先補齊 V2 data plane，才能用真實且受治理的資料評估 rewrite、reranker 與 multi-source planner。

## Consequences

### Positive

- 資料 scope、consent 與 authority 邊界可被 contract、negative test 與 audit 驗證。
- 公開知識、正式資料與 Graph 可以獨立演進、降級與 rollback。
- Planner 與每個 tool 都有 bounded schema，可建立 routing accuracy 與 failure-path evaluation。
- 避免為架構對稱性而建立不必要的 Vector／BM25 雙資料面。
- 可以先交付 Phase 1 的治理式 public knowledge RAG，再逐步增加能力。

### Cost and trade-offs

- 需要維護 Core Query Gate、source-specific contracts、projection versions 與 trust-layer context schema。
- 多來源回答不能只靠單一 relevance score，需要定義衝突、freshness 與 fallback 規則。
- Graph／Core tools 的新增速度較慢，因為每個用途都要明確的授權與資料最小化設計。
- Reranker 與 LLM-assisted rewrite 需額外 evaluation、latency 與成本 evidence。

## Alternatives considered

### A. 直接採用 LLM Router 與任意查詢語言

不採用。可塑性高，但無法可靠證明 scope、consent、query ceiling 與 no-side-effect failure；prompt injection 也可能改變 query intent 或 filters。

### B. 把所有資料放進單一向量資料庫

不採用。會模糊 public／private、formal／projection、current／expired 的界線，也難以正確處理 revocation、tombstone 與 transactional truth。

### C. 同時建立獨立 Vector Index 與 BM25 Search Index

現階段不採用。PostgreSQL public projection 可在同一 release 執行 lexical 與 vector retrieval；除非未來量測顯示需要分拆，否則維持單一版本化資料面。

### D. 一次完成 ingestion、rewrite、reranker、SQL 與 Graph

不採用。當前尚缺 approved release activation／online backend 與 production review evidence；同時擴大範圍會使 retrieval quality 與 security failure 無法定位。

### E. 永遠只保留 public-doc RAG

不採用作為長期方向。它無法安全回答使用者自己的 verified care data 或有限關聯問題；但在 Phase 3 前，這仍是安全的可交付基線。

## Implementation sequence

1. Phase 1：治理式 `RagChunkV2` release、PostgreSQL versioned projection／activation、evaluation 與 CI。
2. Phase 2：bounded intent／entity／rewrite；有 evidence 才加入 reranker。
3. Phase 3：bounded planner、Core verified-data tool、Graph projection tool、trust-layer context。
4. Phase 4：owner approval、staging evidence、security／region／latency／cost gates 與 production rollout。

## Revisit conditions

在以下情況重新評估本 ADR：

- PostgreSQL 單一 public projection 無法達成量測過的 isolation、latency 或 scaling requirement。
- Core query templates 無法涵蓋經批准的新用途。
- Graph traversal 需要超出既定 hops／edge allowlist。
- 新 reranker／model／embedding 使品質、成本或資料區域假設改變。
- 法規、來源 rights／license 或資料 retention 要求改變。

即使重新評估，LLM 不得成為 authorization authority，且 private formal data 不得因便利而混入 public knowledge projection。
