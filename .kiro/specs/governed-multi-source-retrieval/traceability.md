# Governed Multi-Source Retrieval Traceability

- 更新日期：2026-08-24
- 文件狀態：Plan baseline verified；PostgreSQL storage／candidate projection `VERIFIED_LOCAL`
- Requirements：[requirements.md](requirements.md)
- Design：[design.md](design.md)
- Tasks：[tasks.md](tasks.md)

## 1. Status vocabulary

- `DOCUMENTED`：需求／設計／task 已建立，不代表程式已完成。
- `CURRENT_EVIDENCE`：已有 repository evidence，可描述為 Current。
- `NOT_STARTED`：尚無對應 implementation evidence。
- `BLOCKED`：有明確 owner decision、review、environment 或 release evidence blocker。
- `VERIFIED_LOCAL`／`VERIFIED_STAGING`：未來完成後，需附 command／artifact／version／date 才可使用。

## 2. Requirement matrix

| Req | Design sections | Tasks | Required evidence | Current status |
| --- | --- | --- | --- | --- |
| R1 Current／Target truth | 1, 2, 12 | 0.1-0.3 | Spec／ADR／Kiro docs；current repo evidence | `CURRENT_EVIDENCE` |
| R2 Governed source release | 4.1-4.3, 5.2 | 1.1, 1.2, 2.6, 4.4 | review outcomes、rights/version evidence、signed immutable release | `BLOCKED` — human review／owner decisions |
| R3 Canonical V2 projection | 4.4, 5.1 | 1.0A-1.5, 1.9 | embedding provider seam、mapping、mapper tests、projection manifest、private-data rejection | storage＋17／726 candidate projection `VERIFIED_LOCAL`；Google document embedding／approved release `NOT_STARTED` |
| R4 Versioned release／activation | 4.5, 5, 8 | 1.0B, 1.3-1.6, 4.3 | immutable release、verification receipt、activation／rollback evidence | schema／compatibility constraints `VERIFIED_LOCAL`；activation／rollback `NOT_STARTED` |
| R5 Public retrieval | 4.8, 6.1, 7 | 1.0, 1.7-1.9, 2.2-2.5 | provider-neutral backend seam、V2 runtime tests、filter/citation tests、retrieval eval | `CURRENT_EVIDENCE` for SearchBackend seam and V1-like staging baseline；V2 `NOT_STARTED` |
| R6 Bounded planning | 4.6, 4.7, 6 | 2.1-2.3, 3.1-3.3 | QueryPlan schema、scope non-expansion tests、route eval | `NOT_STARTED` |
| R7 Verified Core data tool | 4.9, 6.2 | 3.4, 3.5 | approved templates、Core authorization tests、contracts/verifier | `NOT_STARTED` |
| R8 Graph projection tool | 4.10, 6.3 | 3.6, 3.7 | projection policy、traversal tests、reauth／lag／resurrection evidence | `NOT_STARTED` |
| R9 Trust-layer grounding | 4.11-4.13, 6 | 1.7, 3.8, 3.9 | evidence validators、context／conflict tests、claim/citation eval | `CURRENT_EVIDENCE` for public citations only；multi-source `NOT_STARTED` |
| R10 Privacy／security | 5.2, 8, 9 | all phases；especially 1.0B-1.0C, 1.4, 3.1, 3.5, 3.7-3.10, 4.2 | threat/negative tests、restricted-data scans、revocation／scope evidence | `rag_public` schema／PUBLIC grant isolation `VERIFIED_LOCAL`；runtime role與multi-source boundaries `NOT_STARTED` |
| R11 Evaluation／observability／CI | 7, 10, 11 | 1.0B-1.0C, 1.8, 1.9, 2.3-2.5, 3.3, 3.10, 4.1-4.2 | versioned dataset、metrics、CI artifacts、real staging telemetry | pgvector CI configuration／local tests `VERIFIED_LOCAL`；GitHub run與retrieval eval `NOT_STARTED` |
| R12 Phased rollout | 12, 13 | 0.1-0.3, 1.6, 2.5, 3.3, 4.1-4.4 | flags、kill switch、approvals、staging/rollback evidence | plan `DOCUMENTED`; release `BLOCKED` |

## 3. Repository evidence ledger

以下 evidence 支持 Current baseline 或已標示的本機 foundation，不支持 online／Production completion：

| Evidence | Supports | Does not prove |
| --- | --- | --- |
| `data/rag-v2/candidates/v002`：17 sources、726 chunks | candidate corpus、V2 validation input | human review、approved release／activation、production accuracy |
| candidates：`needs_review`、`production_approved=false` | governance gate仍關閉 | production eligibility |
| `data/rag-manifest/AI_Reviewed_Embedding_Staging_Allowlist_v002.json` | 現行 staging allowlist與blocked status | owner-signed production allowlist |
| rag-ingestion validate／create／embed／ingest／verify／smoke commands | staging ingestion workflow與alias pattern | V2 projection mapper或production cutover |
| Bedrock Cohere Embed v4／1024 + OpenSearch BM25/KNN | current retrieval technology | query rewrite、reranker、multi-source planner |
| Agent Runtime `/api/v2/rag/retrievals`與request-bound service credential | current public RAG security seam | Core data／Graph tools |
| purpose／audience／governance filters與complete citation batch | current fail-closed public retrieval behavior | trust-layer multi-source context |
| local immutable evidence v008：242 rag-ingestion tests passed | local regression evidence | real AWS staging、availability、cost、region或production deployment |
| CDK staging desired count 0／model mock | deployment仍未啟用的證據 | runnable staging／production readiness |
| `20260824_1200_add_public_rag_pgvector_projection.py` + full Core integration suite：111 passed（2026-08-24，本機 disposable PostgreSQL 16／pgvector） | `rag_public` schema、extensions、constraints、indexes、roundtrip與既有 DB regression | shared／remote DB migration、online retrieval、production role grants |
| `project_postgres.py dry-run` 與 disposable DB import／rerun：17 sources／726 chunks、candidate SHA `bab68588963be5b47c7058f9cb9b5c0fd87181087316c262c9faefea6d5bedec`；rerun `inserted=0`／`existing=726`、embedding 0 | canonical candidate 可決定性驗證並 idempotent staging projection | shared／remote DB import、human review、approved release、Google embedding |
| full Core unit suite 898 passed；其中 importer tests 驗證 tamper／allowlist mismatch／production promotion rejection | candidate staging projection behavior與既有 unit regression | production import、runtime cutover、retrieval quality |

## 4. Target evidence checklist

### Phase 1 exit

- [x] PostgreSQL `rag_public` migration、pgvector／pg_trgm、FTS／trigram／HNSW與schema isolation（local）
- [x] Canonical 17／726 candidate dry-run與atomic／idempotent staging projection importer（local）
- [ ] Google `RETRIEVAL_DOCUMENT` corpus embedding與compatibility receipt
- [ ] Per-source／per-chunk human review outcomes
- [ ] Rights／license、source accuracy與version decisions
- [ ] Owner-signed immutable approved release + independent expected hash
- [ ] Approved-release mapper extension與signed-release tests
- [ ] Approved versioned release與complete projection／embedding receipt
- [ ] V2 runtime retrieval integration與negative tests
- [ ] Recall@5／NDCG@5／filter／grounding／unsupported/no-data evidence
- [ ] Release activation與rollback rehearsal
- [ ] CI artifacts與real staging smoke evidence

### Phase 2 exit

- [ ] Intent／entity taxonomy與ambiguous/injection dataset
- [ ] Bounded rewrite implementation與baseline comparison
- [ ] Reranker experiment with pre/post rank evidence
- [ ] Promotion/rejection decision including latency／cost／failure
- [ ] Connector snapshot／hash／rights／candidate-only evidence

### Phase 3 exit

- [ ] ApprovedQueryScope與Core Query Gate negative tests
- [ ] Bounded QueryPlan schema／validator／route accuracy
- [ ] Approved Core query templates與minimal-data review
- [ ] Core tool contracts、tests與live verifier
- [ ] Approved Graph intents／edges／hops／freshness policy
- [ ] Graph tool reauthorization、lag、fallback與resurrection tests
- [ ] Trust-layer context、conflict與source-isolation tests
- [ ] Claim／citation／restricted-data validation
- [ ] Multi-source E2E與zero cross-elder／inactive retrieval evidence

### Phase 4 exit

- [ ] Runnable target staging with real providers／service identities
- [ ] Security／Privacy／Region approvals
- [ ] Availability／latency／rate／cost gates
- [ ] Feature flags／kill switches／incident runbook
- [ ] Rollout／rollback rehearsal
- [ ] Product／Architecture／Security／Data Governance／Operations sign-off

## 5. Quality gate mapping

| Metric／invariant | Requirement | Phase | Release behavior |
| --- | --- | --- | --- |
| Recall@5 `>= 0.85` | R11 | 1+ | below gate blocks changed retrieval variant |
| NDCG@5 `>= 0.80` | R11 | 1+ | below gate blocks changed retrieval variant |
| Metadata Filter Pass Rate `100%` | R5, R10, R11 | all | any failure blocks rollout |
| expired／needs_review authoritative answer `0` | R2, R5, R9, R11 | all | any failure blocks rollout |
| Grounded Answer Rate `>= 95%` | R9, R11 | 1+ | below gate blocks rollout |
| Unsupported Claim Rate `<= 2%` | R9-R11 | 1+ | above gate blocks rollout |
| no-data correctness `>= 95%` | R5, R9, R11 | 1+ | below gate blocks rollout |
| Query Intent Route Accuracy `>= 90%` | R6, R11 | 3 | planner remains disabled below gate |
| Relevant Node／Edge Recall `>= 90%` | R8, R11 | 3 | graph tool remains disabled below gate |
| Cross-Elder Node Rate `0` | R8, R10, R11 | 3 | any failure blocks rollout |
| Deleted／Inactive Retrieval `0` | R8, R10, R11 | 3 | any failure blocks rollout |
| Graph projection p95 lag `<= 60s` | R8, R11 | 3 | stale graph layer excluded／rollout blocked |
| Graph failure fallback `100%` | R8-R11 | 3 | graph tool remains disabled below gate |

## 6. Open blockers

| Blocker | Required owner／input | Safe fallback |
| --- | --- | --- |
| 726 candidates 尚未完成 production review | Data Governance／Product／domain reviewers | 保持 candidate、`production_approved=false` |
| source rights／license／accuracy／version 未簽核 | Legal／Data Governance／Product | 不建立 production release |
| Approved release activation／rollback與PostgreSQL online backend 尚未實作 | Search／Agent Runtime owners | 現行 staging-only adapter與NO_DATA／fail-closed behavior |
| Google query adapter 已完成，但 document embedding／corpus rebuild、model／region／data policy／cost evidence 未完成 | Product／ML／Architecture／Security | Google query path 保持 opt-in，不查詢 Cohere corpus、不混用向量 |
| reranker provider／value／cost未知 | Product／ML／Architecture | 保持baseline hybrid ranking |
| Core query templates未批准 | Domain／Security／Privacy | 不提供structured data tool |
| Graph intents／edges／hops未批准 | Domain／Architecture／Security | 不提供graph tool |
| real staging／region／SLO／cost evidence缺失 | Operations／Security／Architecture | 不宣稱production ready |

## 7. Documentation linkage

- Product outcome and phases：[Spec 20](<../../../docs/spec/20智慧長照 AI 陪伴系統－治理式多來源 Retrieval 與 RAG 演進 v0.1.md>)
- Architectural decisions and alternatives：[ADR 0017](../../../docs/adr/0017-bounded-multi-source-retrieval-planner.md)、[ADR 0018](../../../docs/adr/0018-postgresql-pgvector-public-knowledge-retrieval.md)
- Test and metric authority：Spec 11
- Query type／planner constraints：Spec 09、Spec 10
- AWS store／authority boundary：Spec 08

未來每個完成 task 都必須在本表補上 commit／command／artifact／date 或其他可重現 evidence；只勾選 task 不構成驗收。
