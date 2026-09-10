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

以下為 2026-09-10 的程式與本機驗證狀態，不代表 production 已部署。

| 單元 | 狀態 |
| --- | --- |
| `services/core-api` | ✅ 主線。Email／Password、選用 Google／LINE OIDC、Core App Session、Elder 授權、Consent、Voice Ticket／ASR gate、Care Event、Memory、Daily Summary、Care Action、Assignment／Service Record、Family Report、LINE 與 transactional outbox |
| `services/agent-runtime` | ✅ 單輪 Agent 閉環可跑；預設 deterministic mock，也可切換明確設定的 model provider |
| `packages/frontend` | ✅ Multi-role PWA + BFF；文字／語音介面、角色動畫、LINE 帳號連結，以及照護 Dashboard、事件覆核、照護行動與服務紀錄輸入 |
| `services/rag-ingestion` | ⚠️ staging-only；治理簽章與 production gate 尚未完成，不可視為正式照護知識來源 |
| `services/speech-gateway` | ⚠️ 已有語音主線與 provider adapters；目前沒有已部署的雲端 ASR／TTS provider，未設定時 fail closed |

Gate 1 CI 已啟用，涵蓋四個 Python 元件、Core PostgreSQL integration、contracts、五輪 synthetic
Core-to-Agent evidence 與 Frontend production build；完整自動化 browser／外部部署 E2E 仍未建立。
RAG 已完成 Supabase 開發資料同步及「長照法」「長照法第二條」本機瀏覽器文字問答驗收；
仍屬 staging-only，詳見下方 RAG 說明。

### CI 執行方式

- 八個獨立 jobs：`core-fast`、`core-db`、`agent-quality`、`speech-quality`、`rag-quality`、
  `contracts`、`cross-service`、`frontend-quality`；只有 `core-db` 啟動測試 PostgreSQL。
- PR 的 `changes` job 依影響範圍選擇 jobs；未知路徑或不完整 diff 回退全跑。合併後的 `main` push 仍全跑。
- `synthetic-gate1` 是永遠執行的 aggregate gate：選定 jobs 必須成功且有 metrics；只有計畫排除的
  jobs 可略過，失敗、取消、意外略過或缺少結果皆不可放行。這不等於 GitHub 已設定合併保護。
- 收集 job／step、命令與測試耗時；平行 job 秒數不能相加當作整體等待時間。

設定與量測方式見 [CI 優化紀錄](docs/project/ci-pipeline-optimization.md)及
[workflow](.github/workflows/gate1.yml)。

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
├── packages/       frontend（PWA＋BFF）、shared（TypeScript 型別）
├── scripts/        contract 與 repository 驗證腳本
└── services/       core-api、agent-runtime、rag-ingestion、speech-gateway
```

分類軸線是 **runtime**：Python 服務進 `services/`、npm workspace 進 `packages/`。
不是 Turborepo 的 apps／packages 慣例（`services/core-api` 同樣可部署卻不在 `apps/`）。
完整說明見 `AGENTS.md` §9。

## 快速開始

### 需求

- [uv](https://docs.astral.sh/uv/)（本機跑 Python 服務與 Alembic）
- Python 3.12（可由 uv 安裝）
- Node.js ≥ 20.9
- 已授權的 Supabase 開發資料庫連線；Docker Desktop／Compose v2 只用於明確選用的隔離環境

### 安裝與環境設定

```powershell
npm ci
uv sync --frozen --project services/core-api --extra test --extra dev
uv sync --frozen --project services/agent-runtime --extra test --extra dev
uv sync --frozen --project services/speech-gateway --extra test --extra dev
uv sync --frozen --project services/rag-ingestion --extra test --extra dev
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path packages/frontend/.env.local)) {
  Copy-Item packages/frontend/.env.example packages/frontend/.env.local
}
```

以上從 repository 根目錄執行，已有 ENV 檔案不得覆寫。將 root `.env` 的 `DATABASE_URL`
改成 Owner 提供的 Supabase 開發連線，採 `postgresql+asyncpg://` 形式；不要直接使用 example
中的 localhost 值。Next.js 另讀 `packages/frontend/.env.local`，不會自動沿用 root `.env`。
所有密碼、驗證碼與 provider secrets 只經安全管道交付，不進 Git。

預設開發直接使用 **Supabase PostgreSQL**，不啟動 Docker 或本機 PostgreSQL；不使用 Supabase
Auth 或專有資料 API。Migration 檢查與 additive upgrade 見下方章節；一般啟動不重建資料庫。
`TEST_DATABASE_URL` 必須另指向獨立、可丟棄的測試資料庫，不能拿 Supabase 開發庫代替。

瀏覽器登入以 Kinsun Email／Password 為主，Google／LINE OIDC 為選配。Example 中相關 gates
預設關閉；`FAKE_AUTH_ENABLED=true` 只能供直接 Core API 開發，不會建立瀏覽器 Session。
登入所需設定與 synthetic 帳號使用邊界見 [建置指南](docs/project/COLLABORATOR_SETUP.md)。

### 啟動服務

每個服務使用獨立 PowerShell terminal，且各自從 repository 根目錄執行對應指令。

```powershell
# Terminal 1：Agent Runtime :8001（預設 mock 不需雲端憑證）
.\scripts\ide\run-local.ps1 -Target agent-runtime

# Terminal 2：Core API :8000
.\scripts\ide\run-local.ps1 -Target core-api

# Terminal 3：Frontend :3000
.\scripts\ide\run-local.ps1 -Target frontend

# Terminal 4：Speech Gateway :8002（選配，文字測試不需要）
.\scripts\ide\run-local.ps1 -Target speech-gateway
```

這些啟動命令不會建立資料庫或自動啟用登入、RAG、ASR／TTS provider。
其他作業系統可使用 [建置指南](docs/project/COLLABORATOR_SETUP.md)中的等價 uv／npm 命令。

### 選用 Docker 隔離環境

只有明確要求可丟棄的本機隔離環境時，才使用 `docker-compose.yml`；步驟見
[建置指南](docs/project/COLLABORATOR_SETUP.md)。它不是預設開發或登入測試流程。
`docker compose down` 保留資料 volume；`docker compose down -v` 會刪除資料，不能作為例行啟停指令。

### Schema 從哪來

分兩層，不要混：

- `docker/postgres/init/` 只建立 extension（`pgcrypto`、`citext`）與測試資料庫，**不建表**。
  僅供 Docker 隔離環境，且只在資料 volume 為空時執行一次，不應靠刪除 volume 更新正式 schema。
- **所有 table／index／constraint／trigger 由 Alembic 管理**；Domain schema 是 `eldercare_ai`，
  另有受 Alembic 管理的 `rag_public` 與 `service_identity`。

## Core API

[`services/core-api/`](services/core-api/)：FastAPI ＋ SQLAlchemy 2.0 async。

```powershell
cd services/core-api
uv run pytest tests/unit          # 不需資料庫
uv run ruff check .
uv run ruff format --check .
```

Integration 會 drop／rebuild／清理資料，只可在已確認的獨立 disposable `TEST_DATABASE_URL`
執行；沒有就略過。不得對 Supabase 開發庫或其他共享／production DB 執行。
Migration lifecycle 必須先在獨立 pytest process 執行，成功後才跑其餘 integration：

```powershell
# 從 services/core-api 執行；先確認 TEST_DATABASE_URL 是可丟棄的測試庫
uv run pytest tests/integration/test_migrations.py
# 僅在上一支成功後執行
uv run pytest tests/integration --ignore=tests/integration/test_migrations.py
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
uv run pytest              # 預設不需資料庫、雲端憑證或網路
uv run ruff check .
```

閉環是 `POST /api/v1/agent/runs` → contract 驗證 → Orchestrator → Companion Agent →
Safety Evaluator → 回應。本機預設走 `MockModelProvider`，讓測試與開發可重現；需要真實推論時，
可由環境設定切換 Google Gemini 或 provider-neutral OpenAI-compatible adapter；Bedrock adapter
仍保留為明確 opt-in 的 legacy option，但目前沒有 AWS deployment。Core 的 `BASIC_VOICE` 路徑可在
重驗授權與長期記憶 Consent 後，
帶入最多 5 筆 current ACTIVE Confirmed Memory；Knowledge／RAG purpose 不會混入私人記憶。
目前只按更新時間做有界選取，尚未有語意相關性排序。RAG 仍受 allowlist、簽章與 production gate 約束。

Candidate 採 Core-owned proposal flow：Runtime 可回傳不含 scope／source ID 的 Event proposal，
以及明確固定早餐習慣的 bounded Memory proposal。Core 先建立待覆核 Event，Memory proposal 只私下
綁在該版本；照護者 VERIFY 事件且 Core 重驗長期記憶 Gate 後，才建立仍須長者本人確認的
Memory Candidate。Runtime 不直接寫 Domain DB。

**安全阻擋回的是 200 不是錯誤**：`data.result_status` 為 `BLOCKED`、`data.reply_text`
換成安全訊息，長者仍然收到回覆。Safety Evaluator 目前是 deterministic 關鍵字規則
（停藥、改藥、診斷等）。

RAG 保留 `POST /api/v1/rag/retrievals` 相容路徑，Agent 內部改用
`POST /api/v2/rag/retrievals` 的完整治理 citation contract。現行 target／已驗證資料面是 Google
query embedding ＋ Supabase PostgreSQL FTS／trigram＋pgvector hybrid search；OpenSearch／Bedrock
只保留為顯式 opt-in legacy adapters，沒有 live AWS evidence。只有 `general_information`／
`legal_reference` purpose 的回合會檢索，
成功時 3～5 個帶引用的 chunk 進入 Context Manifest，查無資料時**不呼叫模型猜測**。
治理 gate：staging review／Owner acceptance 不等於正式簽章或 production approval。僅在 staging 明確設定
`RAG_REQUIRE_OWNER_SIGNATURE=false` 才可用 unsigned development override；即使啟用，
外部 `RAG_ALLOWLIST_EXPECTED_SHA256` 精確比對與來源／chunk／數量驗證仍是不可略過的
hard gate，receipt 與 log 必須標記 `governance_status=UNSIGNED_DEVELOPMENT_OVERRIDE`、
`production_approved=false`。目前 runtime 的 production 核准 RAG modes 清單仍為空，
不能只設定 `RAG_PRODUCTION_ENABLED=true` 就視為可上線。
V2 另需明確設定 `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true` 才會讓 staging 讀取
`needs_review` citation；這不會授予 production approval。

2026-09-10 經獨立授權，已將 successor release `rag-v2-v004-f3339ceae77c` 的 726 筆 projection
與既有向量同步至 Supabase 開發庫，獨立讀回核對通過；僅 71 筆法規治理 metadata 修正，文字、
其他限制與舊 release 保留。本機 Agent 已切換對應 v004 runtime policy，瀏覽器文字輸入
「長照法」「長照法第二條」均為 `SUCCESS / ALLOW`，並確認引用與固定的專業諮詢提醒。

同步、驗收與安全回復條件見 [RAG 修復紀錄](docs/project/rag-law-governance-sync-plan-20260909.md)。
這是特定 synthetic 帳號與問題的本機驗收，不是真機語音或外部部署 E2E，也不代表全部法規問答
品質已驗證。375px 驗收仍記錄約 3 CSS px 水平溢出。獨立 read-only DB principal、完整 live
relevance／ranking evaluation 與 production 核准仍未完成。

回應與 core-api 共用 envelope（`{"data","meta"}` / `{"error"}`），見
[ADR 0005](docs/adr/0005-agent-runtime-api-conventions.md)。範圍見
[`docs/ownership/member-c-scope.md`](docs/ownership/member-c-scope.md)，架構見
[`docs/architecture/agent-runtime-overview.md`](docs/architecture/agent-runtime-overview.md)。

四個 Python 元件各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。

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
Speech Gateway 合成語音。Repository 保留多個可替換 provider adapter，但目前沒有已部署的雲端
ASR／TTS provider；未設定時會明確失敗，**不會靜默改用另一種語言或 provider**。文字路徑保留為
獨立的無障礙 fallback。

視覺、RWD 與無障礙規範見 [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md)，
**建立任何頁面前先讀**（元件內不得出現 raw hex，§14）。

## Speech Gateway

[`services/speech-gateway/`](services/speech-gateway/) 封裝 ASR／TTS、語言路由、Core voice gate 與
可替換 provider adapters。低資源語言的歷史模型選擇、endpoint contract 與 Hackathon 證據見
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

先確認 root `.env` 指向已授權的開發資料庫，唯讀檢查 revision 並人工審查待套用 migration。
只有確認後才執行 additive upgrade；不是每次啟動都需要 migration。

```powershell
cd services/core-api
uv run alembic current
uv run alembic heads
# 人工審查與確認後才執行
uv run alembic upgrade head
```

禁止對 Supabase 開發庫或其他共享／production DB 執行 `downgrade base`、reset、truncate 或空庫
重建。破壞性的 migration roundtrip 僅能在獨立 disposable 測試庫執行。

連線字串取自 `DATABASE_URL`，只維護一份且統一寫成 **asyncpg** 形式。應用層直接用；
Alembic 走同步連線，`alembic/env.py` 自行換成 psycopg——刻意保留兩個 driver
（[ADR 0003](docs/adr/0003-core-api-framework-and-schema-authority.md)）。

新增 migration：

```powershell
cd services/core-api
uv run alembic revision -m "PROJ-123 add xxx table"
```

**`--autogenerate` 目前不能直接採用**：v0.1 baseline 來自手寫 SQL，ORM metadata 不涵蓋所有
Alembic 管理的資料表（包含 `rag_public`、`service_identity`），會把未映射的 table 誤判為應刪除。必須人工
撰寫或逐項審查，不得套用自動產生的 drop（[ADR 0002](docs/adr/0002-alembic-baseline-strategy.md)）。

已套用的 migration 視為不可變。要改 schema 就新增 revision，不要動 baseline。

[`docs/project/smart_eldercare_schema_v0_1.sql`](docs/project/smart_eldercare_schema_v0_1.sql)
是設計產出物，也是匯入 DBeaver／DataGrip 看 ER 圖的來源。它的逐位元副本凍結在
`services/core-api/alembic/versions/sql/`，**那份才是套用到資料庫的權威版本**，每次
upgrade 前驗證 SHA-256。注意檔名叫 `smart_eldercare_schema_v0_1`，但它建立的 PostgreSQL
schema 名稱是 `eldercare_ai`。

## Deployment

現行資料庫是 Supabase PostgreSQL，repository 目前沒有 production IaC，也沒有使用中的 AWS
deployment。舊 AWS CDK profile 已由
[ADR 0019](docs/adr/0019-retire-aws-cdk-deployment-profile.md) 正式退役；歷史 AWS spec／ADR 只作為
設計與決策紀錄。未來 hosting provider 必須先經 ADR 定案，再透過環境變數與 adapter 邊界接入，
不把 Domain Core 綁在單一雲端服務。

仍可在本機建立四個 portable runtime images：

```powershell
./scripts/build_runtime_images.ps1 `
  -ReleaseId <git-sha> `
  -ConsentPolicyVersion <policy-version>
```

這只建立並檢查本機 OCI images，不會 push registry 或部署資源。外部環境 smoke test 見
[`docs/runbooks/deployment-smoke.md`](docs/runbooks/deployment-smoke.md)。

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
| 產品規格 | [`docs/spec/`](docs/spec/) |
| 技術決策與理由 | [`docs/adr/`](docs/adr/) |
| Agent Runtime 架構 | [`docs/architecture/`](docs/architecture/) |
| 視覺與無障礙規範 | [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md) |
| 契約與實作的已知差異 | [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) |
| 外部部署驗證 | [`docs/runbooks/deployment-smoke.md`](docs/runbooks/deployment-smoke.md) |
| CI 選擇性執行與耗時指標 | [`docs/project/ci-pipeline-optimization.md`](docs/project/ci-pipeline-optimization.md) |
| RAG 法規修復、驗收與安全回復 | [`docs/project/rag-law-governance-sync-plan-20260909.md`](docs/project/rag-law-governance-sync-plan-20260909.md) |
