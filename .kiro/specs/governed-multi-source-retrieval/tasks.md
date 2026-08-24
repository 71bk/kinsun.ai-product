# Implementation Plan: Governed Multi-Source Retrieval

- 狀態：In progress — PostgreSQL storage foundation verified locally
- 日期：2026-08-24
- Requirements：[requirements.md](requirements.md)
- Design：[design.md](design.md)
- Traceability：[traceability.md](traceability.md)

## Status rules

- `[x]` 只代表已有可定位 evidence 的完成項目。
- `[ ]` 代表尚未完成；即使 Target design 已寫入文件，也不代表程式已存在。
- 新 endpoint／event／tool／schema 只有在 implementation、tests、examples 與 verifier 同步後才可加入 executable `contracts/`。
- 所有 phase 均需保留 Current／Target 區隔與 production release blockers。

## Phase 0 — Architecture baseline

- [x] 0.1 記錄 Current／Target、非目標、分期與 release blockers
  - Evidence: [Spec 20](<../../../docs/spec/20智慧長照 AI 陪伴系統－治理式多來源 Retrieval 與 RAG 演進 v0.1.md>)
  - _Requirements: R1, R12_

- [x] 0.2 記錄 bounded multi-source planner 決策與 alternatives
  - Evidence: [ADR 0017](../../../docs/adr/0017-bounded-multi-source-retrieval-planner.md)、[ADR 0018](../../../docs/adr/0018-postgresql-pgvector-public-knowledge-retrieval.md)
  - _Requirements: R1, R6, R10, R12_

- [x] 0.3 建立 requirements、design、tasks 與 traceability 文件
  - Evidence: 本目錄四份文件
  - _Requirements: R1-R12_

## Phase 1 — Governed RagChunkV2 data plane

- [x] 1.0 建立 provider-neutral SearchBackend seam
  - Retriever 只接收 bounded `HybridSearchPlan` 與 provider-neutral `SearchHit`，不依賴 OpenSearch class。
  - OpenSearch adapter 在邊界內把 plan 編譯成 DSL；plan 本身不含 executable DSL。
  - 現行 runtime factory 仍只組裝 OpenSearch search backend；PostgreSQL backend 尚未實作。
  - Evidence: `services/agent-runtime/src/agent_runtime/rag/search_backend.py`、targeted unit tests
  - _Requirements: R1, R5, R6, R10, R12_

- [x] 1.0A 建立 provider-neutral EmbeddingProvider 與 Google query adapter
  - Google query adapter 使用原生 Google Gen AI SDK、`RETRIEVAL_QUERY` 與固定 1024 dimensions。
  - API key 只由 runtime secret 注入，不進 config model／log；provider error、malformed response 與 dimension mismatch fail closed。
  - Agent Runtime 使用獨立 `RAG_QUERY_EMBEDDING_CONFIG_PATH`，不改動 ingestion 共用 embedding config。
  - Evidence: `services/agent-runtime/src/agent_runtime/rag/query_embedder.py`、`config/rag/embedding-google.yaml`、unit/integration tests
  - _Requirements: R3, R5, R10-R12_

- [x] 1.0B 建立 PostgreSQL／pgvector public projection storage foundation
  - Alembic 建立隔離的 `rag_public` schema、release／chunk／embedding profile／embedding／ingestion receipt tables。
  - lexical baseline 使用 generated `tsvector`、`pg_trgm` GIN；vector 使用固定 `vector(1024)` 與 HNSW cosine。
  - extensions 明確位於 `public` schema；`rag_public` 撤銷 `PUBLIC` 權限，不授予 Agent Runtime `eldercare_ai` 存取權。
  - CI PostgreSQL service 使用 immutable pgvector image digest；migration roundtrip、constraints、indexes 與 extension namespace 已通過本機 integration tests。
  - Evidence: `services/core-api/alembic/versions/20260824_1200_add_public_rag_pgvector_projection.py`、`services/core-api/tests/integration/test_migrations.py`、`.github/workflows/gate1.yml`
  - _Requirements: R3, R4, R10, R11_

- [x] 1.0C 實作 deterministic 17／726 candidate projection importer
  - 嚴格驗證 canonical checksum inventory、JSON duplicate keys、JSON Schema、source／chunk manifests、exact allowlist identity／hash 與 counts。
  - 單一 transaction 寫入 versioned staging release／chunks／ingestion receipt；重跑 idempotent，既有 row digest 不符時整批 fail closed。
  - candidate 保持 `production_approved=false`，不建立 embedding rows；CLI `dry-run` 已納入 CI，`import` 需獨立 expected SHA 且拒絕 production environment。
  - Evidence: `services/core-api/app/rag_projection_importer.py`、`scripts/rag/project_postgres.py`、unit／integration tests
  - _Requirements: R1-R4, R10, R11_

- [ ] 1.0D 實作 Google document embedding、corpus rebuild 與相容性 gate
  - ingestion 使用 `RETRIEVAL_DOCUMENT`，並與 query adapter使用同一 model、dimension 與version。
  - 切換 provider 時重建全部 embedding，不混用 Bedrock／Google 向量。
  - 完成 model／API surface／region／data policy／cost evidence 與 retrieval evaluation。
  - provider error、dimension mismatch 或設定缺失維持 fail closed，不 fallback 到 mock。
  - **Dependencies:** Tasks 1.0A-1.0C、Google provider decision、evaluation dataset
  - _Requirements: R3, R5, R10-R12_

- [ ] 1.1 決定並執行 candidate human-review successor
  - 指定 source accuracy、rights／license、version 與 chunk reviewers／owners。
  - 對 17 sources／726 candidates 產生逐來源與逐 chunk outcome。
  - 未通過資料需 reject、修正或 supersede，不得直接沿用 candidate status。
  - **Dependencies:** Owner decision
  - _Requirements: R2, R10, R12_

- [ ] 1.2 建立 immutable approved release builder
  - 產生 signed release manifest、獨立 expected hash、source／chunk counts 與 review summary。
  - 驗證 candidate input、source snapshot、citation locator、rights 與 current／expiry metadata。
  - 測試 hash／count／signature／review 缺失時整批 fail closed。
  - **Dependencies:** Task 1.1
  - _Requirements: R2, R3, R10_

- [ ] 1.3 完成 approved-release activation model 與 mapper versioning
  - 在既有 `rag_public` foundation 上定義 approved release、active pointer／view、verification status 與 rollback evidence。
  - 明確定義 required／optional／derived fields、normalization、rejection 與 version transition rules。
  - 記錄 embedding profile、projection、schema、release 與 activation versions。
  - **Dependencies:** Task 1.2
  - _Requirements: R3, R4_

- [ ] 1.4 將 V2 Projection Mapper 擴充到 approved release
  - 以 signed canonical V2 release 為唯一 production projection input；candidate path 不可自行升格。
  - 產生 deterministic row IDs、metadata、digests、embedding receipts 與 projection manifest。
  - invalid item、duplicate identity、hash mismatch 或 private-data field 使整批失敗。
  - 加入 unit、property、negative 與 fixture tests。
  - **Dependencies:** Tasks 1.0C, 1.0D, 1.2, 1.3
  - _Requirements: R3, R10, R11_

- [ ] 1.5 實作 PostgreSQL lexical + vector hybrid `SearchBackend`
  - 使用固定、參數化 SQL template 查詢同一 approved release 的 FTS／trigram 與 1024-dimension pgvector KNN，再做版本化 fusion。
  - 驗證 embedding profile／dimension incompatibility、exact governance filters、timeouts 與 bounded top-k。
  - 使用只讀 `rag_public` role；不得讀取 private Core／CRM／event tables，也不接受 LLM 產生 SQL。
  - **Dependencies:** Tasks 1.0B, 1.0D, 1.3
  - _Requirements: R3, R4, R10_

- [ ] 1.6 實作 rebuild、verification receipt、release activation 與 rollback
  - 維持 validate／create／embed／ingest／verify／smoke 的明確階段。
  - receipt涵蓋 exact release hash、count、record hashes、schema、embedding profile／dimension、filters與citations。
  - 只有完整 verified receipt可 activation；保留 prior release與rollback rehearsal evidence。
  - **Dependencies:** Tasks 1.4, 1.5
  - _Requirements: R4, R10, R12_

- [ ] 1.7 將 Runtime retrieval adapter 接到 V2 projection
  - 保留 request-bound service credential、purpose／audience mapping與現有 fail-closed batch semantics。
  - 驗證 3–5 complete cited chunks、malformed/no-data/provider-failure paths。
  - 更新 implementation docs；只在 code／tests／verifier完成後更新 contracts。
  - **Dependencies:** Task 1.6
  - _Requirements: R4, R5, R9, R10_

- [ ] 1.8 建立 public retrieval evaluation baseline
  - 版本化 natural-language、legal、no-data、expired、needs-review、wrong-audience／purpose與injection dataset。
  - 保存 per-query ranks、scores、filters、citations、versions與failure outcomes。
  - 驗證 Recall@5、NDCG@5、metadata、grounding、unsupported claim與no-data gates。
  - **Dependencies:** Task 1.7
  - _Requirements: R5, R9, R11_

- [ ] 1.9 納入 Phase 1 CI gate
  - Storage foundation 已納入 pgvector migration integration tests、canonical dry-run 與 importer idempotency tests。
  - 待補 mapper／manifest／hash／filter／citation tests與固定 retrieval evaluation subset。
  - full evaluation與staging smoke輸出可下載 evidence artifact。
  - 零容忍 gate失敗必須阻擋 merge／rollout。
  - **Dependencies:** Tasks 1.4, 1.7, 1.8
  - _Requirements: R3, R4, R5, R10, R11_

## Phase 2 — Query understanding and retrieval quality

- [ ] 2.1 建立 bounded query intent／entity taxonomy
  - 對齊 `EXACT_TRANSACTIONAL`、`KEYWORD`、`VECTOR`、`GRAPH`、`HYBRID`、`NONE`。
  - 定義 allowlisted intents、entities、purposes、audiences與low-confidence fallback。
  - 建立 ambiguous、injection、cross-purpose與no-data fixtures。
  - **Dependencies:** Task 1.8
  - _Requirements: R5, R6, R10, R11_

- [ ] 2.2 實作 bounded normalization／rewrite
  - 限制 query length、variant count、language、timeout與total retrieval calls。
  - 任何 variant使用相同server-derived filters，保存original/variant/version。
  - invalid／unsafe rewrite回到original query或`NONE`。
  - **Dependencies:** Task 2.1
  - _Requirements: R5, R6, R10_

- [ ] 2.3 評估 rewrite quality
  - 與Phase 1 baseline比較retrieval、grounding、latency、provider failure與cost。
  - 未達gate保持feature flag關閉。
  - **Dependencies:** Task 2.2
  - _Requirements: R11, R12_

- [ ] 2.4 實作 feature-flagged reranker experiment
  - 保存pre/post ranks、scores、model/version與citation identity。
  - reranker不得接收或改寫authorization/governance filters。
  - provider failure回到已驗證的baseline ranking或typed no-data，依批准policy決定。
  - **Dependencies:** Tasks 1.8, 2.3
  - _Requirements: R5, R9, R10, R11, R12_

- [ ] 2.5 作成 reranker promotion／rejection decision
  - 比較no-rewrite/no-rerank、rewrite-only、rerank-only、combined variants。
  - 同時驗證quality、p50/p95 latency、cost/query、failure與zero-tolerance gates。
  - 以ADR或decision record記錄結果；未證明改善時維持關閉。
  - **Dependencies:** Task 2.4
  - _Requirements: R11, R12_

- [ ] 2.6 建立官方 PDF／Web versioned connectors
  - allowlisted domains、snapshot、robots／rights review、hash與change detection。
  - connector只產生candidate，不跳過human review/release。
  - **Dependencies:** Tasks 1.1-1.4
  - _Requirements: R2, R3, R10_

## Phase 3 — Bounded multi-source retrieval

- [ ] 3.1 定義 `ApprovedQueryScope` 與 Core Query Gate seam
  - 對齊service／actor／tenant／elder／assignment／relationship／consent／purpose／role／policy。
  - 定義deny、revocation、expired assignment與unauthorized/nonexistent equivalence。
  - 加入request-bound、replay、cross-tenant與cross-elder tests。
  - **Dependencies:** Phase 1
  - _Requirements: R6, R10_

- [ ] 3.2 定義並實作 bounded `QueryPlan`
  - schema只含allowlisted fields，不含SQL／Gremlin／provider-specific search DSL。
  - limits涵蓋tools、top-k、variants、hops、timeout與total calls。
  - 建立deterministic baseline planner與output validator，再決定是否加入LLM classifier。
  - **Dependencies:** Tasks 2.1, 3.1
  - _Requirements: R6, R10, R11_

- [ ] 3.3 實作 planner route evaluation與feature control
  - 評估intent route accuracy、unknown／low-confidence、fallback與injection cases。
  - server-side feature flag、allowlisted cohort、kill switch與version telemetry。
  - **Dependencies:** Task 3.2
  - _Requirements: R6, R11, R12_

- [ ] 3.4 決定首批 Verified Core Data query templates
  - 為每個intent定義purpose、roles、required consent、inputs、minimal fields、row limit、timeout與record references。
  - 完成Privacy/Security review；不得提供自由SQL。
  - **Dependencies:** Tasks 3.1, 3.2, Owner decision
  - _Requirements: R7, R10, R12_

- [ ] 3.5 實作 Verified Core Data Tool
  - Core注入scope並重新授權；Runtime/Planner不能override。
  - 回傳typed result、formal record IDs/versions/status與bounded provenance。
  - 加入authorization、consent、cross-scope、version、timeout與data-minimization tests。
  - 實作完成後同步contracts/examples/live verifier。
  - **Dependencies:** Task 3.4
  - _Requirements: R7, R9, R10, R11_

- [ ] 3.6 決定首批 Graph intents與projection policy
  - 定義node／edge allowlist、direction、filters、max hops、result limit、freshness與tombstone policy。
  - 指定source formal entities、projection version與lag SLO。
  - **Dependencies:** Tasks 3.1, 3.2, Owner decision
  - _Requirements: R8, R10, R12_

- [ ] 3.7 實作 read-only Graph Projection Tool
  - 使用固定traversal templates，不接受自由Gremlin。
  - Core reauthorize所有result，移除cross-scope／deleted／inactive／stale evidence。
  - 加入duplicate、out-of-order、replay、restore、lag、unavailable與resurrection tests。
  - 實作完成後同步contracts/examples/live verifier。
  - **Dependencies:** Task 3.6
  - _Requirements: R8, R9, R10, R11_

- [ ] 3.8 實作 source-specific Evidence Validators與Trust-Layer Context Builder
  - 分開驗證Core、Graph、Public evidence，不做單一score盲目fusion。
  - 定義conflict、missing、expiry、freshness、source-unavailable與formal-state priority。
  - 保留citation／record reference與所有必要versions。
  - **Dependencies:** Tasks 3.5, 3.7
  - _Requirements: R9, R10_

- [ ] 3.9 實作 grounded answer／citation／restricted-data validator
  - 驗證claim-evidence mapping、citation completeness、conflicts與unsafe content。
  - 最多一次bounded repair；失敗使用safe fallback。
  - 加入public injection、private leakage、unsupported claim與citation mismatch tests。
  - **Dependencies:** Task 3.8
  - _Requirements: R9, R10, R11_

- [ ] 3.10 建立 multi-source E2E與failure matrix
  - public-only、Core+public、Graph+Core、all-source、no-data與conflict flows。
  - graph/core/search/model timeout、malformed、lagging與revocation during request。
  - 驗證route accuracy、graph recall、cross-elder=0、inactive=0、fallback=100%。
  - **Dependencies:** Tasks 3.3, 3.5, 3.7-3.9
  - _Requirements: R6-R12_

## Phase 4 — Release readiness

- [ ] 4.1 完成 staging deployment與real-provider evidence
  - 部署可實際服務的staging tasks，不以`desiredCount=0`或mock model代替。
  - 使用real service identity、PostgreSQL release、model／embedding／reranker與Graph/Core endpoints。
  - _Requirements: R10, R11, R12_

- [ ] 4.2 驗證 Security／Privacy／Region／SLO／Cost gates
  - threat model、data flow、retention/deletion、region、availability、latency、rate limit與cost ceiling。
  - 完成unauthorized、enumeration、prompt injection、data exfiltration與dependency abuse tests。
  - _Requirements: R10-R12_

- [ ] 4.3 完成 rollout、kill switch與rollback rehearsal
  - release rollback、feature flags、provider fallback、incident runbook與owner contacts。
  - 保存演練時間、版本、結果與未解風險。
  - _Requirements: R4, R10, R12_

- [ ] 4.4 取得 owner approvals並作成production release decision
  - Product、Architecture、Security、Data Governance與Operations owner簽核。
  - 未通過時維持staging-only/public-knowledge-only/fail-closed。
  - _Requirements: R2, R10-R12_

## Completion rule

只有 Phase 1 可視為「governed public knowledge RAG data plane 完成」；Phase 1 不代表 multi-source RAG 完成。只有 Phase 3 全部完成且達成 traceability gates，才可描述為「bounded multi-source retrieval implemented」。Production readiness 還必須另外完成 Phase 4，兩者不可混用。
