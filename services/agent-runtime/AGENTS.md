# AGENTS.md — agent-runtime

本檔補充根目錄 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `services/agent-runtime/`；根目錄規則一律適用，衝突時以根目錄為準。
整理日期：2026-10-15。負責範圍見 [`docs/ownership/member-c-scope.md`](../../docs/ownership/member-c-scope.md)。

| 需要 | 讀 |
| --- | --- |
| RAG 目前 release、資料／外部寫入／驗收規則、版本沿革 | [`docs/project/rag-release-history.md`](../../docs/project/rag-release-history.md) |
| 各次交付與驗收結果 | [`docs/project/progress-log.md`](../../docs/project/progress-log.md)、[交付索引](../../docs/project/README.md) |
| Agent 架構背景 | [`docs/architecture/agent-runtime-overview.md`](../../docs/architecture/agent-runtime-overview.md) |

## 目前狀態

- 單輪閉環：HTTP → contract 驗證 → Orchestrator → Companion Agent → deterministic Safety Evaluator → 回應。
  目前只有單一模型決策；Event proposal 是 deterministic output，不是 Tool call。
- Model provider（`MODEL_PROVIDER`）：`mock`（repository 預設）、`bedrock`（另需 `AWS_REGION`、`BEDROCK_TEXT_MODEL_ID`）、`openai-compatible`（只依 runtime URL／model／
  optional Bearer key，不跟隨 redirect，帶 key 的遠端 HTTP 啟動即拒絕）、`gemini`（Google Gen AI SDK；`AQ.` 開頭的 Vertex AI
  Express key 走 Vertex AI，其他走 Gemini Developer API，不得混用 endpoint）。設定不完整或呼叫失敗一律 fail closed，不 fallback
  到 mock，也不把上游訊息帶出 provider 邊界。本機 development 以真實 Vertex 驗收；Bedrock／OpenSearch 無現行部署證據。
- RAG：`RAG_MODE` 預設 `disabled`。啟用時預設 PostgreSQL FTS／trigram＋pgvector Hybrid backend 與
  `config/rag/embedding-google.yaml`，仍需完整 release／profile／database／policy 設定才會啟動；legacy OpenSearch 只在明確設定時選用。
  Endpoint：`POST /api/v1/rag/retrievals`（相容）、`/api/v2/...`（治理 citation，3–5 筆）、`/api/v3/...`（預設關閉，自然問句
  Hybrid＋生成，1–5 筆引用）。只有標示 `general_information`／`legal_reference` purpose 的回合會檢索；無資料或 provider 失敗走
  no-guess fallback。
- Event／Memory：Core 以 `requested_outputs` 要求 proposal（`event_candidate`；另通過 memory 授權／Consent 時可含 `memory_candidate`）；Safety 為 `ALLOW` 且 extractor 找到受支援內容時，Runtime 只回傳不含
  actor／tenant／elder／session／consent／source ID／逐字稿的 typed proposal。Memory first slice 只辨識明確固定早餐習慣，且需同時有
  Event proposal。Runtime 不註冊或完成 AgentRun、不呼叫 Core Tool、不寫 domain DB；canonical path 的 `allowed_tools` 固定空陣列
  （舊欄位與早期 Core Tool client 只為相容，README 或舊測試敘述相反時以 orchestrator 與本檔為準）。
- Context：`BASIC_VOICE` 可接收 Core 已重驗的最多 5 筆 current ACTIVE Confirmed Memory，以獨立 `confirmed-memory` item 標記並視為資料
  而非指令；Knowledge／RAG purpose 的 request 不得帶此欄位。尚無語意相關性排序；Verified Care Data 與 Graph 未進 Context。
- 尚未實作（不要描述成已完成）：其他類型 Memory 自動擷取與 conflict detection、Model Router、Prompt Registry、完整 Agent Trace、
  Neptune、通用 Tool 執行迴圈、RAG／Graph Evaluation。
- 以上是 Current first slice。Accepted Target 依 Spec 18／ADR 0014：Runtime 仍只輸出不可信 proposal 與 risk hint；Core 依 versioned
  policy、verified Elder speaker、語意、confidence、Consent 與 scope 決定 LOW auto-save、MEDIUM 固定版本確認或 HIGH restriction。
  Runtime 不得宣告 actual risk、confirmation 或 ACTIVE；Staff／Family witness 不得替 Elder consent；Care Event VERIFIED 不自動成為 Memory。

## 硬性規則

- **不得讓 Agent 直接改變正式 Domain State**。Event 轉 `VERIFIED`、Memory 轉 `ACTIVE`、Consent 變更、Report 發布，一律透過 Core
  Command Gate，由 Core 重新授權。
- **不得繞過 ElderScope、Consent 或 Authorization**；本地用 Mock 不是省略檢查的理由。不得跨 `elder_id` 或 `tenant_id` 讀取資料。
- **只有每次通過 Core final retrieval gate 的 Trusted Memory 可進 Context**：current ACTIVE、有效 Consent、Speaker ownership、risk
  verification、version binding（如需要）、validity、tenant／elder scope 與 tombstone 缺一不可。
- **`APP_ENV=production` 有啟動 gate**：`create_app()` 先跑 `validate_production_configuration()`。`MODEL_PROVIDER` 必須是真實 provider，
  `RAG_ALLOW_NEEDS_REVIEW_CITATIONS` 與 `RAG_STAGING_ALLOW_ALL_AUDIENCES` 必須 false，且 `app.py` 的
  **`PRODUCTION_APPROVED_RAG_MODES` 刻意是空集合**，所以 production 現階段一律啟動失敗。這不是 bug；只有 Owner 核准 production
  retrieval release 後才把該 mode 加入。Dockerfile 出廠預設（production＋mock＋disabled）被測試釘住必須被拒絕。
- **Service credential replay 判定必須可跨 replica**：`ServiceCredentialVerifier` 的 `replay_store` 必填；`InMemoryReplayStore` 只給
  test 與單一 process 本機。`SERVICE_IDENTITY_REPLAY_DATABASE_URL` 改用 `PostgresReplayStore`（`service_identity.credential_nonce` 的
  `INSERT ... ON CONFLICT DO NOTHING`）；production 缺此設定 `create_app()` 直接失敗。Runtime 對 `eldercare_ai` 沒有任何 grant；
  claim 無法判定時 fail closed，錯誤只帶 exception type。
- **不得產生可執行的 SQL、Gremlin 或 OpenSearch DSL**；查詢走參數化 Planner／bounded plan。
- **不得建立無上限的 Agent Loop**；每條控制流都要有 step 上限與明確停止條件。
- 所有 Agent 輸出同時通過 Pydantic model 與 `contracts/schemas/` 的 JSON Schema。
- Prompt、測試、fixture、log 不放真實個資。Contract 不明確時用 Adapter／Stub，不自行發明跨團隊 Contract。

## RAG 與生成的實作規則

- Retriever 只依賴 `SearchBackend`；遠端 live current／stop／retrieval／block reasons／review-production 狀態不可被本機 policy 覆蓋，
  搜尋與回覆階段各自 fail closed。Google query adapter 不得查詢 Cohere document vectors。
- 每次檢索連線／交易第一步執行共用 `configure_readonly_transaction`（明確 READ ONLY 與 timeout），失敗不得執行搜尋 SQL；實測
  preflight 同樣套用。SQL predicate 的 regex 須經 SQLAlchemy `text()` 編譯檢查 bind keys。
- V3 排序：raw lexical capped score＋dense，不沿用 legacy 0.7 門檻，弱 trigram 不 min-max 放大；授權／來源／hash gate 與最多 5 筆不變。
  V1／V2 排序與舊 quote 精確比對保留。
- 生成以來源連續 span ID 定位，未知 ID 或任意 offsets 拒絕。至少三行有欄間寬空白的疑似多欄來源整筆不送生成，全部排除回
  NO_DATA；不自行拼接或重排來源。正確 span ID 不代表欄位順序或語意已釐清。
- PDF 排版相容只移除漢字間至少兩格縮排的續行；保留 tab、行內空格、未縮排換行、空白行與所有非空白字元。禁用全域去空白或 NFKC 當來源驗證。
- Gemini grounded schema 只約束形狀；parser 繼續檢查來源 ID 與原文支持，不是語意判官。不放寬驗證冒充通過。
- 不要把整個來源（例如 A 手冊）的 `source_id` 當成專業限定；只排除專業片段，保留家屬可用記錄。
- 生成預算：一般 token 512；grounded JSON 下限 4096 token（`models/prompting.py`），外層 parser 20000 字元，一般文字與解析後答案仍限
  4000。公開問答各層 deadline 見 RAG 文件；外部取消必須向上傳遞，typed provider timeout、服務 deadline 與外部取消分開。
- Gemini 3.8 最低 thinking level 為 LOW（MINIMAL 會被拒），3.6 用 MINIMAL，其他模型維持原 temperature 行為；不用寬鬆名稱比對推測未來模型能力。
- `rag_v3_failure` 以 task-local context 記錄，標準 logger 輸出精簡 JSON：request_tag 為 request_id SHA-256 前 16 碼，只有階段、固定
  code、耗時；不得附 exception、traceback、問句或模型原文。未知驗證理由映射通用分類；正常 SUCCESS／NO_DATA 不記為失敗。

## 實作慣例

- **Contract first**：`contracts/schemas/agent/`、`contracts/schemas/tools/` 與 `src/agent_runtime/contracts/models.py` 必須一致，由
  `tests/unit/test_contract_schema_consistency.py` 守著（`additionalProperties: false` 對應 `extra="forbid"`）。
- **外部服務只在 Provider／Adapter 邊界**：模型邊界在 `models/`（`models/provider.py` 的 `ModelProvider` 介面與各 provider），共用安全 prompt 在
  `models/prompting.py`；RAG 邊界在 `rag/`，OpenSearch DSL 留在其 adapter。不要把 SDK 呼叫散進 orchestration 或 agent 層。
- Step／Tool 上限來自 `settings.py`：`MAX_AGENT_DECISIONS`、`MAX_TOOL_ROUNDS`、`MAX_TOTAL_TOOLS`、`MAX_REWRITE`；後三者保留給未來
  受控 Tool loop，`MAX_REWRITE` 尚無程式使用。

## 對外 API 慣例

依 [ADR 0005](../../docs/adr/0005-agent-runtime-api-conventions.md)：

- 路徑 `/api/v1/agent/runs`；`/health` 在根層。成功 `{"data", "meta"}`、錯誤 `{"error"}`，型別在 `core/envelopes.py`，JSON Schema
  共用 `contracts/schemas/common/`。**不要讓任何 endpoint 自行拼裝頂層結構。**
- 錯誤一律 `DomainError → api/error_handlers.py → ErrorEnvelope`，狀態碼對應只有一份 `EXCEPTION_MAP`；未收錄的子類刻意變成 500
  （fail loud），新增例外要登記。
- **錯誤回應不得回填被拒絕的值**：request body 是長者逐字稿，`details[].reason` 只帶 pydantic error type。
- 安全阻擋是 200 不是錯誤：`result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息。

## 測試

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
# 改到 endpoint 或回應形狀時（對執行中的服務驗證，不需 DB、憑證或網路）
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

- 不需資料庫、雲端憑證或網路。`tests/conftest.py` 在匯入 app 前固定 `APP_ENV=test`、`MODEL_PROVIDER=mock`；不得移除這層隔離。
- pytest 也必須能從 repo root 以 `uv run --project services/agent-runtime pytest services/agent-runtime/tests` 執行；測試不得以
  `tests.unit.*` 匯入另一測試檔的 helper。
- `test_contract_schema_consistency.py` 掃整個 `contracts/schemas/`，core-api 加了壞 schema 這裡也會紅（刻意的交叉守護）。
- Live verifier 涵蓋安全阻擋仍是 200、超過 step 上限走 domain handler、錯誤不回填輸入；新增 endpoint 要同步加檢查。
- 實測 RAG 時：SUCCESS／PARTIAL、引用 ID 與錨點不等於語意正確；定向複測不得拼成新整批分數（見 RAG 文件）。
