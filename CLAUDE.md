# CLAUDE.md

- 更新日期：2026-08-17
- 校準基準：`main` at `a2af73e`
- 適用範圍：整個 `kinsun.ai` repository

本檔定義 Claude 在本專案中的工作流程、檢查順序與交付格式。完整架構、安全、Contract、
資料庫與測試規則以根目錄 [`AGENTS.md`](AGENTS.md) 為準；進入
`services/agent-runtime/` 時還要讀取該目錄的 [`AGENTS.md`](services/agent-runtime/AGENTS.md)。
競賽題目、Persona、Story Map 與各領域規格在 [`docs/spec/`](docs/spec/)；不要把本檔當產品規格。

## 每次工作固定流程

1. 先確認工作區，不覆蓋使用者既有變更。

   ```powershell
   git -c safe.directory=D:/Hackthon/kinsun.ai status --short
   git -c safe.directory=D:/Hackthon/kinsun.ai log -5 --oneline
   ```

   開發與登入／註冊 E2E 預設由 repository 根目錄 `.env` 的 `DATABASE_URL` 直接連 Supabase
   PostgreSQL；不要啟動 Docker、`docker compose` 或本機 PostgreSQL，除非使用者明確要求。
   Supabase 不得執行 integration reset、`downgrade base` 或空庫重建；這些驗證必須使用獨立、
   可丟棄的 `TEST_DATABASE_URL`，沒有就略過並回報。

2. 讀根目錄 `AGENTS.md`、目前目錄適用的巢狀 `AGENTS.md`，再讀與需求直接相關的 spec、ADR、
   contract、migration、測試與實作。若文件和程式衝突，先以可執行 contract、migration、測試與
   code path 建立證據，再修正文件；不要靠 README 或檔名猜進度。
3. 把需求拆成 Persona、User Story、Acceptance Criteria、Domain State、Security Gate、Test Gate。
   明確區分「目標架構」、「程式已實作」、「測試已通過」與「環境已部署」。
4. 追完整資料流：Browser/BFF → Core Command Gate → DB/Outbox → Agent、Speech、RAG 或通知邊界。
   涉及寫入時，一併檢查授權、Consent、狀態機、idempotency、audit 與 failure path。
5. 先做最小、可回復的變更，再跑受影響元件測試；跨 contract、migration 或共用套件時擴大驗證。
6. 交付前檢查 diff、更新必要文件，並清楚列出已驗證與因環境限制未驗證的項目。

```text
需求 → 實作證據 → Contract／State／Security 影響 → 最小修改 → 目標測試 → 跨層檢查 → 交付
```

## 實作時的對齊規則

### Core API 與資料庫

- `services/core-api` 是 Domain authority。Route 只處理傳輸；authorization、Consent、state transition
  與 business rule 放 service；資料存取經 repository；跨系統通知先寫 transactional outbox。
- 以解析後的 `Identity`／`Actor` 為權限依據，不信任 Client 傳入的 tenant、elder、role、assignment
  或 permission scope。email 不是 Actor authority，也不得用 email 自動合併帳號。
- Kinsun-owned Email＋Password primary flow、Direct Google／LINE OIDC、Core App Session、pending onboarding、explicit Google→LINE linking 與
  bounded empty-account consolidation 已有 application code。Cognito runtime、SDK、Hosted UI callback、
  IaC reference 與 actor legacy identity 已移除；committed example gates 預設關閉。不得把「本機可登入」
  寫成「雲端環境已部署驗證」。
- Baseline migration 已凍結；新增 schema 只加新的 Alembic revision，不改寫既有 migration。
  2026-08-17 工作樹基準為 19 個 revisions、48 張 baseline tables 中 43 張已有 SQLAlchemy mapping。
  model attribute `id` 常透過 `__pk_name__` 對應 DB 的領域主鍵，不要把欄位名稱不同誤判成 schema drift。
- 不用未經檢查的 autogenerate。migration SQL 維持 LF、可重建、可升級，並保留 RLS、grant、trigger、
  constraint 與 state-machine 規則。

### Agent Runtime

- Runtime 只產生不可信 proposal；Core 重新授權、重驗 Consent 並建立 review-required Candidate。
  canonical flow 由 Core 傳 `requested_outputs`，`allowed_tools` 固定空陣列；Runtime 不 callback Core、
  不完成 AgentRun、也不寫 Domain DB。
- bounded Memory first slice 只擷取明確固定早餐習慣：Runtime proposal 不含 scope／source ID；Core
  先把它私下綁在 Care Event version，照護者 VERIFY 事件後再重驗 `memory:candidate:create` 與
  `LONG_TERM_MEMORY` Consent，建立仍須長者本人以 `ELDER_UI` 確認才可 ACTIVE 的 Candidate。這是
  Current first slice；Target 依 Spec 18／ADR 0014 改為 Agent proposal＋Core deterministic policy＋
  Speaker Gate：LOW all-of 可自動保存、MEDIUM 對固定 version／digest 由 Elder UI／Voice 確認、HIGH
  零 Memory row。Staff witness 不能取代 Elder consent，且 Care Event 與 Memory 不再硬性綁定。
- 預設與 staging application template 使用 mock。文字生成可明確選 `bedrock`、`gemini` 或
  `openai-compatible`。原生 `gemini` provider 使用 Google Gen AI SDK，`AQ.` 開頭的 Vertex AI
  Express key 走 Vertex AI，其他 key 走 Gemini Developer API；`openai-compatible` 只依 runtime
  URL／model／optional Bearer key。provider 錯誤時都不會 fallback 到 mock。RAG Retriever 已改由
  provider-neutral `SearchBackend` 接收不含 executable DSL 的 bounded plan；query embedding 由
  `EmbeddingProvider` 隔離，已有 Bedrock 與 opt-in Google query adapters。Core 已新增並以本機
  pgvector integration tests 驗證 `rag_public` schema 與 17 sources／726 candidate chunks 的
  deterministic、idempotent staging projection importer。2026-08-25 已對目前 Supabase development
  database 套用 migration `e6f8a0b2c345`，並匯入 release `rag-v2-v002-bab68588963b`；遠端讀回為
  17 sources、726 chunks、全部 record/text/embedding-text hash 一致、`needs_review=726`、
  `production_approved=0`。2026-08-25 已使用確認的 Google
  `gemini-embedding-001`／1024／`RETRIEVAL_DOCUMENT` profile 產生 726 成功、0 失敗的 repository 外
  staging artifact，SHA-256 為
  `599d194db552433710ec6aff69318e962cb5b4b1c9f7a3050d527b369a3df7d5`；經使用者確認後已以單一
  transaction 匯入 726 document embeddings，Supabase 獨立讀回的 profile、embedding-text hash 與
  vector fingerprint 全部 `VERIFIED`。2026-08-25 已新增全參數化、固定模板的 PostgreSQL
  FTS／trigram＋pgvector hybrid `SearchBackend`，可由 `RAG_SEARCH_BACKEND=postgresql` 精確綁定
  release／profile；Supabase data-plane smoke 與 Google `RETRIEVAL_QUERY` → Supabase → V2 citation
  smoke 均回傳 5 筆 staging chunks。現行只有 14 筆 official/public chunks 通過普通 RAG filter，
  metadata 都只允許 `care_professional`；2026-08-25 經 owner 明確要求，本機 development 以
  `RAG_STAGING_ALLOW_ALL_AUDIENCES=true` 暫時開放有明確 audience 的 Elder／Family／Staff，且 Elder
  全鏈路 smoke 回傳 5 筆，Production 仍禁止此 override。這不代表 production deployment：獨立 read-only
  principal、Golden Query／quality gate、v003 Supabase sync、activation／rollback 尚未完成，retrieval 與
  Production 仍封鎖；legacy OpenSearch adapter 保留。
  2026-08-26 已依 Owner 明確人工確認，在 repository 內產生 immutable successor
  `data/rag-v3/candidates/v003/`：17 sources／726 chunks 全部 `review_status=verified`，文字與
  embedding text 均未變更，且 726／726 通過既有 embedding profile reuse 檢查；這是尚未同步的
  本機 staging candidate，Supabase 目前仍維持上述 v002／`needs_review=726`。
- 現行 `BASIC_VOICE` context 除本輪輸入外，可由 Core 在重驗 `memory:read` 與 active
  `LONG_TERM_MEMORY` Consent 後帶入最多 5 筆同 tenant／elder、current `ACTIVE` version 的
  Confirmed Memory；Knowledge／RAG purpose 由契約與 Core 雙重禁止夾帶私人記憶。這個 first slice
  仍未做語意相關性排序；Verified Care Data、Graph、Neptune、通用 Tool loop、Prompt Registry、
  Model Router 與完整 trace 仍未完成。
- Target Context 必須每次由 Core 重驗 current ACTIVE、Consent、Speaker ownership、risk verification、
  version-bound confirmation、validity、tenant／elder scope 與 tombstone；不得只因 legacy row、Graph、
  Search 或 cache 標示 ACTIVE 就放行。
- 保留 deterministic Safety Evaluator、step 上限、typed outputs、Pydantic／JSON Schema 一致性與
  no-guess fallback。不得讓 LLM 判斷取代 deterministic security gate。

### Frontend 與身份驗證

- 前端是 `packages/frontend` 的單一 multi-role Next.js 16 App Router PWA；不要重建已移除的
  `apps/elder-web`、`apps/care-web`、`apps/family-web`。
- Browser 只透過同源 BFF 呼叫後端；token、provider secret 與 session credential 不進 client bundle、
  URL、log 或錯誤訊息。新環境變數必須同步 `.env.example`，只放安全假值。
- Kinsun Email／Password 是 primary flow；BFF 以獨立 private credential 呼叫 Core，Browser 只收到
  HttpOnly Core App Session cookie。verification code／password 不得進 response 或 log；目前 delivery
  只允許 synthetic development mode，不能宣稱 production email 已上線。
- 使用既有 CSS Modules、design tokens 與 components；不要引入 Tailwind 或第二套 UI framework。
  使用者可見文字同步 `zh-TW` 與 `en`，至少檢查 375／390／430 px。
- 功能旗標預設關閉；未經明確授權，不啟用 direct OIDC、ASR、通知或其他 staging／production 功能。

### Speech、RAG 與通知

- Canonical voice flow 是 Browser JSON audio upload → Core Voice Ticket → Speech Gateway consume →
  Core server-side ASR Gate。低信心結果必須要求確認，不可直接成為 verified event 或 memory。
- Managed zh/en 與 SageMaker nan/hak adapters 已有 code/tests；真實 endpoint、service credential、
  WebSocket binary transport、quality／cost gate 尚未完成，不得宣稱 production-ready。
- `services/rag-ingestion` 與 Agent RAG 都是 staging-only。Allowlist、hash、來源、chunk 數、receipt 與
  human review 規則不得被繞過；unsigned development override 不是 production approval。
- `services/notification-worker` 目前只有 scheduler boundary README；工作邏輯仍在 Core，尚無獨立
  worker framework、Scheduler、SQS 或 DLQ deployment。`projection-worker`、`report-worker` 也不存在。

### Contract 與 IaC

- OpenAPI、AsyncAPI、JSON Schema、Pydantic model、實際 route 與 live verifier 必須一起演進。
  不可實作未登記 API；不相容變更必須有新 major version 或正式 migration plan。
- [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) 是差異說明，不是 executable truth，而且局部摘要
  可能落後；改動前後都跑 validator。2026-08-17 快照：Core OpenAPI 67 paths、Agent 3 paths、
  AsyncAPI 1 channel，Core app 實際 72 operations。
- `infra` 保留 AWS CDK v2 deployment profile；application stack 的 `desiredCount` 預設 0。黑客松 AWS
  帳號目前無法操作，Cognito 已從 IaC 移除，OpenSearch 仍是 external reference。沒有使用者明確要求
  與新的可操作帳號，不部署、不 push image、不變更 AWS resource，也不把 synth 結果描述成已上線。
- `.github/workflows-disabled/pr.yml` 代表 CI 目前停用；本機通過不等於 PR gate 已啟用。

## 驗證矩陣

只改文件時至少跑 `git diff --check`、檢查連結與 diff。程式變更依影響範圍執行下列命令。

### Core API

```powershell
cd services/core-api
uv sync --extra test --extra dev
uv run pytest tests/unit
uv run ruff check .
uv run ruff format --check .
```

Integration 與空庫 migration rebuild 只可使用獨立、可丟棄的 `TEST_DATABASE_URL`；不得為此啟動
Docker 或拿 Supabase development database 重建。一般 migration 直接連 Supabase，先跑唯讀
`alembic current`／`alembic heads` 並審查 migration，再做 additive `alembic upgrade head`。連線不可用
時，不要把 `/ready` 失敗混寫成 contract regression。

### Agent Runtime

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_agent_contract_live.py ../../contracts
```

`services/agent-runtime/tests/conftest.py` 必須在匯入 app 前固定 `APP_ENV=test`、
`MODEL_PROVIDER=mock`；不要讓本機 `.env` 選到的真實 provider 或 secret 汙染一般測試。

### RAG Ingestion 與 Speech Gateway

```powershell
cd services/rag-ingestion
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .

cd ../speech-gateway
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Frontend

```powershell
npm run test --workspace @elderly-care/frontend
npm run lint
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
```

有畫面或互動改動時，再做 375／390／430 px、keyboard、loading／empty／error、`prefers-reduced-motion`
與 feature-on／feature-off 視覺驗證。

### IaC 與 contracts

```powershell
npm run test --workspace @elderly-care/infrastructure
npm run typecheck --workspace @elderly-care/infrastructure
npm run synth --workspace @elderly-care/infrastructure
npm run synth:application --workspace @elderly-care/infrastructure

uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
```

2026-08-13 Cognito retirement 當次結果：Core unit 752、Frontend 135、Infra 7 tests passed；Core Ruff
lint、本次 Core 檔案 format、Frontend lint／typecheck／build、Infra typecheck／兩個 synth、static
contract 與 Core live verifier 均通過。Agent 259、RAG ingestion 138、Speech 22 是較早且未受本次變更
影響的結果。沒有獨立 `TEST_DATABASE_URL`，因此未重建 integration DB；Supabase 只在唯讀確認 legacy
欄位非空筆數為 0 後，套用 migration 至 `f2c6d8a1e490`。完整 Core format check 仍會指出兩個本次未
修改的既有檔案。這個快照只供回歸比較，不可取代當次驗證。

2026-08-17 Kinsun Email＋Password contract closure 當次結果：Core unit 808、Frontend 220 tests passed；
Frontend typecheck／production build、static contract 與 Core live verifier（72 operations）通過。完整
Frontend ESLint 仍有一個本次未修改的既有 unused argument，完整 Core Ruff 仍有兩個本次未修改的既有
問題。沒有獨立 `TEST_DATABASE_URL`，未重建 integration DB；本機 Docker 設定檔受執行環境權限限制，
`docker compose config --quiet` 未驗證。這個快照同樣不可取代當次驗證。

## 交付前自我審查

- `git diff` 只包含本次需求；沒有重寫或刪除使用者既有變更。
- 實作、contract、migration、測試、文件與 feature flag 敘述一致。
- 每個 write path 都有 actor、scope、Consent、state、idempotency、audit 與失敗路徑。
- 沒有真實長者資料、逐字稿、音訊、token、secret、endpoint credential 或敏感 log。
- SQLAlchemy 即使在 development 開啟 `echo` 也必須維持 `hide_parameters=True`；不得讓 Email、
  credential hash 或其他 bind parameter 進入本機／正式 log。
- 沒有把 mock、adapter、synth、disabled gate 或本機測試誤稱為已部署能力。
- 新增 API 有 schema 與 verifier；新增 state 有 migration 與 transition test；新增 UI 有雙語與 RWD。
- `git diff --check` 通過，必要測試已跑；未跑項目附具體原因與風險。
- 若這次踩到文件沒有記錄的坑，補回 `AGENTS.md` 或本檔，避免下一位重複踩坑。

## 常見誤判與禁止事項

- 不因 route、provider 或 CDK construct 存在，就宣稱功能已啟用、已部署或 production-ready。
- 不把 Memory API 當成 Agent Context、不把 RAG retrieval 當成 projection、不把 notification README
  當成 worker deployment。
- 不依賴舊 README 的 `allowed_tools` callback 敘述；以 proposal-only canonical path 為準。
- 不用 email 自動連結 Google／LINE 身份，不讓 Client 自稱角色或 scope。
- 不修改 frozen baseline migration，不以 dual write 更新 PostgreSQL 與 projection store。
- 不執行 `git reset --hard`、`git checkout --` 覆蓋變更，不直接 push `main`。
- 不為了 Windows Git ownership 問題改 repository owner 或全域安全設定；命令使用 scoped
  `git -c safe.directory=D:/Hackthon/kinsun.ai ...`。若 Supabase、網路、AWS 或沙箱受限，記錄限制，
  不以關閉安全檢查繞過。
- 本機直接啟動 Speech Gateway 要使用
  `uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002`；其
  `pyproject.toml` 設定 `tool.uv.package = false`，不可省略 `--app-dir src`。

## 尚待產品／平台決策

以下仍是 `TODO(待確認)`，不得自行選定：production hosting provider／region 與成本上限、正式 Bedrock model／fallback、
ASR/TTS endpoint 與 quality gate、LINE／email service credential、scheduler frequency、資料 retention／
legal hold／offboarding、production API／event client、voice／agent／TTS performance gate。

## 回報格式

完成工作時用精簡四段：

1. 結果：實際完成什麼。
2. 變更：關鍵檔案與行為。
3. 驗證：執行的命令與結果。
4. 未驗證／風險：只列真實存在的環境限制或待決事項。
