# kinsun.ai

<p align="center">
  <img src="docs/assets/readme/kinsun-hero.png" alt="小暖陪伴角色與 kinsun.ai 使用情境" width="720" />
</p>

<p align="center"><i>「小暖陪你聊生活，也陪你安心過每一天。」</i></p>

Voice-first 智慧長照 AI 陪伴系統。長者以語音互動，系統從對話中擷取生活事件、產生每日摘要，
供照服員覆核、家屬檢視。核心設計原則是**模型輸出只能是候選**——未經長者確認的記憶與未經
人工覆核的事件，都不得成為正式照護事實。

規則與邊界見 [`AGENTS.md`](AGENTS.md)，產品規格見 [`docs/spec/`](docs/spec/)。
新協作者請先依 [`docs/project/COLLABORATOR_SETUP.md`](docs/project/COLLABORATOR_SETUP.md)
完成工具、ENV、資料庫與本機服務建置。

## 開發理念

- **科技輔助而不取代照護**：AI 整理與提示候選資訊，最終判斷仍由長者與照護人員完成。
- **語音優先、清楚可及**：以自然對話降低操作門檻，介面同時遵守大字、對比與觸控尺寸規範。
- **安全與可追溯優先**：身份、同意、租戶隔離、人工覆核與稽核紀錄都是主流程的一部分。

## 現在能跑什麼

| 單元 | 狀態 |
| --- | --- |
| `services/core-api` | ✅ 主線。Direct Google／LINE OIDC、Core App Session、Identity、Elder 授權、Consent、Voice Ticket／ASR gate、Care Event、Memory、Daily Summary、Family Report、LINE 與 transactional outbox |
| `services/agent-runtime` | ✅ 單輪 Agent 閉環可跑；預設 deterministic mock，也可切換 Bedrock 或 provider-neutral OpenAI-compatible provider |
| `packages/frontend` | ✅ Multi-role PWA + BFF；文字與語音主線、麥克風錄音、角色動畫及 LINE 帳號連結已接入 |
| `services/rag-ingestion` | ⚠️ staging-only；治理簽章與 production gate 尚未完成，不可視為正式照護知識來源 |
| `services/speech-gateway` | ✅ 已接入語音主線；華語／英語使用 AWS managed speech，台語／客語可接私有 SageMaker endpoint |
| `infra` | ⚠️ 保留 AWS CDK deployment profile；黑客松 AWS 帳號目前無法操作，不能視為可部署或仍在使用的環境 |

CI workflow 目前仍停用；本機已有 Ruff／ESLint、TypeScript typecheck、單元測試、合約驗證與
production build。Core integration test 與完整 E2E 仍需要 PostgreSQL 或對應的外部服務環境。
`.github/workflows-disabled/pr.yml` 是未啟用的歷史草稿，見 `AGENTS.md` §1。

## 小暖｜陪伴角色

小暖不是醫療診斷機器人，而是以傾聽、鼓勵、提醒與陪伴為核心的數位角色。前端的
[`CompanionCharacter`](packages/frontend/src/components/voice/CompanionCharacter.tsx) 會依互動狀態
切換動畫；相關 runtime 素材保留在 [`packages/frontend/public/`](packages/frontend/public/)，
README 主視覺則獨立放在 [`docs/assets/readme/`](docs/assets/readme/)，避免文件圖片影響產品資產。

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

目前外部資料庫 provider 是 **Supabase PostgreSQL**，但程式只依賴標準 PostgreSQL／asyncpg
連線字串與 Alembic，不使用 Supabase Auth 或專有資料 API。本節的 Docker PostgreSQL 是可替換的本機環境。

| 項目 | 值 |
| --- | --- |
| Host / Port | `localhost:5432`（`POSTGRES_PORT` 可改） |
| Database | `kinsun`（測試用 `kinsun_test`） |
| User / Password | `kinsun` / `kinsun_local_dev` |
| 版本 | PostgreSQL 16（對齊 Aurora Serverless v2） |

### 起四個服務

```powershell
# Core API :8000
cd services/core-api;    uv sync --extra test --extra dev; uv run uvicorn app.main:app --reload

# Agent Runtime :8001（預設 mock provider 不需 AWS 憑證或網路）
cd services/agent-runtime; uv sync --extra test --extra dev
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001

# Speech Gateway :8002（雲端 ASR／TTS 需對應 AWS 設定）
cd services/speech-gateway; uv sync --extra test --extra dev
uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002

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
uv run pytest tests/unit          # 不需資料庫
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
uv run pytest              # 預設不需資料庫、AWS 憑證或網路
uv run ruff check .
```

閉環是 `POST /api/v1/agent/runs` → contract 驗證 → Orchestrator → Companion Agent →
Safety Evaluator → 回應。本機預設走 `MockModelProvider`，讓測試與開發可重現；需要真實推論時，
可由環境設定切換 Bedrock，或以 provider-neutral OpenAI-compatible adapter 連到相容的本機服務／
Google Gemini API。Core 的 `BASIC_VOICE` 路徑可在重驗授權與長期記憶 Consent 後，
帶入最多 5 筆 current ACTIVE Confirmed Memory；Knowledge／RAG purpose 不會混入私人記憶。
目前只按更新時間做有界選取，尚未有語意相關性排序。RAG 仍受 allowlist、簽章與 production gate 約束。

Candidate 採 Core-owned proposal flow：Runtime 可回傳不含 scope／source ID 的 Event proposal，
以及明確固定早餐習慣的 bounded Memory proposal。Core 先建立待覆核 Event，Memory proposal 只私下
綁在該版本；照護者 VERIFY 事件且 Core 重驗長期記憶 Gate 後，才建立仍須長者本人確認的
Memory Candidate。Runtime 不直接寫 Domain DB。

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

## Frontend → Speech Gateway → Core → Agent 閉環

[`packages/frontend/`](packages/frontend/) 是唯一的前端：單一 multi-role PWA，
同時擔任 BFF（[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）。

```powershell
npm run dev       --workspace @elderly-care/frontend   # :3000
npm run test      --workspace @elderly-care/frontend
npm run typecheck --workspace @elderly-care/frontend
```

瀏覽器只呼叫 Next.js 的同源 `/backend/core/*`；BFF 從 `HttpOnly` Cookie 取得 Core-owned opaque
App Session，在**伺服器端**轉成 Core API 的 Bearer Header。瀏覽器 JavaScript 讀不到 credential，
寫入請求另有同源 Origin／CSRF gate。Core 從可信認證 context 取得 actor／tenant，重新檢查
elder scope 與 `BASIC_VOICE` consent，建立 Voice Session 後才 server-to-server 呼叫
Agent Runtime。

語音主線會由瀏覽器錄製 16 kHz mono PCM，交給 Speech Gateway 做 ASR；Core 驗證 voice ticket、
身份、elder scope、consent 與 ASR gate 後，才建立 Voice Session 並呼叫 Agent Runtime，最後再由
Speech Gateway 合成語音。華語／英語走 AWS managed services；台語／客語走設定的私有 SageMaker
endpoint，未設定時會明確失敗，**不會靜默改用華語**。文字路徑保留為獨立的無障礙 fallback。

視覺、RWD 與無障礙規範見 [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md)，
**建立任何頁面前先讀**（元件內不得出現 raw hex，§14）。

## Speech Gateway

[`services/speech-gateway/`](services/speech-gateway/) 封裝 ASR／TTS、語言路由、Core voice gate 與
SageMaker adapter。低資源語言的模型選擇、endpoint contract 與部署證據見
[`services/speech-gateway/docs/`](services/speech-gateway/docs/)；服務在缺少必要 endpoint 時採
fail-closed，不宣稱已提供不可用的語言能力。

## LINE 整合

Core API 負責 LINE webhook、帳號連結、身份解析與家屬每日摘要通知；Frontend 提供登入 callback
與 account-link 頁面。原始 LINE user ID 不以明文持久化，查找使用 keyed digest，需要推播的目的地
則以 authenticated encryption 保存。Rich Menu 素材位於
[`packages/frontend/public/line/`](packages/frontend/public/line/)。

## API Contract

[`contracts/`](contracts/) 放 OpenAPI 3.1、AsyncAPI 與 JSON Schema。Handoff、Context Manifest、
Safety Evaluation 與 Tool schema 中仍有尚未接上 executable endpoint 的目標形狀；實際數量由
下列驗證指令與目前 contract 檔案決定，不在 README 固定容易過期的數字。

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

## Infrastructure

[`infra/`](infra/) 保留 AWS CDK v2 deployment profile（[ADR 0007](docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)）。
黑客松 AWS 帳號目前已無法操作；repository 內的 stack 只能代表可 synth 的 IaC，不代表資源仍存在、
可存取或正在計費。Cognito 已從 runtime、前端與 IaC 移除，登入改走 direct Google／LINE OIDC +
Core App Session。現行資料庫是 Supabase PostgreSQL；未來 deployment provider 必須透過環境變數與
adapter 邊界接入，不把 Domain Core 綁在單一雲端服務。

```powershell
cd infra
npm run test      # 7 tests
npm run synth     # foundation stack
npm run diff
```

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
| 新協作者工具、ENV 與本機建置 | [`docs/project/COLLABORATOR_SETUP.md`](docs/project/COLLABORATOR_SETUP.md) |
| 產品規格（17 份） | [`docs/spec/`](docs/spec/) |
| 技術決策與理由 | [`docs/adr/`](docs/adr/) |
| Agent Runtime 架構 | [`docs/architecture/`](docs/architecture/) |
| 視覺與無障礙規範 | [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md) |
| 契約與實作的已知差異 | [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) |
| AWS 存取與維運 | [`docs/runbooks/`](docs/runbooks/) |
