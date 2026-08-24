# Agent Runtime Service

成員 C（Agent／RAG／Graph）的服務。目前保留 M0 Agent 閉環，並新增第一版
**staging-only、fail-closed** RAG Retrieval，以及一條受控的
`create_event_candidate` Core Tool 寫入路徑；尚未對 AWS 環境完成實際連線驗證。
規則見 [`AGENTS.md`](AGENTS.md)，架構見
[`docs/architecture/agent-runtime-overview.md`](../../docs/architecture/agent-runtime-overview.md)。

## Endpoints

- `GET /health`
- `POST /api/v1/agent/runs`
- `POST /api/v1/rag/retrievals`
- `POST /api/v2/rag/retrievals`

契約在 [`contracts/openapi/agent-runtime.v1.yaml`](../../contracts/openapi/agent-runtime.v1.yaml)
與 [`contracts/openapi/agent-runtime.v2.yaml`](../../contracts/openapi/agent-runtime.v2.yaml)。

V1 retrieval 保留作相容路徑。V2 是 Agent 內部採用的完整治理 citation 契約：每筆結果都帶
`source_locator`、公開來源 URL、版本證據、`review_status` 與
`production_approved`，且永遠不回傳 `storage_url`。任一候選 citation 不完整時，V2
整批回傳空結果，不以其他 chunk 掩蓋資料缺口。

## 執行

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

一般無 Tool 的本機回合不需要資料庫、Core API、AWS 憑證或網路；未設定 staging RAG
provider 時，retrieval endpoint 會明確回傳 `FAILED` fallback 與空結果，不會猜測答案。
要啟用真實檢索時，依根目錄 `.env.example` 設定明確的 embedding provider、search backend 與
版本化 RAG config 路徑。

### RAG query embedding

預設 `RAG_EMBEDDING_CONFIG_PATH=config/rag/embedding.yaml` 仍選 Bedrock/Cohere。Google query
embedding 是 opt-in，使用獨立的 Agent Runtime override，不會改動 ingestion 共用設定：

```dotenv
GEMINI_API_KEY=<runtime-secret>
GEMINI_EMBEDDING_MODEL_ID=gemini-embedding-001
GEMINI_EMBEDDING_DIMENSION=1024
GEMINI_EMBEDDING_TIMEOUT_SECONDS=30
RAG_QUERY_EMBEDDING_CONFIG_PATH=config/rag/embedding-google.yaml
```

Google adapter 固定使用 `RETRIEVAL_QUERY` task type，provider error、空回應或維度不符一律 fail
closed。此設定目前只證明 query adapter；ingestion 尚未產生 Google `RETRIEVAL_DOCUMENT` vectors，
不得把 Google query vectors 與既有 Bedrock/Cohere corpus 混用。必須先用同一 model／dimension
重建完整 projection 並通過 evaluation，才可接真實 search backend。

## 模型設定

`MODEL_PROVIDER=gemini` 會使用 Google Gen AI SDK 的原生 `generate_content` API。`AQ.` 開頭的
Vertex AI Express key 會自動走 Vertex AI；其他 Gemini API key 走 Gemini Developer API。兩者
不能混用 endpoint，設定不完整或 provider 失敗時一律 fail closed，不會退回 mock：

```dotenv
MODEL_PROVIDER=gemini
GEMINI_API_KEY=<runtime-secret>
GEMINI_MODEL_ID=<configured-model-id>
GEMINI_MAX_TOKENS=512
GEMINI_TEMPERATURE=0.2
GEMINI_TIMEOUT_SECONDS=30
```

模型名稱不在程式碼寫死。Core 的 `AGENT_RUNTIME_MODEL_ID` 應同步使用相同 audit label；API key
只可由本機未版控 `.env` 或部署平台 secret store 注入，不得放進 image、前端或 log。

`MODEL_PROVIDER=openai-compatible` 會啟用 provider-neutral Chat Completions adapter。
商業流程只依賴 `ModelProvider` 介面，URL、模型 ID 與 credential 都是 runtime 設定；adapter
不使用特定供應商 SDK，也不跟隨 redirect。遠端有 API key 的端點必須是 HTTPS；無驗證的
本機相容端點可以使用 HTTP。

Gemini Developer API 也提供 OpenAI-compatible endpoint；模型名稱仍應依建立 key 時可用的官方
清單選擇，不在 repository 寫死。`AQ.` 開頭的 Vertex AI Express key 請使用上面的原生 provider，
不要送到這個 Developer API endpoint：

```dotenv
MODEL_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
OPENAI_COMPATIBLE_API_KEY=<runtime-secret>
OPENAI_COMPATIBLE_MODEL_ID=<compatible-model-id>
OPENAI_COMPATIBLE_MAX_TOKENS=512
OPENAI_COMPATIBLE_TEMPERATURE=0.2
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=30
```

Google 的 endpoint 與 Bearer 規格以
[Gemini API OpenAI compatibility 官方文件](https://ai.google.dev/gemini-api/docs/openai)為準。
這條路徑只使用文字 Chat Completions，不假設相容層支援供應商專屬 Tool、Grounding 或 File API。

無驗證的本機相容服務可改為：

```dotenv
MODEL_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=http://127.0.0.1:<port>/v1
OPENAI_COMPATIBLE_API_KEY=
OPENAI_COMPATIBLE_MODEL_ID=<local-model-id>
```

Core 的 `AGENT_RUNTIME_MODEL_ID` 是 audit label，部署時應同步設成實際 model ID。API key 只可由
本機未版控 `.env` 或部署平台 secret store 注入，不得放進 image、前端或 log。一般陪伴與
Confirmed Memory 已可走這個 adapter；目前 knowledge RAG 仍依賴 staging Bedrock／OpenSearch，
不會因換文字模型而自動脫離 AWS。

若 `allowed_tools` 明確包含 `create_event_candidate`，Safety 允許且 Event Extractor 真的產生
Candidate，Runtime 才會要求 `CORE_API_BASE_URL`，向 Core 註冊正式 UUID AgentRun、以同一
UUID 執行 Core Tool，並同步完成該 AgentRun。Tool `SUCCESS`／`NO_DATA`／`BLOCKED` 對應同名
終態；Tool `FAILED` 或 dependency failure 先 best-effort 完成 `DEPENDENCY_FAILED` 再回傳
sanitized 503，逾時與取消則分別完成 `TIME_BUDGET_EXCEEDED`／`CANCELLED`。completion 本身失敗
也會 fail closed，不會把未確認的終態當成功。

Runtime 不建立或保存 service token；它只轉交呼叫端既有的 `Authorization`，由 Core 重新驗證
`SYSTEM_SERVICE`、tenant／elder／session／policy、consent、scope 與 idempotency。缺少 Core
設定、Core 拒絕或 transport／protocol 失敗一律 fail closed，不會用本地 `run-<UUID>` 寫入。

未簽署 Allowlist 只有在 staging 明確設定 `RAG_REQUIRE_OWNER_SIGNATURE=false` 時才可使用；
`RAG_ALLOWLIST_EXPECTED_SHA256` 精確比對，以及來源、Chunk、數量與完整 Allowlist 驗證仍為
強制 gate。此 override 的 receipt／log 會標示
`governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、`production_approved=false`，不得當成
Human Review 或 production 核准。Production 仍要求正式簽署，且必須明確設定
`RAG_PRODUCTION_ENABLED=true`。目前尚未完成 Human Review，也未完成 AWS deployment 或
staging 連線驗證。

Agent Run 只在 request `purpose` 明確為 `general_information` 或 `legal_reference` 時使用
`app.state.rag_retriever`；一般 `conversation` 不會誤觸檢索。成功檢索的 3–5 個 chunk 會以
限長、帶來源的 Context Item 傳給 Companion Agent，並由 deterministic post-processing
確保允許送出的回覆附上引用。`NO_DATA`／`FAILED` 或 provider 未設定時不呼叫模型產生知識
答案，直接回 `SAFE_FALLBACK`。

```powershell
curl http://localhost:8001/health
```

## Container image

The image is environment-neutral so an approved release can be promoted without rebuilding;
production deployment itself is not yet approved. Deployment settings are injected at runtime.
The image is multi-stage, contains only the locked runtime dependencies, `src/`, and the four
versioned non-secret RAG configuration files, and runs Uvicorn as UID/GID `10001` rather than root.
Its Dockerfile-specific build context is an explicit allowlist, so `.env`, AWS credentials, RAG
chunks, generated vectors, receipts, tests, and repository metadata are not sent to the Docker
daemon or copied into the image.

```powershell
docker build --file services/agent-runtime/Dockerfile `
  --tag kinsun/agent-runtime:local .
docker run --rm --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m `
  --publish 8001:8001 kinsun/agent-runtime:local
curl http://localhost:8001/health
```

The container intentionally defaults to `MODEL_PROVIDER=mock` and `RAG_MODE=disabled`. Setting
`APP_ENV=staging` alone does not enable Bedrock or retrieval. A staging deployment must explicitly
inject its approved non-secret model/OpenSearch settings and use an ECS task role for AWS access.
The image includes only the Bedrock/Google query embedding configs, the index mapping, and the
natural/legal hybrid profiles;
it does not include an Allowlist, source documents, chunks, receipts, or vectors. Never bake `.env`
or static AWS credentials into the image. Production RAG is not approved; `RAG_MODE=production` is
not a supported runtime mode and still fails closed.

The Docker/ECS health check invokes `python -m agent_runtime.healthcheck`. It only verifies the local
`/health` contract and never probes Core API, Bedrock, or OpenSearch.

## 測試

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .

# 對執行中的服務驗證契約
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

## 設計要點

- **Contract first**：Pydantic model 與 `contracts/schemas/` 的 JSON Schema 必須一致，
  由 `tests/unit/test_contract_schema_consistency.py` 守著。
- **一般 M0 對話不持久化**；只有實際執行 allowlisted Candidate Tool 時，才先建立
  Core-owned AgentRun。模型預設走 `MockModelProvider`；可明確切換 Bedrock 或
  provider-neutral OpenAI-compatible adapter，不會靜默 fallback。
- **RAG 外部依賴只在 adapter 邊界**：Retriever 只接收 provider-neutral `EmbeddingProvider`、
  `SearchBackend` 與不含 executable DSL 的 bounded plan；query embedding 可明確選 Bedrock 或
  Google，唯一 search backend 仍是 OpenSearch。Google document embedding／corpus rebuild 與
  PostgreSQL hybrid backend 尚未實作；設定不完整或 provider 失敗都回 no-guess fallback。
- **Safety 是第一版 deterministic 關鍵字規則**，不是完整安全機制。命中時回 200、
  `result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息——拒絕是對話結果，不是傳輸錯誤。
- **Orchestrator 保持單一模型決策**，並最多執行一次 deterministic Candidate Tool；沒有
  自由 Tool loop、Agent Debate 或未受控重試。
- **RAG intent 是保守的顯式 purpose gate**：目前不以自由文字猜測意圖，避免生活聊天誤觸
  外部知識服務。
- **Retrieval endpoint 目前只允許內部 staging 使用**：目前使用 request-bound service
  credential；`/api/v1/rag/retrievals` 與 `/api/v2/rag/retrievals` 均不得直接暴露到公網。
  `audience`、`purpose` 必須由已授權的內部 caller 從可信身分與用途推導。
- **V2 needs-review override 預設關閉**：只有 staging operator 明確設定
  `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true` 才能回傳 `needs_review` chunk，而且結果仍固定
  `production_approved=false`。目前沒有執行 V2 OpenSearch reindex 或 alias cutover；在相符的
  V2 projection 可用前，真實 adapter 會安全地回 `NO_DATA`。
- 外部服務只能出現在 `models/provider.py`、`core/`、`tools/` 或 `rag/` 的 Adapter 邊界。

## 尚未實作

通用多 Tool 執行迴圈、Memory Candidate、Graph 查詢、Prompt Registry、Model Router、
完整 Agent Trace 持久化（Core AgentRun register／complete lifecycle 以外）、RAG Evaluation、
production index。OpenAI-compatible text provider 與 provider-neutral `SearchBackend` seam 已完成，
但現行唯一 runtime 組裝仍是 staging-only AWS adapters；V2 citation 已用合成 in-process adapter
完成 live verification，並不代表真實
OpenSearch V2 projection、AWS deployment 或 production enablement 已完成。

`contracts/schemas/agent/HandoffEnvelopeV1` 仍是目標形狀；`contracts/schemas/tools/` 現已由
受控的 Core Tool adapter 使用，但目前只接通 `create_event_candidate`。
