# kinsun.ai 新協作者環境建置指南

- 更新日期：2026-09-02
- 適用範圍：本機開發、測試與 Synthetic Demo
- 主要環境：Windows 11 + PowerShell；其他作業系統請換成等價指令

這份文件提供新協作者從乾淨電腦開始建置 `kinsun.ai` 的步驟。它只描述 repository
目前真正存在的功能與設定。Repository 沒有使用中的 AWS 服務或 production IaC，也不代表
Production、真實語音 Provider 或 RAG 已部署可用。

## 1. 開始前先讀

依序閱讀：

1. [`AGENTS.md`](../../AGENTS.md)：開發規則、產品安全邊界、驗證要求。
2. [`CLAUDE.md`](../../CLAUDE.md)：repository 協作補充規則。
3. [`README.md`](../../README.md)：專案架構與各服務現況。
4. [`docs/design-system/MASTER.md`](../design-system/MASTER.md)：修改前端時必讀。
5. [`contracts/DIVERGENCE.md`](../../contracts/DIVERGENCE.md)：修改 API／contract 前必讀。

重要邊界：

- 只能使用 Synthetic 或完成去識別的資料；不要輸入真實長者資料。
- 不得把模型輸出或未通過 Spec 18 Core Memory Policy／final retrieval gate 的資料當成正式事實。
- 不得在前端、Git、log、截圖或 issue 中放入 Token、Secret、逐字稿或 Audio。
- 前端是單一 Next.js multi-role PWA，不要新增第二套 elder／care／family app。
- 不要直接修改已套用的 Alembic migration、database schema 或 API contract。
- 要 Push 遠端時，先從最新的 `origin/main` 建立工作分支，不要直接 Push `main`。

## 2. 必要工具

| 工具 | 要求 | 用途 |
| --- | --- | --- |
| Git | 建議最新版 | 版本控制 |
| Node.js | `>= 20.9` | Next.js、TypeScript |
| npm | 隨 Node.js 安裝 | repository workspaces |
| Python | 3.12 | Core、Agent、Speech、RAG |
| uv | 建議最新版 | Python 版本、依賴與 lockfile |
| Docker Desktop | 含 Compose v2 | PostgreSQL 16、migration、Adminer |

先確認工具：

```powershell
git --version
node --version
npm --version
uv --version
docker version
docker compose version
```

若本機沒有 Python 3.12，可讓 uv 安裝：

```powershell
uv python install 3.12
```

## 3. Clone 與建立工作分支

```powershell
git clone <repository-url> kinsun.ai
cd kinsun.ai
git fetch origin main
git switch -c feat/<work-item> origin/main
```

若只是在既有 checkout 進行環境建置，可略過建立分支；只要開始修改，就應建立獨立分支。

## 4. 安裝依賴

Node.js dependencies 只在 repository 根目錄安裝一次：

```powershell
npm ci
```

四個 Python component 各自維護 `pyproject.toml`、`uv.lock` 與 `.venv`，不可共用環境：

```powershell
cd services/core-api
uv sync --frozen --extra test --extra dev

cd ../agent-runtime
uv sync --frozen --extra test --extra dev

cd ../speech-gateway
uv sync --frozen --extra test --extra dev

cd ../rag-ingestion
uv sync --frozen --extra test --extra dev

cd ../..
```

不要用 `pip install` 更新 lockfile 內的套件，也不要在 repository 根目錄建立一個共用 Python
虛擬環境。

## 5. ENV 檔案與載入規則

所有 `.env`、`.env.local` 與 service-local `.env` 都已被 `.gitignore` 排除。只能提交
`.env.example`，不得提交真實值。

| 檔案 | 誰會讀取 | 用途 |
| --- | --- | --- |
| `/.env` | Docker Compose、Core（非 production）、Agent Runtime、root scripts | DB、Core、Agent 與共用本機設定 |
| `/packages/frontend/.env.local` | Next.js | BFF、OIDC 與 `NEXT_PUBLIC_*` |
| `/services/agent-runtime/.env` | Agent Runtime，且會覆蓋 root `.env` | 選用的 Agent 個人設定 |
| `/services/speech-gateway/.env` | Speech Gateway | 選用的 Speech provider、Core system credential |
| 目前工作目錄的 `.env` | RAG ingestion | 從 root 執行時即使用 `/.env` |

第一次建置時建立兩個必要檔案；已有檔案時不要覆寫：

```powershell
if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
}

if (-not (Test-Path packages/frontend/.env.local)) {
  Copy-Item packages/frontend/.env.example packages/frontend/.env.local
}
```

最小本機開發可以保留 example 的 PostgreSQL 與 mock model 設定。至少確認 root `.env`：

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun
TEST_DATABASE_URL=postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test
FAKE_AUTH_ENABLED=true
MODEL_PROVIDER=mock
AGENT_RUNTIME_URL=http://127.0.0.1:8001
```

以及 frontend `.env.local`：

```dotenv
CORE_API_INTERNAL_URL=http://127.0.0.1:8000
FRONTEND_ORIGIN=http://localhost:3000
NEXT_PUBLIC_CONSENT_POLICY_VERSION=demo-consent-v1
```

注意：

- `DATABASE_URL` 必須使用 `postgresql+asyncpg://`；Alembic 會自行轉成 psycopg。
- 若修改 `POSTGRES_PORT`，必須同步修改 `DATABASE_URL` 與 `TEST_DATABASE_URL`。
- `NEXT_PUBLIC_*` 會送到瀏覽器，只能放公開設定，絕不能放 Secret 或 Token。
- Next.js 不會以 root `.env` 取代 `packages/frontend/.env.local`。
- ENV 改完後要重啟對應 service；`NEXT_PUBLIC_*` 改動後也要重啟或重新 build 前端。
- `APP_ENV=production` 時 Core 不讀本機 `.env`，Production 必須由 runtime secret store 注入。

## 6. 建立本機資料庫

從 repository 根目錄執行：

```powershell
docker compose config --quiet
docker compose up -d postgres
docker compose ps
```

等 `kinsun-postgres` 顯示 `healthy` 後，套用正式 Alembic migration：

```powershell
docker compose run --rm migrate
docker compose run --rm migrate alembic current
```

Schema 名稱是 `eldercare_ai`。`docker/postgres/init/` 只建立 extension 與 `kinsun_test`，
table／index／constraint／trigger 的唯一權威仍是 Alembic。

### 建立 Synthetic Demo 資料

首次 migration 後，可建立固定的 Synthetic Persona、Consent、Event、Memory 與 Report：

```powershell
uv run --project services/core-api python scripts/seed_demo.py
```

Seed ID 清單在 [`data/seed/demo_ids.json`](../../data/seed/demo_ids.json)。這些 ID 是測試資源
識別碼，不是憑證。

Seed script 只允許操作 localhost 的 `kinsun` database。若資料已存在，它會拒絕重複寫入。
需要重建時才執行下列破壞性指令：

```powershell
.\scripts\reset_demo.ps1 -ConfirmLocalReset
```

這會刪除並重建本機 `kinsun` 的整個 `eldercare_ai` schema，不能對共享、staging、Supabase
或 production database 使用。

## 7. 啟動最小本機 Stack

每個 service 開一個 PowerShell terminal。啟動順序建議為 Agent → Core → Frontend。

### Terminal 1：Agent Runtime（port 8001）

```powershell
cd services/agent-runtime
uv run uvicorn --app-dir src agent_runtime.app:app --reload --port 8001
```

`MODEL_PROVIDER=mock` 不需要 AWS、LLM API key 或網路。

### Terminal 2：Core API（port 8000）

```powershell
cd services/core-api
uv run uvicorn app.main:app --reload --port 8000
```

Core 在 development 會以絕對路徑讀取 repository root `.env`。

### Terminal 3：Frontend（port 3000）

```powershell
npm run dev --workspace @elderly-care/frontend
```

開啟：

- Public site：`http://localhost:3000`
- Sign-in chooser：`http://localhost:3000/sign-in`
- Core docs（development only）：`http://127.0.0.1:8000/docs`

### Health check

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-WebRequest http://localhost:3000/health -UseBasicParsing
```

使用 root `.env.example` 的 fake auth 時，也可直接驗證受保護 Core endpoint：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/me
```

## 8. Fake Auth 與瀏覽器登入的差別

`FAKE_AUTH_ENABLED=true` 是 Core 的 development-only server setting，適合直接測 Core API。
它不是瀏覽器登入系統。

目前前端只接受 BFF 設定的 HttpOnly `ks1_` Core App Session Cookie。舊文件提到的
`POST /backend/auth/session` 開發登入已移除；現在該 route 只有查詢與登出能力。不要手動偽造
Cookie，也不要新增繞過 Auth 的 Demo route。

因此最小本機 Stack 可以驗證：

- Public frontend 與 sign-in 頁面。
- Core、Agent、DB 與 contracts。
- 使用 fake auth 直接呼叫 Core API。

若要操作受保護的 Elder、Care、Family 前端頁面，必須完成下一節的 Google 或 LINE OIDC
設定並由 Core 正式核發 App Session。登入成功也不代表具有任意 elder scope；Core 仍會根據
TenantMembership、Relationship、Assignment、Consent 與 resource state 重新授權。

## 9. 完整 Google OIDC 登入（選配）

Google Cloud 必須建立 Web application OAuth client，並登記完全相同的 callback：

```text
http://localhost:3000/backend/auth/google/callback
```

需要多個互相獨立、至少 32 bytes 的 Secret。可在 PowerShell 產生單一開發用 Secret：

```powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
[Convert]::ToBase64String($bytes)
$rng.Dispose()
```

每個欄位都要重新產生一次，不可重用。

### Root `.env`（Core）

```dotenv
FAKE_AUTH_ENABLED=false
APP_SESSION_AUTH_ENABLED=true
GOOGLE_OIDC_HANDOFF_ENABLED=true
GOOGLE_OIDC_CLIENT_ID=<google-client-id>
GOOGLE_IDENTITY_HMAC_SECRET=<unique-32-byte-secret>
GOOGLE_IDENTITY_HMAC_KEY_VERSION=1
GOOGLE_OIDC_HANDOFF_SECRET=<shared-bff-core-handoff-secret>
FAMILY_INVITATION_HMAC_SECRET=<unique-32-byte-secret>
```

### `packages/frontend/.env.local`（BFF）

```dotenv
GOOGLE_DIRECT_OIDC_ENABLED=true
GOOGLE_OIDC_CLIENT_ID=<same-google-client-id>
GOOGLE_OIDC_CLIENT_SECRET=<google-client-secret>
GOOGLE_OIDC_TRANSACTION_SECRET=<unique-32-byte-secret>
GOOGLE_OIDC_HANDOFF_SECRET=<same-shared-bff-core-handoff-secret>
```

規則：

- `GOOGLE_OIDC_CLIENT_ID` 在 BFF 與 Core 必須相同。
- `GOOGLE_OIDC_HANDOFF_SECRET` 在 BFF 與 Core 必須相同。
- Client Secret 只放 BFF，不放 Core，也不能使用 `NEXT_PUBLIC_*`。
- Identity HMAC、transaction、handoff、family invitation secrets 必須彼此不同。
- 三個 gate 缺一不可：BFF `GOOGLE_DIRECT_OIDC_ENABLED`、Core
  `GOOGLE_OIDC_HANDOFF_ENABLED`、Core `APP_SESSION_AUTH_ENABLED`。
- `FAKE_AUTH_ENABLED` 必須改成 `false`；development mode 會優先選 fake authenticator，保持
  `true` 會讓受保護 endpoint 無法驗證剛核發的 App Session。
- 新 Google identity 會進入受控 onboarding；不會依 email 自動合併既有 Actor。

設定完成後重新啟動 Core 與 Frontend，再從 `http://localhost:3000/elder/start` 登入。

## 10. LINE Login 與帳號連結（選配）

LINE Login 和 LINE Messaging API 是兩組不同設定，不得混用 Channel Secret。

LINE Login callback：

```text
http://localhost:3000/backend/auth/line/callback
http://localhost:3000/backend/auth/identities/line/callback
```

Core root `.env` 至少需要：

```dotenv
FAKE_AUTH_ENABLED=false
APP_SESSION_AUTH_ENABLED=true
LINE_OIDC_HANDOFF_ENABLED=true
LINE_LOGIN_CHANNEL_ID=<line-login-channel-id>
LINE_IDENTITY_HMAC_SECRET=<unique-32-byte-secret>
LINE_IDENTITY_HMAC_KEY_VERSION=1
LINE_OIDC_HANDOFF_SECRET=<shared-bff-core-handoff-secret>
FAMILY_INVITATION_HMAC_SECRET=<unique-32-byte-secret>
```

Frontend `.env.local` 至少需要：

```dotenv
LINE_DIRECT_OIDC_ENABLED=true
LINE_LOGIN_CHANNEL_ID=<same-line-login-channel-id>
LINE_LOGIN_CHANNEL_SECRET=<line-login-channel-secret>
LINE_OIDC_CALLBACK_URL=http://localhost:3000/backend/auth/line/callback
LINE_ACCOUNT_LINK_CALLBACK_URL=http://localhost:3000/backend/auth/identities/line/callback
LINE_OIDC_TRANSACTION_SECRET=<unique-32-byte-secret>
LINE_OIDC_HANDOFF_SECRET=<same-shared-bff-core-handoff-secret>
```

LINE 直接登入只允許既有已連結 identity。新帳號建立、任意 Actor 合併或依 email 自動合併都不在
這條路徑中。LINE Messaging、Daily Notification 與官方 Account Linking 另需
`LINE_ACCOUNT_LINK_*`、Channel access token 及 encryption secret；全部保持 disabled，直到正式
Provider、scope 與 callback 都準備完成。

## 11. Speech Gateway 與語音（選配）

只驗證 service health 時，不需要任何雲端 credential：

```powershell
cd services/speech-gateway
uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002
```

建立 git-ignored 的 `services/speech-gateway/.env`：

```dotenv
APP_ENV=local
AWS_REGION=us-west-2
CORE_API_BASE_URL=http://127.0.0.1:8000
CORE_API_SERVICE_IDENTITY_ENABLED=true
CORE_API_SERVICE_IDENTITY_HMAC_SECRET=<same-as-root-SPEECH_SERVICE_IDENTITY_HMAC_SECRET>
CORE_API_SERVICE_IDENTITY_ISSUER=kinsun-local
CORE_API_SERVICE_IDENTITY_TTL_SECONDS=30
CORE_API_TIMEOUT_SECONDS=5
SAGEMAKER_ASR_ENDPOINT=
SAGEMAKER_TTS_ENDPOINT=
AZURE_SPEECH_KEY=<Speech-resource-Key-1-or-Key-2>
AZURE_SPEECH_REGION=<same-Speech-resource-region>
```

Frontend `.env.local`：

```dotenv
NEXT_PUBLIC_SPEECH_GATEWAY_URL=http://127.0.0.1:8002
```

要走正式 browser voice path，Core root `.env` 還必須使用兩個不同的 32+ byte Secret：

```dotenv
VOICE_TICKET_ENABLED=true
VOICE_TICKET_HMAC_SECRET=<unique-32-byte-secret>
ASR_GATE_ENABLED=true
ASR_GATE_HMAC_SECRET=<different-unique-32-byte-secret>
SPEECH_SERVICE_IDENTITY_ENABLED=true
SPEECH_SERVICE_IDENTITY_HMAC_SECRET=<third-independent-32-byte-secret>
SPEECH_SERVICE_IDENTITY_ISSUER=kinsun-local
SPEECH_SERVICE_IDENTITY_TTL_SECONDS=30
```

Repository 目前沒有已部署的雲端 ASR／TTS provider。只有在明確測試對應 optional adapter 時，
才需要以下 provider-specific 設定：

- AWS Transcribe／Polly adapter：標準 AWS credential provider chain 與對應權限。
- Gate 1 local/test 的 Speech Gateway 必須啟用 request-bound service identity；
  `CORE_API_SERVICE_IDENTITY_HMAC_SECRET` 與 root `SPEECH_SERVICE_IDENTITY_HMAC_SECRET` 相同，且不得與
  Core → Agent Runtime、Voice Ticket、ASR Gate、OAuth 或 provider secret 共用。
- SageMaker 台語／客語 adapter：通過 license 與 Synthetic smoke gates 的私有 endpoint。
- 國語／英文 TTS 預設走 Azure Speech；`AZURE_SPEECH_KEY` 必須是 Speech resource 的
  Key 1／Key 2，且 `AZURE_SPEECH_REGION` 必須與該 resource 的 region 相同。Azure 拒絕憑證時
  Gateway 回 503；只有未部署該語言時才回 501。

Gate 1 local/test credential 最長 60 秒，並綁定 issuer、subject、audience、method、path、body digest、
correlation ID 與單次 credential ID。Production IAM／mTLS 等 credential mechanism 仍待 Owner 核准；
不可把此 synthetic/local 機制宣稱為 production ready，也不可用假 Token 或跳過 Voice Ticket／ASR Gate。

## 12. 真實文字模型（選配）

預設 `MODEL_PROVIDER=mock` 最適合本機開發。若要使用 OpenAI-compatible provider，在 root `.env`
或 `services/agent-runtime/.env` 設定：

```dotenv
MODEL_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=<https-compatible-endpoint-or-loopback-http>
OPENAI_COMPATIBLE_API_KEY=<runtime-secret-or-empty-for-local-no-auth>
OPENAI_COMPATIBLE_MODEL_ID=<model-id>
OPENAI_COMPATIBLE_MAX_TOKENS=512
OPENAI_COMPATIBLE_TEMPERATURE=0.2
OPENAI_COMPATIBLE_TIMEOUT_SECONDS=30
```

遠端 endpoint 必須使用 HTTPS。本機無驗證相容服務才可用 loopback HTTP。Core 的
`AGENT_RUNTIME_MODEL_ID` 只是稽核 label，切換模型時應同步更新；設定不完整時 Runtime 會在啟動
階段 fail closed，不會靜默 fallback 到 mock。

## 13. RAG Ingestion（staging-only，選配）

RAG 不是最小本機 Stack 的必要服務。它目前只允許 staging、官方公共資料與既有 allowlist，禁止
處理真實長者個資。

從 repository root 執行時，它使用 root `.env`。現行 target 是 Supabase PostgreSQL／pgvector，
Runtime 要明確綁定 `RAG_DATABASE_URL`、release、embedding profile 與治理 policy digest；完整設定見
[`rag-v3-runtime-policy-integration.md`](rag-v3-runtime-policy-integration.md)。Legacy
OpenSearch／Bedrock adapter 只在顯式 opt-in 時使用，沒有現行 AWS deployment evidence。

本機 Agent Runtime 使用 port 8001 時，RAG smoke 應明確設定：

```dotenv
AGENT_RUNTIME_BASE_URL=http://127.0.0.1:8001
RAG_MODE=staging
RAG_REQUIRE_OWNER_SIGNATURE=false
RAG_PRODUCTION_ENABLED=false
```

`RAG_REQUIRE_OWNER_SIGNATURE=false` 只代表 unsigned development override，不代表 Human Review 或
production approval。完整流程與安全 gate 見
[`services/rag-ingestion/README.md`](../../services/rag-ingestion/README.md)。

## 14. 驗證命令

以下每個 command block 都假設從 repository 根目錄開始執行。

### 每次前端變更

```powershell
npm run test --workspace @elderly-care/frontend
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
npm run lint
```

### Core

```powershell
cd services/core-api
uv run pytest tests/unit
uv run ruff check .
uv run ruff format --check .
```

Integration tests 會 migration roundtrip 並重建 `kinsun_test`，不要把 `TEST_DATABASE_URL` 指向
`kinsun`、Supabase、共享或 production database。建議使用帶安全確認的 script：

```powershell
.\scripts\verify_core.ps1 -ConfirmTestDatabaseMigrations
```

### Agent Runtime

```powershell
cd services/agent-runtime
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Speech Gateway

```powershell
cd services/speech-gateway
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### RAG Ingestion

```powershell
cd services/rag-ingestion
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Contract 與 repository 基本檢查

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
docker compose config --quiet
git diff --check
git status --short
```

靜態 contract validator 只證明 schema 與 examples 自洽。Live verifier 需要先啟動對應服務，才是
contract 與實作一致的證據。

### Portable runtime images 與外部部署 smoke

```powershell
./scripts/build_runtime_images.ps1 `
  -ReleaseId <git-sha> `
  -ConsentPolicyVersion <policy-version>
```

這只建立並檢查本機 OCI images，不 push registry 或部署資源。Repository 目前沒有 production IaC；
舊 AWS CDK profile 已依 ADR 0019 退役。若 deployment owner 提供外部服務 URL，依
[`docs/runbooks/deployment-smoke.md`](../runbooks/deployment-smoke.md) 驗證，不得自行猜測 hosting
provider 或環境。

## 15. 日常啟停

啟動：

```powershell
docker compose up -d postgres
```

再分別啟動 Agent、Core、Frontend；需要語音時才啟動 Speech Gateway。

停止 application service 時，在各 terminal 按 `Ctrl+C`。停止 PostgreSQL 並保留資料：

```powershell
docker compose down
```

選用 Adminer：

```powershell
docker compose --profile tools up -d
```

開啟 `http://localhost:8080`，Server 填 `postgres`，帳密與 database 取自 root `.env`。

不要例行執行 `docker compose down -v`；它會刪除本機 PostgreSQL volume。

## 16. 常見問題

### PostgreSQL 5432 已被占用

修改 root `.env`：

```dotenv
POSTGRES_PORT=15432
DATABASE_URL=postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:15432/kinsun
TEST_DATABASE_URL=postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:15432/kinsun_test
```

重新建立 compose container 後再 migration。

### Core 啟動時顯示沒有 authenticator

- 直接 API 本機開發：確認 `APP_ENV=development`、`FAKE_AUTH_ENABLED=true` 與三個
  `FAKE_AUTH_*` synthetic 值存在。
- 完整瀏覽器登入：確認 App Session 與 OIDC 三個 gates、shared handoff secret 和 callback。
- 不要在 `APP_ENV=production` 啟用 fake auth；它不會生效。

### Frontend 顯示未登入，但 Core fake auth 可用

這是預期行為。Fake auth 不會建立 HttpOnly App Session Cookie。請設定 Google／LINE OIDC，或只以
direct Core API 進行 fake-auth 測試。

### Consent 不能開啟

確認：

- 已執行 migration 與 Synthetic seed。
- Frontend `NEXT_PUBLIC_CONSENT_POLICY_VERSION=demo-consent-v1`。
- DB 中存在相同版本的 ACTIVE policy。
- 登入 Actor 對該 Elder 具有 `consent:read/write/revoke` scope。

前端不會自行建立不存在的 policy 或繞過 Core authorization。

### Agent 可啟動，但知識問答只回 fallback

`MODEL_PROVIDER=mock` 與一般 conversation 不代表 RAG 已啟用。PostgreSQL release／profile、query
embedding provider、runtime policy path／digest、staging mode 或治理 gate 任一項缺少時都會
no-guess／fail-closed。

### Speech health 通過，但錄音失敗

Health 不會驗證雲端 provider、Core system credential、Voice Ticket、ASR Gate 或模型 endpoint。依第 11 節
逐項確認；不要把 health 200 當成語音 E2E 證據。

### PowerShell 不允許執行 repository script

不要修改 machine-wide policy。可只對目前 process 暫時允許：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

### Migration baseline checksum 不符

Windows checkout 可能把 SQL 從 LF 轉成 CRLF。不要修改 baseline SQL 或預期 checksum；先確認
`.gitattributes` 生效並還原乾淨的 LF checkout。

## 17. Secret 交付檢查表

在 commit、PR、issue、截圖或交接前確認：

- `git status --short` 沒有 `.env`、`.env.local`、credential、audio 或 transcript。
- 沒有 Secret 使用 `NEXT_PUBLIC_*`。
- Google／LINE Client Secret 只在 BFF/runtime secret store。
- Identity、transaction、handoff、family invitation、voice ticket、ASR gate、encryption secrets
  彼此獨立。
- 任何 optional provider credential 都只使用其標準 credential chain／runtime secret，不寫入 repository。
- 所有測試、Demo 與截圖都只有 Synthetic／de-identified data。
- Production secret 由部署平台的 Secret Manager 注入，不打包進 image。

若環境需求與這份文件不一致，先用目前程式、contracts、migration 與測試確認實際狀態，再更新
本文件；不要沿用過時 handover 或假設尚未存在的 API／bootstrap 已完成。
