# Design Document: Governed Multi-Source Retrieval

- 狀態：Accepted Target；storage foundation verified locally
- 日期：2026-08-24
- Requirements：[requirements.md](requirements.md)
- Product spec：[Spec 20](<../../../docs/spec/20智慧長照 AI 陪伴系統－治理式多來源 Retrieval 與 RAG 演進 v0.1.md>)
- ADRs：[ADR 0017](../../../docs/adr/0017-bounded-multi-source-retrieval-planner.md)、[ADR 0018](../../../docs/adr/0018-postgresql-pgvector-public-knowledge-retrieval.md)

## 1. Design intent

本設計把既有 public knowledge RAG 演進為受治理的多來源 retrieval。核心原則是「先授權、後規劃；各來源自行驗證；依信任層組 context；所有新增能力可關閉與回復」。

本文件中的 component／field 名稱是 Target logical design。只有在 implementation、schema、tests 與 live verifier 同步完成後，才能新增或更新 executable `contracts/`。

## 2. Current baseline

| Area | Current evidence | Design implication |
| --- | --- | --- |
| Candidate corpus | 17 sources／726 `RagChunkV2` chunks；全部 `needs_review`、`production_approved=false` | 可用於 deterministic validation／evaluation，不是 Production ingestion input |
| Staging allowlist | `AI_Reviewed_Embedding_Staging_Allowlist_v002.json`；owner not signed、review not completed、production blocked | 保留 staging-only fail-closed boundary |
| Legacy embedding／search | Bedrock Cohere Embed v4、1024 dimensions、OpenSearch Serverless workflow／adapter；未有真實 deployment evidence | migration 期間保留 adapter，但不再是 Phase 1 Target |
| PostgreSQL projection | `rag_public` migration、FTS／trigram／HNSW indexes、embedding profile compatibility constraints，以及 17／726 candidate importer 已通過本機 integration tests；embedding rows 為 0 | 下一步才是 Google document embedding 與 online backend；不得宣稱已切換 runtime 或遠端 DB |
| Retrieval | purpose／audience mapping、BM25 + KNN、governance filters、top 5、3–5 complete cited chunks | Phase 1 不改安全語意，先替換資料投影 seam |
| Runtime | `/api/v2/rag/retrievals` request-bound service credential；malformed／no-data／failure fail closed | 新 Planner／tools 必須保留 request-bound authorization 與 batch atomicity |
| Deployment | staging stack desired count 0、model mock、無 production deployment evidence | 文件與 local tests 不可被宣稱為 deployed evidence |
| Missing | Google document embedding、approved release activation／rollback、PostgreSQL online backend、retrieval evaluation、query rewrite、reranker、Core data tool、Graph tool | 依 phase 分開交付與驗收 |

## 3. Architecture

```text
                            OFFLINE

 Public source artifact / web snapshot
                 |
                 v
 Source registry -> parse/normalize -> RagChunkV2 candidates
                                         |
                                         v
                     validation -> human review -> signed release
                                                       |
                                                       v
                                      V2 Projection Mapper + Embedding
                                                       |
                                                       v
                           versioned PostgreSQL rag_public projection
                              FTS / trigram + pgvector + governed filters

                             ONLINE

 User -> BFF -> Core Query Gate -> Bounded Planner
                  |                    |     |     |
                  |                    |     |     +-> Graph Projection Tool
                  |                    |     +--------> Verified Core Data Tool
                  |                    +--------------> Public Knowledge Tool
                  |                                      |
                  +----------- server-approved scope ----+
                                                         v
                                            Evidence Validator
                                                         v
                                      Trust-Layer Context Builder
                                                         v
                                        Grounded Model + Safety
                                                         v
                                      Citation / Output Validator
                                                         v
                                                       Answer
```

## 4. Component responsibilities

### 4.1 Source Registry and Snapshotter

- 管理 allowlisted public publishers／URLs／document identifiers。
- 保存 immutable source artifact 或 reproducible web snapshot。
- 記錄 content hash、publisher、version、retrieved-at、rights／license 與 supersession。
- 不接受 private Core／CRM／event sources進入 public lane。

### 4.2 RagChunkV2 Processor

- parse、normalize、chunk、citation locator 與 governance metadata。
- 產出 candidate、structured records、manifest 與 validation report。
- 不自行宣告 production approval。

### 4.3 Review and Release Builder

- 收集 source accuracy、rights／license、version 與 chunk review outcome。
- 只把完整審查的 chunks 放入 immutable approved release。
- 對 release manifest 使用獨立 expected hash，避免 manifest 自我宣告即生效。

### 4.4 V2 Projection Mapper

唯一的 canonical → search projection seam：

```text
RagChunkV2
  -> validate required fields
  -> normalize projection fields deterministically
  -> attach projection / schema / embedding versions
  -> emit immutable release + chunk rows + per-record digest
  -> embed approved text under the release's compatible profile
  -> emit ingestion / embedding receipts
```

Mapper 對任一 invalid item 採整批拒絕。embedding vector 本身可因 provider implementation 出現允許範圍內差異，但 source identity、text、metadata 與 projection manifest 必須可重現。

### 4.5 Versioned Release Manager

- 建立新 immutable release，不就地覆寫 active release。
- `rag_public` schema 以生成欄位、GIN 與 HNSW 同時支援 lexical／vector search。
- projection 後執行 exact count／hash／schema／embedding profile／dimension／filter／citation checks。
- verification receipt 通過後才 activation。
- 保存 previous verified release 供 rollback。

### 4.6 Core Query Gate

- 驗證 service credential、actor session 與 request binding。
- 取得 server-side tenant／elder／assignment／relationship／consent／purpose／role／policy。
- 產生不可被 Planner 擴大的 `ApprovedQueryScope`。
- deny 時不呼叫任何 retrieval tool。

### 4.7 Bounded Query Planner

Planner 可由 deterministic rules 起步，後續加入 LLM-assisted intent classifier；兩者都必須通過相同 output validator。

Target logical plan：

```json
{
  "query_type": "HYBRID",
  "normalized_query": "長照 2.0 喘息服務申請資格",
  "filters": {
    "purpose": "natural_language",
    "audience": "elder"
  },
  "top_k": 5,
  "max_graph_hops": 0,
  "required_sources": ["PUBLIC_KNOWLEDGE"],
  "fallback_order": ["PUBLIC_KNOWLEDGE", "NONE"],
  "grounding_required": true,
  "reason": "public_policy_question"
}
```

Validator 必須：

- 覆寫或拒絕與 `ApprovedQueryScope` 不一致的 filters。
- allowlist query types、sources、purposes、audiences 與 tools。
- 限制 query length、variant count、top-k、graph hops 與 total tool calls。
- 禁止 DSL／code fields、未知 keys 與 recursive plans。
- low-confidence 時使用 deterministic fallback 或 `NONE`。

### 4.8 Public Knowledge Tool

1. 使用 approved scope 建立 immutable governance filters。
2. 對原始／bounded rewritten query 產生 embedding。
3. 對同一 PostgreSQL release 執行 FTS／trigram 與 pgvector KNN。
4. 以版本化 fusion 合併 ranks。
5. 可選 feature-flagged reranker；不得改變 chunk identity 或 filters。
6. 驗證整批 citation／metadata，回傳完整 batch 或 no data。

### 4.9 Verified Core Data Tool

- tool registry 以 intent 對應固定 domain query template。
- template 決定 allowed parameters、columns、row limit、ordering 與 timeout。
- Core 根據 request context 注入 tenant／elder scope，拒絕 client/model override。
- 回傳 minimal view model 與 formal record references，不回傳 raw ORM／database rows。
- 不與 search score fusion；由 Context Builder 放入 formal-data layer。

### 4.10 Graph Projection Tool

- tool registry 以 intent 對應固定 traversal template。
- allowlist node／edge type、direction、filters、result limit 與 max hops。
- 回傳 projection version、freshness、source IDs 與 status evidence。
- Core reauthorization filter 移除 stale／deleted／inactive／cross-scope nodes。
- unavailable／lagging 時回傳 typed failure，讓 Planner／Context Builder 安全降級。

### 4.11 Evidence Validator

每種 tool 有不同 validator：

| Source | Required evidence | Reject when |
| --- | --- | --- |
| Public knowledge | release／source／chunk／content hash／version／locator／approval | missing citation、expired、needs review、wrong purpose／audience |
| Core data | formal record ID／version／status／authorized scope／retrieved-at | auth／consent／scope／version 不可驗證 |
| Graph | source entity ID／projection version／freshness／scope／status | lagging beyond policy、deleted／inactive、reauthorization failure |

### 4.12 Trust-Layer Context Builder

Context 使用區段化結構，而非把所有結果轉成一個 score list：

```text
POLICY_AND_SCOPE
FORMAL_CORE_DATA
AUTHORIZED_GRAPH_EVIDENCE
APPROVED_PUBLIC_KNOWLEDGE
MISSING_OR_CONFLICT_MARKERS
OUTPUT_AND_CITATION_RULES
```

正式資料與公開知識衝突時，保留兩者 provenance，formal state 優先；model 必須說明衝突，不得自行更新資料。

### 4.13 Grounding and Output Validation

- 對可驗證主張建立 evidence reference。
- public claims 必須有 citation；formal-data claims 必須有 record reference（對外可用安全 display reference）。
- 檢查 unsupported claim、citation mismatch、restricted data、medical／legal safety 與 injection residue。
- validation failure 時可做一次 bounded rewrite；仍失敗則回 safe fallback，不啟動無界限 retry。

## 5. Data and projection design

### 5.1 Public knowledge projection fields

以下為設計分類，最終 field names 由實作 mapping 與 contract 決定：

| Category | Fields |
| --- | --- |
| Identity | chunk ID、source ID、release ID、schema／projection version |
| Content | normalized text、title、section、page／locator、language |
| Retrieval | text fields、embedding、embedding model／dimension、fusion metadata |
| Governance | review status、production approval、risk、current status、expiry、superseded-by |
| Scope | purpose、audience、jurisdiction／region（如適用） |
| Provenance | source URL／publisher／version、source／content hash、retrieved-at |
| Rights | rights／license review status、usage constraint |

### 5.2 Physical separation

```text
public source artifacts / releases  -> immutable artifact storage
approved public search projection   -> PostgreSQL rag_public schema
formal personal/care data           -> PostgreSQL eldercare_ai via Core only
relationship projection             -> Neptune / Graph store
operational audit                    -> bounded logs / metrics / traces
```

`rag_public` 與 `eldercare_ai` 可位於同一 PostgreSQL instance，但必須使用不同 schema、role 與 query path；Agent Runtime 不因共用 instance 而取得 Core tables 的讀取權。禁止 public projection 與 private personal-data corpus 共用可自由檢索的 rows。若未來有 private semantic search 需求，需另立 Spec、Threat Model、retention／deletion design 與 ADR。

## 6. Query flows

### 6.1 Public information only

```text
Core Query Gate
  -> Planner: PUBLIC_KNOWLEDGE
  -> hybrid retrieval
  -> citation validation
  -> public-knowledge context
  -> grounded answer
```

### 6.2 Verified personal data + public explanation

```text
Core Query Gate
  -> Planner: CORE_DATA required, PUBLIC_KNOWLEDGE optional
  -> Core template query + public retrieval
  -> validate each source independently
  -> formal-data layer + public explanatory layer
  -> answer with distinct references
```

若 Core query 失敗，不得用 public knowledge 推測個人狀態。

### 6.3 Graph relationship query

```text
Core Query Gate
  -> Planner: GRAPH required or optional
  -> bounded traversal
  -> Core reauthorization
  -> graph evidence layer
  -> optional Core/public corroboration
  -> answer or typed no-data fallback
```

## 7. Reranker decision design

Reranker 不在 Phase 1 critical path。Phase 2 實驗需比較：

- no rewrite／no reranker baseline；
- bounded rewrite only；
- reranker only；
- rewrite + reranker。

Promotion gate 同時考量 Recall@5、NDCG@5、grounding、unsupported claims、filter correctness、p50／p95 latency、provider failure 與 cost/query。只提高 relevance 但破壞 filter、citation、latency 或 cost ceiling 的版本不得啟用。

## 8. Failure design

| Boundary | Failure | Result |
| --- | --- | --- |
| Query Gate | auth／consent／scope unknown | deny，zero retrieval calls |
| Planner | invalid／unknown／ceiling exceeded | deterministic fallback／`NONE` |
| Embedding | timeout／dimension mismatch | public retrieval unavailable；no partial lexical fallback unless policy explicitly allows |
| PostgreSQL retrieval | malformed batch／database error | discard batch；typed no-data／dependency result |
| Core tool | auth／version／query failure | no formal-data claim；other layers不得替代 |
| Graph | unavailable／lagging／cross-scope | discard graph layer；bounded fallback |
| Context | conflict／missing provenance | explicit conflict/no-data marker |
| Model／validator | unsupported／unsafe／citation mismatch | one bounded repair or safe fallback |

是否允許 embedding failure 時使用 BM25-only，必須由 evaluation 與 ADR／policy 明確決定；在決定前維持現行 fail-closed 行為。

## 9. Security design

- 所有 caller scope 由 server-side identity/context 取得。
- model input/output 與 retrieved text 都視為 untrusted content。
- tool call 數、query 長度、top-k、variants、hops、timeout 與 payload size 有硬上限。
- logs／metrics／traces 僅保存 bounded IDs、versions、reason codes 與 durations。
- unauthorized／nonexistent、cross-tenant／cross-elder、revoked consent、expired assignment 為必要 negative tests。
- projection deletion／tombstone 必須能重試、replay、rebuild，且不能 resurrection。

## 10. Observability

最小 telemetry：

- query gate decision／reason／policy version；
- planner route／confidence bucket／fallback／version；
- tool latency／status／hit count／rejection count；
- release／schema／embedding profile／fusion／reranker／graph projection versions；
- citation validation／unsupported claim／no-data outcome；
- cross-scope rejection、revocation、tombstone 與 provider failure counters；
- token／cost bucket，不記錄原始 Restricted Data payload。

## 11. Testing strategy

### Unit

- `RagChunkV2` validation與 deterministic mapping。
- QueryPlan schema、allowlists、ceilings、scope non-expansion。
- source-specific evidence validators、fusion、citation與conflict rules。
- Core／Graph query template registries與 input rejection。

### Property／negative

- 任意 client／model input 不能改 tenant／elder／purpose／audience filters。
- 任意 invalid batch 都不能產生 partial approved result。
- deleted／inactive／revoked records經 replay／rebuild不會復活。
- arbitrary SQL／Gremlin／DSL／unknown tool 永遠被拒絕。

### Integration

- candidate／approved release → mapper → PostgreSQL projection → verify receipt → activation／rollback。
- Agent Runtime → PostgreSQL hybrid retrieval with exact governance filters。
- Core request-bound identity → bounded tools → reauthorization。
- dependency timeout／malformed／lagging 的 source isolation與fallback。

### Evaluation

- 固定 dataset與版本；保存 per-case rank／citation／route evidence。
- 比較 baseline、rewrite、reranker與planner variants。
- 零容忍 gate獨立判斷，不與平均分數合併。

### Staging／release

- real provider、real PostgreSQL projection、real service identity、real region evidence。
- release rollback rehearsal、feature kill switch與incident runbook。
- cost、latency、availability、data-region與security approval。

## 12. Delivery phases

| Phase | Scope | Exit evidence |
| --- | --- | --- |
| 0 | Spec／ADR／requirements／design／tasks／traceability | 文件連結與 Current／Target audit |
| 1 | governed release、V2 PostgreSQL projection／embedding／online backend、activation、public retrieval evaluation／CI | signed release、verification receipt、smoke／eval、rollback evidence |
| 2 | bounded intent／entity／rewrite、optional reranker、official connectors | comparative eval、latency／cost evidence、feature flags |
| 3 | bounded planner、Core data tool、Graph tool、trust-layer context | contracts、negative security tests、route／graph gates、fallback evidence |
| 4 | production decision／rollout | owner approvals、staging E2E、region／security／SLO／cost、rollback rehearsal |

## 13. Open decisions

1. 726 candidates 的 review successor、source rights／license 與 accuracy owner。
2. approved release activation pointer／view、read-only role、connection pool、retention 與 rollback window。
3. embedding／model／reranker production providers、regions與 cost ceilings。
4. BM25-only emergency fallback 是否可在 embedding failure 時使用。
5. Phase 3 首批 Core query templates、Graph intents／edges／hop ceilings。
6. private projection retention、deletion SLA與 audit display policy。

未決事項一律使用安全 fallback，不以 model 推測補齊。
