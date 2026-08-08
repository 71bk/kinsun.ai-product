# kinsun.ai

Voice-first 智慧長照 AI 陪伴系統。長者以語音互動，系統從對話中擷取生活事件、產生每日摘要，
供照服員覆核、家屬檢視。核心設計原則是**模型輸出只能是候選**——未經長者確認的記憶與未經
人工覆核的事件，都不得成為正式照護事實。

規則與邊界見 [`AGENTS.md`](AGENTS.md)，產品規格見 [`docs/spec/`](docs/spec/)。

## 現在能跑什麼

| 單元 | 狀態 |
| --- | --- |
| `services/core-api` | ✅ 可跑。Identity、Elder 授權、Consent、Care Event、Memory、Daily Summary、Family Report、受控 Agent Tool、transactional outbox |
| `services/agent-runtime` | ⚠️ M0 骨架。單輪 Agent 閉環可跑，但**模型走 `MockModelProvider`**，不是真的 LLM |
| `packages/frontend` | ⚠️ TEXT_ONLY。PWA + BFF 可跑，但麥克風／ASR／TTS 未實作 |
| `services/rag-ingestion` | ⚠️ staging-only。未對真實 AWS／OpenSearch 驗證 |
| `services/speech-gateway` | ⚠️ ASR／TTS adapter 骨架，尚未接入主線 |
| `infra` | ⚠️ canonical staging foundation 已建於 AWS；application task／service 尚未部署 |

**尚未建立**：CI quality gate、type check（mypy／pyright）、跨服務 contract test、E2E test。
`.github/workflows-disabled/pr.yml` 是未啟用且已知有路徑錯誤的草稿，見 `AGENTS.md` §1。

現有測試共 **919** 個：core-api 587（unit）、agent-runtime 206、frontend 115、infra 11。

## Repository 結構

```text
kinsun.ai/
├── config/rag/     RAG 設定（agent-runtime 與 rag-ingestion 共用，路徑寫死勿搬）
├── contracts/      OpenAPI 3.1、AsyncAPI、JSON Schema
├── data/           RAG chunks、manifest、seed
├── docker/         docker-compose 引用的 PostgreSQL 初始化腳本
├── docs/           spec／adr／architecture／design-system／runbooks／handover…
├── infra/          AWS CDK v2（canonical staging stacks）
├── packages/       frontend（PWA＋BFF）、shared（TypeScript 型別）
├── scripts/        contract 與 repository 驗證腳本
└── services/       core-api、agent-runtime、rag-ingestion、speech-gateway
```

分類軸線是 **runtime**：Python 服務進 `services/`、npm workspace 進 `packages/`。
不是 Turborepo 的 apps／packages 慣例（`services/core-api` 同樣可部署卻不在 `apps/`）。
完整說明見 `AGENTS.md` §9。

## 快速開始

### 需求

- Docker Desktop（含 Docker Compose v2）
- [uv](https://docs.astral.sh/uv/)（本機跑 Python 服務與 Alembic）
- Node.js ≥ 20.9

### 起資料層

```powershell
Copy-Item .env.example .env   # 第一次才需要，.env 不進版控
docker compose up -d postgres
docker compose ps             # 顯示 healthy 才算就緒
docker compose run --rm migrate   # 建立 eldercare_ai schema
```

本機 5432 被占用時，改 `.env` 的 `POSTGRES_PORT`（例如 `15432`）再重跑。

| 項目 | 值 |
| --- | --- |
| Host / Port | `localhost:5432`（`POSTGRES_PORT` 可改） |
| Database | `kinsun`（測試用 `kinsun_test`） |
| User / Password | `kinsun` / `kinsun_local_dev` |
| 版本 | PostgreSQL 16（對齊 Aurora Serverless v2） |

### 起三個服務

```powershell
# Core API :8000
cd services/core-api;    uv sync --extra test --extra dev; uv run uvicorn app.main:app --reload

# Agent Runtime :8001（不需資料庫、AWS 憑證或網路）
cd services/agent-runtime; uv sync --extra test --extra dev
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001

# Frontend :3000
npm install
npm run dev --workspace @elderly-care/frontend
```

### 常用 Docker 指令

```powershell
docker compose exec postgres psql -U kinsun -d kinsun   # 進 psql
docker compose logs -f postgres                          # 看 log
docker compose down                                      # 移除容器（保留資料）
docker compose down -v                                   # 連資料清掉，下次重跑 init
docker compose --profile tools up -d                     # Adminer → localhost:8080
```

### Schema 從哪來

分兩層，不要混：

- `docker/postgres/init/` 只建立 extension（`pgcrypto`、`citext`）與測試資料庫，**不建表**。
  只在資料 volume 為空時執行一次；改了內容要 `docker compose down -v` 才會重跑。
- **所有 table／index／constraint／trigger 由 Alembic 管理**，PostgreSQL schema 名稱是 `eldercare_ai`。

## Core API

[`services/core-api/`](services/core-api/)：FastAPI ＋ SQLAlchemy 2.0 async。

```powershell
cd services/core-api
uv run pytest tests/unit          # 587 tests，不需資料庫
uv run pytest tests/integration   # 需要 postgres 容器
uv run ruff check .
```

授權模型的重點：

- **預設拒絕**，每次請求都對 live DB 重新驗證，不做跨請求快取。
- `BaseRepository` 強制每個查詢帶 `tenant_id` 述詞，且由 constructor 明確傳入而非
  contextvars——背景工作與 consumer 才能建立自己的可信 context。
- **查無此長者與無權限一律回同一個 404**，避免探測長者是否存在。

ORM 的 Python 屬性統一是 `id`，實際對應各表自己的 PK 欄位（`actor.actor_id`、
`elder.elder_id`…），由每個 model 的 `__pk_name__` 宣告。**新增 model 一定要設它**，
否則 SQLAlchemy 會在 class 建立時失敗。

## Agent Runtime

[`services/agent-runtime/`](services/agent-runtime/)：M0 Agent Foundation ＋ 第一版
staging-only RAG Retrieval。

```powershell
cd services/agent-runtime
uv run pytest              # 206 tests，不需資料庫、AWS 憑證或網路
uv run ruff check .
```

閉環是 `POST /api/v1/agent/runs` → contract 驗證 → Orchestrator → Companion Agent →
Safety Evaluator → 回應。**模型仍走 `MockModelProvider`**——這是目前最大的缺口，整條
RAG 鏈路要接上真實 provider 才有意義。

**安全阻擋回的是 200 不是錯誤**：`data.result_status` 為 `BLOCKED`、`data.reply_text`
換成安全訊息，長者仍然收到回覆。Safety Evaluator 目前是 deterministic 關鍵字規則
（停藥、改藥、診斷等）。

RAG（`POST /api/v1/rag/retrievals`）是 Bedrock query embedding ＋ OpenSearch Hybrid
Search adapter。只有 `general_information`／`legal_reference` purpose 的回合會檢索，
成功時 3～5 個帶引用的 chunk 進入 Context Manifest，查無資料時**不呼叫模型猜測**。
治理 gate：Allowlist 尚未簽署，Human Review 未完成。僅在 staging 明確設定
`RAG_REQUIRE_OWNER_SIGNATURE=false` 才可用 unsigned development override；即使啟用，
外部 `RAG_ALLOWLIST_EXPECTED_SHA256` 精確比對與來源／chunk／數量驗證仍是不可略過的
hard gate，receipt 與 log 必須標記 `governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、
`production_approved=false`。Production 需正式簽署並明確設定 `RAG_PRODUCTION_ENABLED=true`。

回應與 core-api 共用 envelope（`{"data","meta"}` / `{"error"}`），見
[ADR 0005](docs/adr/0005-agent-runtime-api-conventions.md)。範圍見
[`docs/ownership/member-c-scope.md`](docs/ownership/member-c-scope.md)，架構見
[`docs/architecture/agent-runtime-overview.md`](docs/architecture/agent-runtime-overview.md)。

兩個 Python 服務各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。

## Frontend → Core → Agent 文字閉環

[`packages/frontend/`](packages/frontend/) 是唯一的前端：單一 multi-role PWA，
同時擔任 BFF（[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）。

```powershell
npm run dev       --workspace @elderly-care/frontend   # :3000
npm run test      --workspace @elderly-care/frontend   # 115 tests
npm run typecheck --workspace @elderly-care/frontend
```

瀏覽器只呼叫 Next.js 的同源 `/backend/core/*`；BFF 從 `HttpOnly` Cookie 取得 Access
Token，在**伺服器端**轉成 Core API 的 Bearer Header。瀏覽器 JavaScript 讀不到 token，
寫入請求另有同源 Origin／CSRF gate。Core 從可信認證 context 取得 actor／tenant，重新檢查
elder scope 與 `BASIC_VOICE` consent，建立 Voice Session 後才 server-to-server 呼叫
Agent Runtime。

這條目前是 **TEXT_ONLY fallback**——麥克風、ASR、WebSocket 與 TTS 尚未實作，前端會明確
顯示不可用，**不會把文字輸入冒充成語音辨識結果**。設定與 E2E 證據見
[`docs/handover/2026-08-01-frontend-core-agent-integration.md`](docs/handover/2026-08-01-frontend-core-agent-integration.md)。

視覺、RWD 與無障礙規範見 [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md)，
**建立任何頁面前先讀**（元件內不得出現 raw hex，§14）。

## API Contract

[`contracts/`](contracts/) 放 OpenAPI 3.1、AsyncAPI 與 JSON Schema。core-api 合約涵蓋
51 個 operations，agent-runtime 3 個。Handoff、Context Manifest、Safety Evaluation 與
Tool schema 中仍有尚未接上 executable endpoint 的目標形狀。

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
```

契約**以目前實作為準**，與規格文件 10 有實質差異（envelope 結構、錯誤欄位、狀態碼對應），
差異清單在 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md)，尚未決定往哪邊收斂。
**改 contract 前先讀那份清單。**

## Database Migration（Alembic）

```powershell
# 用 Docker（不需本機 Python）
docker compose run --rm migrate                     # upgrade head
docker compose run --rm migrate alembic current

# 用本機 uv
cd services/core-api
uv run alembic upgrade head
uv run alembic downgrade base    # 砍掉整個 eldercare_ai schema
```

連線字串取自 `DATABASE_URL`，只維護一份且統一寫成 **asyncpg** 形式。應用層直接用；
Alembic 走同步連線，`alembic/env.py` 自行換成 psycopg——刻意保留兩個 driver
（[ADR 0003](docs/adr/0003-core-api-framework-and-schema-authority.md)）。

新增 migration：

```powershell
cd services/core-api
uv run alembic revision -m "PROJ-123 add xxx table"
```

**`--autogenerate` 目前不能直接採用**：v0.1 baseline 來自手寫 SQL，48 張 baseline table
中只有 33 張有 SQLAlchemy model，autogenerate 會把未映射的 table 誤判為應刪除。必須人工
撰寫或逐項審查，不得套用自動產生的 drop（[ADR 0002](docs/adr/0002-alembic-baseline-strategy.md)）。

已套用的 migration 視為不可變。要改 schema 就新增 revision，不要動 baseline。

[`docs/project/smart_eldercare_schema_v0_1.sql`](docs/project/smart_eldercare_schema_v0_1.sql)
是設計產出物，也是匯入 DBeaver／DataGrip 看 ER 圖的來源。它的逐位元副本凍結在
`services/core-api/alembic/versions/sql/`，**那份才是套用到資料庫的權威版本**，每次
upgrade 前驗證 SHA-256。注意檔名叫 `smart_eldercare_schema_v0_1`，但它建立的 PostgreSQL
schema 名稱是 `eldercare_ai`。

## AWS Infrastructure

[`infra/`](infra/)：AWS CDK v2，canonical staging stacks（[ADR 0007](docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)）。

```powershell
cd infra
npm run test      # 11 tests
npm run synth     # foundation stack
npm run diff
```

Cognito 是**外部管理**的既有 user pool，stack 只透過 CfnParameter／SSM 引用，不自己建立。
目前狀態與邊界見 [`infra/README.md`](infra/README.md)。

## Kiro 開發紀錄

專案以 Kiro 做 spec-driven 開發，紀錄保留在：

- [`.kiro/specs/`](.kiro/specs/)：requirements、design、tasks 與 task execution metadata
- [`.kiro/hooks/`](.kiro/hooks/)：spec traceability、測試、migration 與文件同步檢查
- [`.kiro/steering/`](.kiro/steering/)：**只轉發 `AGENTS.md`，不重述規則**。原本 5 個
  steering 檔已於 2026-08-06 併回 `AGENTS.md`，避免兩份規則互相漂移
- [`docs/project/kiro-development-evidence.md`](docs/project/kiro-development-evidence.md)：
  commit provenance 與證據邊界

歷史 Spec 是開發過程紀錄，**不取代**目前的 `AGENTS.md`、產品規格、contracts 與 ADR。

## 文件導覽

| 想知道 | 看哪裡 |
| --- | --- |
| 開發規則與不可違反的邊界 | [`AGENTS.md`](AGENTS.md) |
| 產品規格（17 份） | [`docs/spec/`](docs/spec/) |
| 技術決策與理由 | [`docs/adr/`](docs/adr/) |
| Agent Runtime 架構 | [`docs/architecture/`](docs/architecture/) |
| 視覺與無障礙規範 | [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md) |
| 契約與實作的已知差異 | [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) |
| AWS 存取與維運 | [`docs/runbooks/`](docs/runbooks/) |
