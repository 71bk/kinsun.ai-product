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

契約在 [`contracts/openapi/agent-runtime.v1.yaml`](../../contracts/openapi/agent-runtime.v1.yaml)。

## 執行

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

一般無 Tool 的本機回合不需要資料庫、Core API、AWS 憑證或網路；未設定 staging RAG
provider 時，retrieval endpoint 會明確回傳 `FAILED` fallback 與空結果，不會猜測答案。
要啟用真實檢索時，依根目錄 `.env.example` 設定 Bedrock、OpenSearch 與四個 RAG config
路徑。

## 無 AWS 的模型設定

`MODEL_PROVIDER=openai-compatible` 會啟用 provider-neutral Chat Completions adapter。
商業流程只依賴 `ModelProvider` 介面，URL、模型 ID 與 credential 都是 runtime 設定；adapter
不使用特定供應商 SDK，也不跟隨 redirect。遠端有 API key 的端點必須是 HTTPS；無驗證的
本機相容端點可以使用 HTTP。

Google Gemini API 提供 OpenAI-compatible endpoint；模型名稱仍應依建立 key 時可用的官方清單
選擇，不在 repository 寫死：

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
The image includes only `embedding.yaml`, the index mapping, and the natural/legal hybrid profiles;
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
- **RAG 外部依賴只在 adapter 邊界**：查詢 embedding 使用 Bedrock，hybrid retrieval 使用
  OpenSearch；設定不完整或 provider 失敗都回 no-guess fallback。
- **Safety 是第一版 deterministic 關鍵字規則**，不是完整安全機制。命中時回 200、
  `result_status` 為 `BLOCKED`、`reply_text` 換成安全訊息——拒絕是對話結果，不是傳輸錯誤。
- **Orchestrator 保持單一模型決策**，並最多執行一次 deterministic Candidate Tool；沒有
  自由 Tool loop、Agent Debate 或未受控重試。
- **RAG intent 是保守的顯式 purpose gate**：目前不以自由文字猜測意圖，避免生活聊天誤觸
  外部知識服務。
- **Retrieval endpoint 目前只允許內部 staging 使用**：服務對服務 IAM／mTLS／token 尚未
  定案，`/api/v1/rag/retrievals` 不得直接暴露到公網；`audience`、`purpose` 必須由已授權的
  內部 caller 從可信身分與用途推導。
- 外部服務只能出現在 `models/provider.py`、`core/`、`tools/` 或 `rag/` 的 Adapter 邊界。

## 尚未實作

通用多 Tool 執行迴圈、Memory Candidate、Graph 查詢、Prompt Registry、Model Router、
完整 Agent Trace 持久化（Core AgentRun register／complete lifecycle 以外）、RAG Evaluation、
production index。OpenAI-compatible text provider 已完成，但 RAG retrieval 本身仍是 staging-only
AWS adapter，尚未 provider-neutral 化。

`contracts/schemas/agent/HandoffEnvelopeV1` 仍是目標形狀；`contracts/schemas/tools/` 現已由
受控的 Core Tool adapter 使用，但目前只接通 `create_event_candidate`。
