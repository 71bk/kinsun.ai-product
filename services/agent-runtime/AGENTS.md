# AGENTS.md — agent-runtime

- 2026-10-02 RAG 簡化第 1 批：程式由 Git 管理；保留真實來源、來源／資料版本與 text／embedding_text 內容 hash。停止 current byte audit successor 鏈，不建立 v021；不再要求每次程式改動新增 manifest、snapshot、封存或 byte attestation。
- 逐筆人工覆核、E3 review 工作台／prepare／validate 與 1,055 qrels 填寫退出日常必經路徑。不要求使用者填完作業包；不得把 pending、needs_review、AI 判定或 synthetic 結果冒充人工 verified。
- 本批只退役開發流程，未完成 runtime／SQL 新准入、自然生成或資料 import。現行 flags、v004 release／policy 與外部寫入／production 授權規則仍有效：`RAG_EVIDENCE_V3_ENABLED=false`，真實 needs_review 的 V3 支持集合仍不能通過，V1／V2 最低引用數與既有 gate 尚未改。第 2–4 批才處理這些行為。
- v020 及以前 audit、舊人工覆核／acceptance／rechunk 報告與 pinned 資料僅為歷史紀錄，不代表今天的程式，也不構成新增 successor 的義務；保留其 bytes。先前 707 原記錄＋28 重切候選、41 facts 與本機 v005 未因此寫外部 DB 或切換 release。
- 有效操作及後續批次見 [`RAG 簡化第 1 批`](../../docs/project/rag-simplification-phase1-20261002.md)。舊報告中的強制逐筆覆核、反覆 audit／封存要求已被使用者本次授權取代。真實來源、secret、Consent、身分及權限規則不變。

- 更新日期：2026-09-29（RAG 現況段落）；其餘段落仍校準於 2026-09-02
- 校準基準：`main` at `03cd170`；RAG 同步狀態另見下方 2026-09-10／09-29 條目

本檔補充 repository 根目錄的 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `services/agent-runtime/`。
根目錄那份的規則一律適用；兩者衝突時以根目錄為準。

負責範圍與邊界見 [`docs/ownership/member-c-scope.md`](../../docs/ownership/member-c-scope.md)。

## 目前狀態

M0 Agent Foundation。可執行的最小 Agent 閉環：HTTP → contract 驗證 → Orchestrator
→ Companion Agent → Safety Evaluator → 回應。Repository 預設走 `MockModelProvider`；程式碼另有
`models/bedrock_provider.py`，設定
`MODEL_PROVIDER=bedrock`、`AWS_REGION` 與 `BEDROCK_TEXT_MODEL_ID` 後才會選用。Bedrock provider
能接收已通過 RAG 治理的 context，但尚未用真實 AWS 憑證與模型端點驗證，不得描述成已部署。
`MODEL_PROVIDER=openai-compatible` 則使用 provider-neutral text adapter；base URL、model ID 與
optional Bearer key 全由 runtime 設定，可接相容本機服務或 Google Gemini API。它只支援文字
Chat Completions、不跟隨 redirect、錯誤時不會 fallback 到 mock，且帶 key 的遠端 HTTP 會在
啟動時被拒絕。RAG Retriever 已透過 provider-neutral `SearchBackend` 與不含 executable DSL 的
bounded plan 隔離搜尋 provider；runtime factory 可明確選 legacy OpenSearch 或 PostgreSQL。
`MODEL_PROVIDER=gemini` 則使用原生 Google Gen AI SDK；`AQ.` 開頭的 Vertex AI Express key 自動
走 Vertex AI，其他 key 走 Gemini Developer API。這兩種 key 不得混用 endpoint；設定不完整或
Google provider 失敗時一律 fail closed，不會退回 mock，也不得把上游訊息帶出 provider 邊界。

2026-09-02 起，RAG 啟用時的預設 search backend 是 PostgreSQL，預設 query embedding config 是
`config/rag/embedding-google.yaml`；仍需完整 release／profile／database／policy 設定才會啟動。
OpenSearch／Bedrock 只在明確設定時選用，沒有現行 AWS deployment evidence。

另有第一版 **staging-only** RAG endpoint、provider-neutral `EmbeddingProvider`／`SearchBackend`
boundaries、Bedrock 與 opt-in Google query embedding adapters、legacy OpenSearch Hybrid adapter，
以及固定模板、全參數化的 PostgreSQL FTS／trigram＋pgvector Hybrid adapter。2026-08-25 已將
726 個 Google document embeddings 匯入 Supabase development database，並以
`RAG_SEARCH_BACKEND=postgresql` 對固定 release／profile 完成 data-plane 與 Google query embedding
全鏈路 smoke；兩者皆回傳 5 筆合規 V2 staging chunks。2026-08-25 的
`RAG_STAGING_ALLOW_ALL_AUDIENCES=true` legacy override 已不在使用中（目前 `.env` 為 `false`），
Production 本來就禁止此 override。

**2026-09-10 已對 Supabase development database 完成外部同步**（授權
`docs/project/rag-law-sync-authorization-20260910.json`，工具 `scripts/rag/sync_law_repair.py`）：
新 immutable release `rag-v2-v004-f3339ceae77c` 以單一交易匯入 726 projections ＋ 726 既有向量，
只改 71 筆長照法治理欄位（`requires_professional_assessment` null→true、移除該筆 block reason），
其餘 655 筆與 `_0048` 的 high-red-line／stop 封鎖不變，舊 release v002 保留，獨立唯讀讀回 `VERIFIED`。
runtime policy 升為 v004（SHA-256 `a7d8dd16…`）包裝原 v003 policy、554 筆 pool 不擴大、改綁新 release。
「長照法」「長照法第二條」經真實 BFF → Core → Agent 為 `SUCCESS / ALLOW`，並已補 Playwright
瀏覽器驗收（[09-10 瀏覽器證據](../../.qa/rag-law-browser-verification-20260910.json)）。
2026-09-29 以 `sync_law_repair.py verify` 唯讀複驗：`status=VERIFIED`、726／726、
profile `ep-google-00a12ec45096fa9d97d9e9b6`、export SHA-256 與 09-10 紀錄逐一相符；
證據見 [09-29 唯讀複驗報告](../../docs/project/rag-law-sync-verification-20260929.json)。

**`data/rag-v3/candidates/v003/` 不是 v004 的後繼**，而是同樣分支自 `rag-v2-v002` 的平行候選
（726 筆 `prior_chunk_id` 相同），且建於 09-09 法規修復之前——它的 72 筆長照法全數仍被
`requires_professional_assessment_missing` 封鎖。逐筆比對：同步 v003 會新開放 224 筆、**關閉 71 筆
長照法**。要採用 v003 的 `review_status=verified` 必須另建以 v004 為基底的 successor，不可直接同步。
全庫仍 `review_status=needs_review`、`production_approved=false`、
`retrieval_activation_status=NOT_AUTHORIZED`。

2026-08-26 已把本機 source-family policy v002 投影為
immutable、hash-pinned runtime policy v001 並接入 V2：search backend 先在固定 554 筆 v002 chunk IDs
搜尋最多 50 筆，Retriever 再以 v003 text SHA-256、四角色、purpose 與 assessment metadata 決定
3–5 筆回覆；遠端 live current／stop／retrieval／block reasons／review-production 狀態不可被 policy
覆蓋，並在搜尋與回覆階段各自 fail closed；high／unknown、stop、非 current 與 research 不在搜尋
projection。policy 啟用時不得與
legacy all-audience override 併用。10 個離線 policy／citation Golden cases 已通過，但真實 backend
relevance／ranking Golden Query 尚未執行。2026-08-28 Owner v006 closeout acceptance 已人工確認
runtime v003 中 32 筆 A 單位 purpose，並核准 27 筆 `stop_normal_rag=true` 進入身份別條件開放複核；
此 acceptance 沒有修改 runtime v003，27 筆在逐筆 audience／purpose 驗證完成前仍不進 current 554 筆
候選池。Google query
adapter 不得查詢 Cohere document vectors。只有明確標示
`general_information`／`legal_reference` purpose 的回合會檢索；成功時 3–5 個帶引用 chunk
進入 Context Manifest，無資料或 provider 失敗時直接 no-guess fallback。未設定 provider
時明確 fail closed。Supplied Allowlist 尚未簽署；只有 staging 明確設定
`RAG_REQUIRE_OWNER_SIGNATURE=false` 時，才允許 unsigned development override。Override
不得關閉外部 `RAG_ALLOWLIST_EXPECTED_SHA256` 精確比對，也不得略過來源、Chunk、數量或
完整 Allowlist 驗證；receipt／log 必須標示
`governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、`production_approved=false`。
Production 仍須正式簽署 Allowlist，並明確設定 `RAG_PRODUCTION_ENABLED=true`。獨立 PostgreSQL
read-only principal、live relevance Golden Query／quality gate、activation／rollback 與正式 runtime
deployment 均未完成；本機目前暫時重用 Core DB URL。AWS/OpenSearch 亦未完成真實環境驗證，
因此不得描述成已部署或可用於
production。

Event／Memory Candidate 採 Core-owned proposal flow：request 的 `requested_outputs` 明確包含
`event_candidate`，並可在另外通過 memory authorization／Consent 時包含 `memory_candidate`。
Safety 為 `ALLOW` 且 deterministic extractor 找到受支援內容時，Runtime 只回傳不含
actor／tenant／elder／session／consent／source ID／逐字稿的 typed proposal。Memory first slice
只辨識明確固定早餐習慣，且必須同時有 Event proposal；一般聊天、一次性事件、健康／情緒／
陪伴需求推論都不產生 Memory proposal。Runtime
不向 Core 註冊或完成 AgentRun、不呼叫 Core Tool，也不寫 domain DB；Core 才能在重新授權、
重驗 Consent 並完成 conversation session 後建立 review-required Event Candidate。Memory proposal
先私下保存在 Event version；照護者 VERIFY 來源事件後，Core 再重驗 memory gate 並建立仍須長者
本人確認的 Memory Candidate。舊 `allowed_tools` 欄位保留解析相容，但 canonical Core path 固定
傳空陣列。尚未實作（不要描述成已完成）：其他類型的 Memory 自動擷取與 conflict detection、
Model Router、Prompt Registry、完整 Agent Trace、Neptune、通用 Tool 執行
迴圈與 RAG／Graph Evaluation。`BASIC_VOICE` request 現可接收 Core 已重驗授權／Consent 的最多
5 筆 current ACTIVE Confirmed Memory；Runtime 以獨立 `confirmed-memory` context item 標記，並把
內容當資料而非指令。Knowledge／RAG purpose 的 request 不得帶這個欄位。現行 selection 仍只是
Core 依更新時間做 bounded first slice，尚未有語意相關性排序；Verified Care Data 與 Graph 仍未
進入 Runtime Context。Repository 內仍有早期
Core Tool client／request 相容程式，但 canonical orchestrator 不會依 `allowed_tools` 呼叫 Core；
若 README 或舊測試敘述相反，以目前 orchestrator、Core companion service 與本檔為準。

上述是 Current first slice。Accepted Target 依根目錄 Spec 18／ADR 0014：Runtime 仍只輸出不可信
proposal 與 risk hint；Core 依 versioned policy、verified Elder speaker、第一人稱／否定／時間語意、
confidence、Consent 與 scope 決定 LOW all-of auto-save、MEDIUM fixed-version Elder confirmation 或 HIGH
restriction。Runtime 不得宣告 actual risk、confirmation 或 ACTIVE；Staff／Family witness 不得替 Elder
consent。Care Event VERIFIED 不自動 promotion 成 Memory，HIGH 不建立 Memory row／content。

## 硬性規則

- **不得讓 Agent 直接改變正式 Domain State**。Event 轉 `VERIFIED`、Memory 轉 `ACTIVE`、
  Consent 變更、Report 發布，一律透過 Core API 的 Command Gate，由 Core 重新授權。
- **不得繞過 ElderScope、Consent 或 Authorization**。本地用 Mock 不是省略這些檢查的理由。
- **不得跨 `elder_id` 或 `tenant_id` 讀取資料**。
- **只有每次通過 Core final retrieval gate 的 Trusted Memory 可進 Context**：current ACTIVE、有效 Consent、
  Speaker ownership、risk verification、version binding（如需要）、validity、tenant／elder scope 與
  tombstone 缺一不可；MEDIUM 未確認／stale、HIGH 與 legacy 缺證據資料一律排除。
- **`APP_ENV=production` 有啟動 gate**。`create_app()` 第一件事是
  `validate_production_configuration()`：`MODEL_PROVIDER` 必須是
  `bedrock`／`gemini`／`openai-compatible`，`RAG_ALLOW_NEEDS_REVIEW_CITATIONS` 與
  `RAG_STAGING_ALLOW_ALL_AUDIENCES` 必須是 false，而
  **`PRODUCTION_APPROVED_RAG_MODES` 目前刻意是空集合**——`disabled` 沒有受治理檢索，
  `staging` 綁 `production_approved=false` 的 release，所以 production 現階段一律啟動失敗。
  這不是 bug，解除條件只有一條：Owner 核准 production retrieval release 後，把該 mode 加進
  `app.py` 的那個常數。`local`／`test`／`staging` 完全不受影響。Dockerfile 的出廠預設
  （`APP_ENV=production`＋`mock`＋`disabled`）被測試釘住必須被拒絕，image 不得以預設啟動成
  production runtime。
- **Service credential 的 replay 判定必須可跨 replica**。`ServiceCredentialVerifier` 的
  `replay_store` 是必填參數；`InMemoryReplayStore`（`durable=False`）只給 test 與單一 process 的
  本機執行。設定 `SERVICE_IDENTITY_REPLAY_DATABASE_URL` 會改用 `PostgresReplayStore`，以 Core
  migration 建立的 `service_identity.credential_nonce` 做 `INSERT ... ON CONFLICT DO NOTHING`
  atomic claim；`APP_ENV=production` 沒有這項設定時 `create_app()` 直接失敗。Runtime 只碰這一張
  非 domain 表，不對 `eldercare_ai` 有任何 grant。claim 因 driver 失敗而無法判定時 fail closed，
  錯誤訊息只帶 exception type。
- **不得產生可執行的 SQL、Gremlin 或 OpenSearch DSL**。查詢一律走參數化的 Planner。
- **不得建立無上限的 Agent Loop**。每條控制流都要有 step 上限與明確停止條件。
- 所有 Agent 輸出必須同時通過 Pydantic model 與 `contracts/schemas/` 的 JSON Schema。
- 不得在 Prompt、測試、fixture 或 log 放入真實個資。測試資料一律 Synthetic。
- Contract 不明確時使用 Adapter／Stub，不自行發明跨團隊 Contract。

## 實作慣例

- **Contract first**。`contracts/schemas/agent/`、`contracts/schemas/tools/` 的 JSON Schema
  與 `src/agent_runtime/contracts/models.py` 的 Pydantic model 必須一致，由
  `tests/unit/test_contract_schema_consistency.py` 守著（含 `additionalProperties: false`
  對應 `extra="forbid"`）。
- **外部服務只在 Provider／Adapter 邊界出現**。模型邊界包含 `models/provider.py` 的
  `ModelProvider` 介面、`models/mock_provider.py`、`models/bedrock_provider.py` 與
  `models/openai_compatible_provider.py`；共用安全 prompt 位於 `models/prompting.py`。RAG 邊界位於
  `rag/`，Retriever 只依賴 `SearchBackend`；OpenSearch DSL 必須留在其 adapter。新增或調整
  Bedrock、Google embedding、OpenSearch、PostgreSQL search 或 Neptune 整合時，不要把 SDK 呼叫散進
  orchestration 或 agent 層。
- Step／Tool 上限來自 `settings.py`：`MAX_AGENT_DECISIONS`、`MAX_TOOL_ROUNDS`、
  `MAX_TOTAL_TOOLS`、`MAX_REWRITE`。目前 companion 仍只有單一模型決策；Event proposal 是
  deterministic output，不是 Tool call。`MAX_TOOL_ROUNDS`／`MAX_TOTAL_TOOLS` 保留供未來
  受控 Tool loop，`MAX_REWRITE` 尚未有程式使用。

## 對外 API 慣例

依 [ADR 0005](../../docs/adr/0005-agent-runtime-api-conventions.md)：

- 路徑 `/api/v1/agent/runs`；`/health` 維持在根層。
- 成功回應 `{"data", "meta"}`、錯誤回應 `{"error"}`，型別在
  `core/envelopes.py`，JSON Schema 共用 `contracts/schemas/common/`。
  **不要讓任何 endpoint 自行拼裝頂層結構。**
- 錯誤一律 `DomainError → api/error_handlers.py → ErrorEnvelope`。狀態碼對應只有一份
  （`EXCEPTION_MAP`）。不在 endpoint 或 orchestrator 裡組裝 HTTP 錯誤。
- `EXCEPTION_MAP` 沒收錄的 `DomainError` 子類會變成 500——這是刻意的 fail loud，
  新增例外時要同步登記。
- **錯誤回應不得回填被拒絕的值**。request body 是長者逐字稿；`details[].reason` 只帶
  pydantic 的 error type，不帶內容。

安全阻擋是 200 不是錯誤：`result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息。
拒絕是對話結果，長者仍然會收到回覆。

## 測試

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

不需要資料庫、不需要 AWS 憑證、不需要網路。`tests/conftest.py` 在 test module 匯入 app 前
固定 `APP_ENV=test`、`MODEL_PROVIDER=mock`；不得移除這層隔離，否則 developer `.env` 可能讓
一般 integration tests 呼叫真實模型並讀取 secret。

2026-08-25 本機基準：377 tests passed；Ruff check、完整 Ruff format check、靜態 contract
validator 與本機 Agent live contract verifier 均通過。另完成一次 PostgreSQL data-plane smoke 與
一次 Google query embedding → Supabase → V2 citation smoke，各回傳 5 筆受治理 staging chunks。
這不是 runtime deployment 或 Production 驗證；Bedrock／OpenSearch staging 仍未驗證。

`tests/unit/test_contract_schema_consistency.py` 掃的是 repository 根目錄的
`contracts/schemas/`，因此它同時會驗證 core-api 的 schema 是否為合法的 JSON Schema。
core-api 那邊加了壞掉的 schema，這裡會紅——這是刻意保留的交叉守護。

改到 endpoint 或回應形狀時，另外跑 live 驗證（AGENTS.md §8.2）：

```powershell
cd services/agent-runtime
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

它對**實際執行中的服務**驗證，包含安全阻擋回合仍是 200、超過 step 上限走 domain
handler 而非 catch-all、以及錯誤回應不回填被拒絕的輸入。新增 endpoint 要同步在裡面加檢查。
