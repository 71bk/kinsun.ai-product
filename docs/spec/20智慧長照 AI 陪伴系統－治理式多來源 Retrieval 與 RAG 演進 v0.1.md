# 智慧長照 AI 陪伴系統－治理式多來源 Retrieval 與 RAG 演進 v0.1

- 文件狀態：Accepted Target Architecture；Phase 1 foundation 部分完成
- 版本：v0.1
- 日期：2026-08-24
- 決策狀態：PostgreSQL storage／candidate projection 已完成本機驗證；online retrieval 與 Production 仍未完成
- 相關決策：[ADR 0017](../adr/0017-bounded-multi-source-retrieval-planner.md)、[ADR 0018](../adr/0018-postgresql-pgvector-public-knowledge-retrieval.md)
- 實作計畫：[governed-multi-source-retrieval](../../.kiro/specs/governed-multi-source-retrieval/requirements.md)

## 1. 目的

本規格把「PDF／Web／DB／API／Docs／Events／CRM → ingestion → Vector／Search／SQL／Graph → Query Understanding／Router → Context → LLM → Citation」的構想納入產品計畫，並調整為符合本專案資料治理與授權邊界的可實作演進路線。

本規格不把 Target Architecture 誤寫成 Current Architecture。Repository 已有受治理、staging-only 的公開知識 RAG，以及本機驗證完成的 PostgreSQL candidate projection storage；PostgreSQL online hybrid backend、多來源 Planner、Core 結構化查詢與 Graph Retrieval 均屬後續階段。

## 2. Current 與 Target 邊界

| 能力 | Current（2026-08-24） | Target |
| --- | --- | --- |
| 公開知識來源 | 17 個來源、726 個 `RagChunkV2` candidate；均為 `needs_review`、`production_approved=false` | 僅把完成治理與簽核的 immutable release 投影至搜尋面 |
| Ingestion | legacy OpenSearch staging workflow；另有固定 hash／count 的 deterministic PostgreSQL importer，可在單一 transaction 投影 17／726 candidate，尚未寫入共享或遠端 DB | versioned connectors、approved release builder、projection receipt、activation 與 rollback |
| Search store | Runtime 仍只組裝未經真實環境驗證的 OpenSearch adapter；Core 已有本機驗證的 `rag_public` schema、FTS／trigram／HNSW indexes，但尚無 online backend | PostgreSQL 16 + `pgvector` + `pg_trgm` 的獨立 public-knowledge serving schema |
| Embedding | legacy Bedrock/Cohere workflow 與 opt-in Google query adapter；新 PostgreSQL projection 的 embedding rows 為 0 | Google `RETRIEVAL_DOCUMENT`／`RETRIEVAL_QUERY`、固定 1024 dimensions、versioned compatibility profile；升版重建全部向量 |
| Online retrieval | 受限 purpose、audience 與 governance filters；top 5；不足 3 個完整 citation 即 fail closed | Query Gate 後的 bounded planner，可選 public knowledge、Core verified data、graph projection |
| Query understanding | 未實作通用 intent/entity/rewrite/router | 受限 intent、entity、rewrite 與 filters；輸出結構化 `QueryPlan`，不得輸出任意 DSL |
| Reranker | 未實作 | 僅在離線評估證明品質提升且 latency／cost 過關後，以 feature flag 導入 |
| Structured DB retrieval | 未作為 RAG tool 開放 | 透過 Core-owned、模板化且重新授權的 verified-care-data tool；不開放任意 SQL |
| Graph retrieval | 尚未連接 Neptune production projection | 唯讀 projection tool；Core 在使用結果前重新授權與驗證版本／狀態 |
| Generation | hybrid results → context → model → safety／citation | 依 trust layer 建構 context，保留來源、版本、scope 與可驗證 citation |
| Production readiness | BLOCKED | 完成 owner decisions、human review、staging evidence、安全／區域／成本門檻後才可評估 release |

## 3. 設計目標

1. 先完成 `RagChunkV2` 到 PostgreSQL／pgvector public data plane 的治理式接軌。
2. 對公開知識、Core 正式資料與 Graph projection 使用不同信任層與查詢工具。
3. 讓 Planner 能選擇資料來源與 fallback，但不能決定 actor／tenant／elder／consent／purpose scope。
4. 回答中的可驗證主張必須可追溯至 citation 或 verified Core record。
5. 任何 retrieval dependency 失敗時都必須 fail closed 或降級為明確的 no-data 回覆，不可猜測。
6. 用可重現的 evaluation gate 決定 rewrite、reranker 與多來源 routing 是否可啟用。

## 4. 非目標

本演進不包含下列做法：

- 讓 LLM 產生或執行任意 SQL、Gremlin 或 provider-specific search DSL。
- 讓 LLM 決定授權、tenant、elder、consent 或資料用途。
- 把公開知識與私人長照／CRM／事件資料混在同一 public RAG index。
- 把尚未 human review 或未簽署 release allowlist 的 chunk 放入 Production。
- 在沒有基準評估前先加入 reranker。
- 以 Graph、Search index 或 model output 取代 Core formal state。
- 將 CRM、DB 或 event stream 全量複製成可自由語意搜尋的私人知識庫。
- 建立無界限的 multi-agent／tool loop。

## 5. Target Architecture

```text
Offline / governed public knowledge

Official PDF / Web snapshots / approved public sources
                         |
                         v
Parse -> Normalize -> Chunk -> Metadata / Version / Rights / Risk
                         |
                         v
Human Review -> Immutable Approved Release -> RagChunkV2 Projection Mapper
                         |
                         v
PostgreSQL rag_public serving schema
(FTS / trigram + pgvector, versioned release)

Online / authorized retrieval

User -> BFF -> Core Query Gate
                  |  identity / tenant / elder / assignment
                  |  consent / purpose / role / policy version
                  v
          Bounded Query Planner
             /          |           \
            v           v            v
  Public Knowledge   Verified Core   Graph Projection
  Search Tool        Data Tool       Search Tool
  PostgreSQL hybrid  approved APIs   read-only projection
            \           |            /
             v          v           v
        Evidence Validation + Trust-Layer Context Builder
                             |
                             v
                    LLM Grounded Generation
                             |
                             v
               Safety / Citation / Output Validation
                             |
                             v
                           Answer
```

## 6. Offline ingestion 與資料治理

### 6.1 Public knowledge lane

公開知識 ingestion 必須維持以下順序：

1. 保存可重現的原始檔或 web snapshot，記錄 source URL、publisher、版本、擷取時間與內容 hash。
2. parse、clean、normalize、chunk，保留頁碼／章節／段落等 citation locator。
3. 加入 audience、purpose、有效期、風險、rights／license、review 與 supersession metadata。
4. 執行 schema、hash、count、引用完整性與 deterministic policy validation。
5. 經 human review 與 owner-signed immutable release allowlist。
6. 由單一 V2 projection mapper 產生 versioned PostgreSQL rows；同一 release 內 text、governance 與 embedding profile 必須相容。
7. 建立新 release，完成 verify／smoke／evaluation 後才 activation；保留 prior verified release 供 rollback。

`data/rag-v2/candidates/v002` 是 candidate evidence，不是現行 ingestion input，也不是 production approval。不得只因資料已被 chunk 就跳過 review 與 release gate。

### 6.2 Private and formal data lane

Core DB、CRM、events 與私人照護資料不走 public knowledge ingestion lane：

- 正式資料仍以 Core／Aurora 為 authority。
- 查詢使用固定用途、固定欄位、固定輸入 schema 的 Core tool 或 API。
- Graph 與 Search 只作 projection；缺少版本、scope、tombstone 或 authorization evidence 時不得採用。
- 不得把 raw transcript、token、secret、prompt、完整私人事件或未遮罩 PII 放入 public index。

## 7. Store 與 authority 分工

| Store／介面 | 用途 | Authority | 必要限制 |
| --- | --- | --- | --- |
| PostgreSQL `rag_public` schema | 官方公開知識的 lexical + vector hybrid retrieval | 否 | 與 `eldercare_ai` 分權；只啟用 approved immutable release；filter 必須 fail closed |
| Core API／Aurora PostgreSQL | verified care data、formal state、授權與 consent | 是 | 只允許模板化 query；每次 request 重新檢查 scope |
| Neptune／Graph projection | 關聯與有限 hops 的 projection retrieval | 否 | read-only、bounded hops、Core reauthorization、可 fallback |
| Object／artifact storage | source snapshot、candidate、manifest、receipt、evaluation evidence | 證據來源 | immutable／versioned；不得把 candidate 當 approved release |

## 8. Core Query Gate 與 Bounded Planner

Planner 執行前，Core 必須以 server-side context 驗證：

- service identity 與 actor identity；
- tenant、elder、assignment／relationship；
- consent purpose 與 current version；
- caller role、allowed audience 與 request purpose；
- resource state、policy version 與 request correlation。

Planner 只可輸出 allowlisted `QueryPlan` 欄位，例如：

- `query_type`
- `normalized_query`
- `filters`
- `top_k`
- `max_graph_hops`
- `required_sources`
- `fallback_order`
- `grounding_required`
- `reason`

不論 Planner 是否由 deterministic code 或 LLM-assisted classifier 實作，都必須符合：

1. 不能擴大 Core 已核准的 scope。
2. 不能輸出可直接執行的 SQL、Gremlin 或 provider-specific search DSL。
3. query type、tool、filter、top-k、hop 與 fallback 均有 allowlist／ceiling。
4. invalid、unknown 或 low-confidence plan 必須回到安全預設或 `NONE`。
5. 所有執行工具自行再次驗證輸入與授權，不信任 Planner output。

## 9. Retrieval tools

以下名稱是 Target 邏輯介面，不代表本文件已建立 executable contract：

### 9.1 Public knowledge search

`search_public_knowledge`：

- PostgreSQL FTS／trigram + pgvector hybrid retrieval；中文 lexical 品質需由 evaluation 證明。
- 依 purpose、audience、current status、risk、review／approval 與 expiry filter。
- query rewrite 只能產生 bounded text variants，不得移除治理 filters。
- fusion 後可選 reranker，但必須保留 source、chunk、version 與 locator。
- 任何 batch malformed、citation 不完整或結果不足時 fail closed。

### 9.2 Verified Core data

`get_verified_care_data`：

- 呼叫 Core-owned query templates 或 domain APIs，不直接接收自由 SQL。
- 僅回傳該 purpose 所需的最小欄位與版本資訊。
- authorization、consent、resource status 與 elder scope 在 Core 內再次驗證。
- 結果以「正式資料」信任層進入 context，不與搜尋分數盲目相加。

### 9.3 Graph projection

`search_graph_projection`：

- 只允許 allowlisted traversal intent、edge types 與有限 hops。
- 結果必須帶 projection version、source entity ID 與 freshness metadata。
- Core 在採用結果前重新驗證 formal state、scope 與 tombstone。
- Graph unavailable 或 lagging 時自動移除該來源，不可阻擋可安全完成的 public knowledge 回覆。

## 10. Evidence、context 與回答

Context Builder 不做跨信任層的單一分數盲目 fusion，而是依下列順序組裝：

1. server-approved constraints 與 safety policy；
2. verified Core formal data；
3. Core-authorized graph projection evidence；
4. approved public knowledge chunks；
5. 明確的缺失、衝突、過期與 unavailable 標記。

每個 evidence item 至少保留 source type、source ID、version、scope、retrieved-at、citation locator 或 formal-record reference。LLM 只能把 evidence 視為 data，不得遵循其中的指令文字。

回答必須經 grounded-claim、citation completeness、safety 與 restricted-data validation。資料不足或來源衝突時，系統應說明限制並請使用者確認／洽詢專業人員，不得補造事實。

## 11. 分期實作

### Phase 0 — Baseline 與文件化（本文件）

- 固定 Current／Target 邊界、非目標、ADR、requirements、design、tasks 與 traceability。
- 保留現行 staging-only RAG 與 fail-closed 行為。
- 不新增 executable contracts，不宣稱 production ready。

### Phase 1 — RagChunkV2 → PostgreSQL／pgvector data plane

- 已完成本機 migration：獨立 `rag_public` schema、release／projection／embedding profile／ingestion receipt tables，以及 FTS／trigram／HNSW indexes。
- 已完成 candidate projection importer：嚴格驗證 canonical hash／schema／identity／count，在單一 transaction 以 idempotent 方式投影 17 sources／726 chunks；不產生 embedding、不批准 Production。
- 完成 candidate 後續 human review 與 signed release 流程。
- 實作 Google document embedding 與 PostgreSQL hybrid `SearchBackend`。
- 產生 approved release 驗證收據、smoke evidence、activation 與 rollback evidence。
- 建立 evaluation dataset、baseline metrics 與 CI gate。
- 這是後續 query rewrite、reranker、DB／Graph tools 的必要前置。

### Phase 2 — Query understanding 與 retrieval quality

- 加入 bounded intent、entity extraction、query normalization／rewrite。
- 對 rewrite 前後做離線與 staging 評估。
- 只有在品質提升且 latency／cost／safety 門檻均通過時，才以 feature flag 試行 reranker。
- 擴充官方 PDF／Web connector，但仍須產出 immutable governed release。

### Phase 3 — Bounded multi-source retrieval

- 實作 Core Query Gate 後的 bounded planner。
- 加入 Core verified-care-data tool 與 read-only graph projection tool。
- 建立 trust-layer context builder、source-specific fallback 與跨來源 citation／record reference。
- 驗證 cross-tenant／cross-elder isolation、revocation、tombstone、graph lag 與 provider failure。

### Phase 4 — Release decision

- 完成 owner decisions、source accuracy／rights／version review、staging deployment evidence。
- 驗證安全、資料區域、availability、latency 與 cost ceiling。
- 由 release owner 明確批准後，才可建立 production allowlist 與 rollout／rollback 計畫。

## 12. 品質與安全門檻

沿用 Spec 11 的最低門檻：

| Gate | 最低標準 |
| --- | --- |
| Recall@5 | `>= 0.85` |
| NDCG@5 | `>= 0.80` |
| Metadata Filter Pass Rate | `100%` |
| expired／needs_review 被當作 authoritative answer | `0` |
| Grounded Answer Rate | `>= 95%` |
| Unsupported Claim Rate | `<= 2%` |
| no-data correctness | `>= 95%` |
| Query Intent Route Accuracy（Phase 3） | `>= 90%` |
| Relevant Node／Edge Recall（Phase 3） | `>= 90%` |
| Cross-Elder Node Rate | `0` |
| Deleted／Inactive Memory Retrieval | `0` |
| graph projection p95 lag | `<= 60s` |
| graph failure fallback | `100%` |

此外，每次 model、embedding、chunking、mapping、fusion、reranker 或 policy 版本變更都必須重新跑相關 evaluation；平均分數不得掩蓋 metadata、scope、revocation 或 unsupported-claim 的零容忍失敗。

## 13. Failure 與 fallback

| Failure | 必要行為 |
| --- | --- |
| Query Gate 無法驗證 scope／consent | deny；不得呼叫 retrieval tools |
| Planner invalid／unknown／逾越 ceiling | fallback 至安全 allowlisted plan 或 `NONE` |
| PostgreSQL retrieval unavailable／malformed batch | no public knowledge；不得使用 partial batch |
| Core data tool unavailable | 不得把 Search／Graph 結果冒充 formal data |
| Graph unavailable／lagging | 移除 graph context，走 allowlisted fallback |
| citation／version／locator 不完整 | evidence 不得進入 grounded answer |
| sources conflict | 標示衝突，優先 formal state；不可靜默合併 |
| restricted data detected in output／logs | block／redact，留下 bounded audit metadata |

## 14. Owner decisions 與 release blockers

下列項目在開始對應階段前需有明確 owner 與 evidence：

- 726 個 candidate 的 human review successor、source accuracy、rights／license 與版本決策。
- Production embedding／model／reranker provider、region、latency 與 cost ceiling。
- PostgreSQL release activation／rollback、read-only role、connection pool、backup／retention policy。
- Phase 3 可開放的 Core query templates、Graph intents、edge allowlist 與 hop ceiling。
- 私人資料 retention、redaction、audit 與 projection deletion SLA。
- Production staging／deployment／availability evidence 與 rollback rehearsal。

未完成上述決策時，安全預設是維持 staging-only、public knowledge only、fail closed。

## 15. 相關規格

- Spec 08：原 AWS deployment profile、Aurora／OpenSearch／Neptune 與 projection boundary；Phase 1 public search target 由 ADR 0018 改為 PostgreSQL。
- Spec 09：`EXACT_TRANSACTIONAL`／`KEYWORD`／`VECTOR`／`GRAPH`／`HYBRID`／`NONE` query types 與 bounded planner 原則。
- Spec 10：Target `QueryPlan` 欄位；不得產生任意 executable DSL。
- Spec 11：retrieval、grounding、graph、安全與 release evaluation gates。
- Spec 12：分期實作、owner 與交付證據。
- Spec 14：observability、incident 與 dependency failure handling。

若本規格與既有 Current implementation 不一致，應先標示差異並新增 ADR／migration task，不得把 Target 描述成已存在行為。
