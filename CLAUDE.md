# CLAUDE.md

- 更新日期：2026-09-02
- 校準基準：`main` at `03cd170`
- 適用範圍：整個 `kinsun.ai` repository

本檔定義 Claude 在本專案中的工作流程、檢查順序與交付格式。完整架構、安全、Contract、
資料庫與測試規則以根目錄 [`AGENTS.md`](AGENTS.md) 為準；進入
`services/agent-runtime/` 時還要讀取該目錄的 [`AGENTS.md`](services/agent-runtime/AGENTS.md)。
競賽題目、Persona、Story Map 與各領域規格在 [`docs/spec/`](docs/spec/)；不要把本檔當產品規格。

## 每次工作固定流程

1. 先確認工作區，不覆蓋使用者既有變更。

   ```powershell
   # 把 <repo> 換成這台機器上的實際 checkout 路徑（不要沿用舊紀錄裡的 D:/Hackthon/kinsun.ai，
   # 那個路徑不一定存在；scoped safe.directory 的用意是不去動全域 Git 設定）。
   git -c safe.directory=<repo> -C <repo> status --short
   git -c safe.directory=<repo> -C <repo> log -5 --oneline
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
  2026-09-04 工作樹基準為 32 個 revisions、head `a7c9e1f3b5d6`；baseline 仍是 48 張 table，
  後續 revision 另加 `elder_enrollment`、`elder_care_profile_entry`、`assisted_elder_session`、
  `care_action_event_provenance` 等表；`app/models/` 目前宣告 52 個 `__tablename__`。Alembic 另外擁有
  `rag_public` 與 `service_identity` 兩個非 domain schema，兩者都沒有 ORM model。model attribute `id` 常透過 `__pk_name__` 對應
  DB 的領域主鍵，不要把欄位名稱不同誤判成 schema drift。
- Staff-assisted accountless Elder Session（`f7a9b1c3d456`／`b8c2d4e5f607`）預設關閉，且在
  `APP_ENV=production` 一律拒絕。`ks1_`／`ep1_`／`es1_` 是三種不同憑證，assisted token 不帶任何
  可信 role／tenant／elder／scope／expiry claim，每次都由 Core 重建 initiator 的 live ActorContext
  再跑既有 ElderAccessPolicy。`ASSISTED_TABLET_ACKNOWLEDGEMENT` 的 consent 只能建立 `BASIC_VOICE`，
  `granted_by_actor_id` 必須為 NULL——照服員是記錄者，不是同意的當事人。無帳號長者沒有 Elder
  Actor，speaker gate 無法判定 verified Elder speech，Event／Memory proposal 維持關閉。
- Speech Gateway → Core 私有呼叫改用 request-bound 短效 HMAC 憑證（綁 method／path／body digest／
  correlation ID／single-use ID，TTL 1–60s），兩側預設關閉、secret 必須相等且不得重用
  Core→Agent Runtime 或任何 Voice／OAuth／provider secret。replay claim 自 2026-09-02 起改用
  `service_identity.credential_nonce` 的 `INSERT ... ON CONFLICT DO NOTHING`，在獨立短交易提交，
  跨 replica 有效。verifier 的 `replay_store` 是必填參數；Agent Runtime 以
  `SERVICE_IDENTITY_REPLAY_DATABASE_URL` 選用 durable store，`APP_ENV=production` 缺這項就
  **啟動失敗**，不得退回 process-local。legacy bearer 只供遷移，不得與 request-bound identity 併用。
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
  principal、live relevance Golden Query／quality gate、v003 Supabase sync、activation／rollback 尚未完成，
  外部 runtime activation 與 Production 仍封鎖；legacy OpenSearch adapter 保留。
  2026-08-26 已依 Owner 明確人工確認，在 repository 內產生 immutable successor
  `data/rag-v3/candidates/v003/`：17 sources／726 chunks 全部 `review_status=verified`，文字與
  embedding text 均未變更，且 726／726 通過既有 embedding profile reuse 檢查；這是尚未同步的
  本機 staging candidate，Supabase 目前仍維持上述 v002／`needs_review=726`。
  2026-08-26 已另建本機 source-family policy v002：13 個缺少 license URL 的來源改以 Owner 已記錄的
  staging project-use review 作為依據，不再因 URL 缺少而自動封鎖，且不改寫既有 `license_status`；
  5 筆表單範例的「一般風險值」以 policy overlay 映射為 canonical `low`，v003 Chunk bytes 保持不變。
  14 個官方來源對四種角色形成 554 筆 ordinary retrieval candidates。2026-08-27 已依 Owner 明確決定
  建立 immutable、hash-pinned runtime policy v002：220 筆 professional assessment null 與 5 筆
  official assessment null 映射為 true，不改寫 v003 Chunk bytes；522 筆具完整 response metadata，
  其中 372 筆命中時由 Runtime 固定附主管機關／專業人員諮詢提醒。個人診斷、長照資格、等級與
  補助額度仍禁止由 AI 判定；32 筆空 purpose、高風險、stop 與非 current 內容持續 fail closed。
  Runtime 先在固定 554 筆 v002 chunk IDs 搜尋最多 50 筆，再依 v003 text SHA-256、角色、purpose 與
  assessment metadata 決定可回覆的 3–5 筆。9 個離線 policy／advisory／citation Golden cases已通過；
  2026-08-27 長者帳號詢問「長照法是什麼？」的 live smoke 已為 `SUCCESS/ALLOW`，取得 5 筆長照法
  chunks，最終顯示 2 個去重引用與 deterministic advisory；完整 backend relevance／ranking Golden
  Query suite 仍為 `NOT_EXECUTED`，外部同步與 Production 仍未授權。
  2026-08-27 已在其上建立 successor runtime policy v003，不改寫 v002 bytes：staging-only purpose
  overlay 分類原本空白的 32 筆 A 單位手冊 chunks，554 筆全部具備 response metadata（v002 為 522），
  Core 自然語言知識提問才能通過 purpose gate；這 32 筆仍是 `needs_review` 的 AI-assisted staging
  classification，不等於人工確認或 Production 核准。啟用必須同時給
  `RAG_SOURCE_FAMILY_POLICY_PATH` 與 `RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256`，缺一、digest 不符
  或仍開著 `RAG_STAGING_ALLOW_ALL_AUDIENCES` 就 fail closed 且不建立 Retriever；Runtime image 不
  內建 `data/rag*`。`config/rag/source-family-golden-queries-v003.json` 的 10 個離線 case ＋ 2 個
  exclusion case 本機通過。細節與未解除封鎖見
  [`docs/project/rag-v3-runtime-policy-integration.md`](docs/project/rag-v3-runtime-policy-integration.md)。
- `trusted_care_profile` 是另一條 bounded context：只有 `BASIC_VOICE`、只有
  `CARE_PROFILE_AI_CONTEXT_ENABLED=true`（預設 `false`）、只取當前 tenant／elder 的
  `RECORDED`／`VERIFIED` 未退場條目。Runtime 以 source-labelled item 帶入並固定加上 prompt 規則：
  健康資料只是安全互動的背景，不是診斷、治療、用藥建議、症狀推論或指令的依據。Care Profile
  與 Memory 表沒有任何關聯或寫入。
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
- 每個角色只有一個 route prefix，shell 由 route group layout 擁有：`app/elder/(app)/*`＝ElderShell、
  `app/staff/(app)/*`＝CareSidebar、`app/family/(app)/*`；sign-in 頁刻意在 group 外。**不要在 page
  自行 import ElderShell 或手寫 `data-surface="voice"`**——那會讓新頁面靜默失去 640px measure、
  64px 觸控目標與較粗 focus ring。舊 URL 由 `next.config.mjs` 以 307 暫時 redirect 承接，
  搬 route 時同步 `route-migration.test.ts` 的 redirect map 與 `oauth-transaction.ts` 的登入後
  allowlist（是搬移，不是新增別名）。
- 平板交接流程：`/staff/elders/new` → `/elder/pair` → `/elder/session`，BFF 邊界只在
  `app/backend/elder-session/*`。BFF 固定 acknowledgement body，不接受 client 指定 policy、actor、
  reason、deletion、tenant 或 elder scope；交換時先清掉該瀏覽器的 App Session cookie，再設定
  獨立的 Elder Session cookie。
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

### Contract 與 deployment

- OpenAPI、AsyncAPI、JSON Schema、Pydantic model、實際 route 與 live verifier 必須一起演進。
  不可實作未登記 API；不相容變更必須有新 major version 或正式 migration plan。
- [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) 是差異說明，不是 executable truth，而且局部摘要
  可能落後；改動前後都跑 validator。2026-09-01 快照：Core OpenAPI 76 paths／81 operations、
  Agent 3 paths、AsyncAPI 1 channel，Core app 實際 80 paths／85 operations——多的 4 條是 FastAPI
  的 `/docs`、`/docs/oauth2-redirect`、`/openapi.json`、`/redoc`，實際 API path 已全部登記。
  `contracts/openapi/core-api.v1.yaml` 副檔名是 `.yaml` 但內容是 JSON（由
  `scripts/export_core_openapi.py` 產生），用 YAML 縮排 grep 會得到 0。
- Repository 目前沒有 production IaC，也沒有使用中的 AWS 服務。舊 `infra` CDK workspace 與 AWS
  deployment scripts 已由 [ADR 0019](docs/adr/0019-retire-aws-cdk-deployment-profile.md) 退役；歷史
  spec／ADR／handover 不是現行 runbook。未來 hosting provider、IaC 與 region 必須先由 Owner 以
  ADR 定案。Portable images 可用 `scripts/build_runtime_images.ps1`／`.sh` 在本機驗證；外部 endpoint
  可用 `scripts/smoke_test_deployment.py` 驗證，兩者都不代表 infrastructure 已部署。
- CI 已啟用：`.github/workflows/gate1.yml` 在對 `main` 的 PR 與 push 觸發，跑四個 Python 服務的
  lint／pytest、Core `tests/integration`（CI 自建 disposable `kinsun_test`）、三支 contract 驗證、
  五輪 synthetic Core-to-Agent 證據與完整 Frontend build。細節見 `AGENTS.md` §1。兩個要記住的
  邊界：core-api 在 CI 只跑 `ruff check` 不跑 `ruff format --check`；repository 目前沒有
  production IaC verification，已被取代的 `.github/workflows-disabled/pr.yml` 也已移除。
  **新增 import 時字母序是 CI 等級的地雷**：`8adba0f` 讓 core-api `ruff check` 出現 2 個 `I001`
  （`assisted_elders` 排在 `assignments` 前、`assisted_elder_session` 排在 `asr_gate` 前），
  同時讓 agent-runtime 的 `context/manifest.py`、`contracts/models.py` 沒過
  `ruff format --check`——這兩項對各自服務**都在 CI 內**。2026-09-01 已修。加完 import 後
  先跑該服務的 `ruff check`／`ruff format --check`，不要靠目測。

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

### Contracts 與 deployment-neutral artifacts

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
```

Repository 目前沒有可執行的 production IaC。需要驗證 container portability 時執行
`scripts/build_runtime_images.ps1`／`.sh`；需要驗證 Owner 提供的外部 URL 時依
`docs/runbooks/deployment-smoke.md` 執行，不能把任一結果描述成 infrastructure 已完成。

以下快照中的 Infra 結果，是 ADR 0019 退役前的歷史紀錄，不表示目前仍有 CDK workspace。

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

2026-08-27 runtime policy v003 併入 `main`（`a2b2b96`）後當次結果：Core unit 913、Agent Runtime 406、
RAG ingestion 311、Frontend 224 tests passed；Frontend ESLint 與 typecheck 通過。Speech Gateway、
Infra、Frontend production build、static contract 與兩支 live verifier 本次未重跑。沒有獨立
`TEST_DATABASE_URL`，未跑 Core integration；v003 只有離線 policy／citation Golden cases 與單筆長者
live smoke。這個快照同樣不可取代當次驗證。

2026-08-29 合併 `origin/main`（合併後 `9f5bbe6`）當次結果：Core unit 916、Agent Runtime 407、
RAG ingestion 320、Speech Gateway 81、Frontend 230 tests passed（37 files）。Agent／Speech／RAG 的
ruff check＋format 全過；Core ruff check 過，完整 format check 仍有 5 個既有檔案未過，且與本次
合併無關。Frontend typecheck／ESLint／production build 與靜態 contract validator 通過。未跑：Core
integration（無獨立 `TEST_DATABASE_URL`）、兩支 live verifier、Infra、五輪 synthetic 證據，這幾項
交由 push 後的 `gate1.yml` 執行。這個快照同樣不可取代當次驗證。

2026-09-01 對 `25f8d77` 的文件校準重跑結果：Core unit `953 passed`、Agent Runtime `426 passed`、
RAG ingestion `320 passed`、Speech Gateway `83 passed`、Frontend `277 passed`（44 files）、
Infra `7 passed`。Frontend typecheck／ESLint／production build、Infra typecheck 與兩個 synth、
靜態 `validate_contracts.py`、`verify_contract_live.py`、`verify_agent_contract_live.py` 全數通過。
RAG ingestion、Speech Gateway、Agent Runtime 的 `ruff check`＋`format` 全過，core-api `ruff check`
通過。同批修掉兩個擋 CI 的 lint 失敗：`ruff check --fix` 調整 `app/main.py`、
`app/models/__init__.py` 的 import 順序，`ruff format` 重排 agent-runtime 的
`context/manifest.py`、`contracts/models.py`；四個都只是排序／換行，修正後兩個 suite 重跑
仍是 953／426 passed。**仍未通過**：core-api `ruff format --check`（12 檔，5 個既有），該項不在
CI 內，本次刻意不整批重排。未執行：Core integration（仍無獨立 `TEST_DATABASE_URL`）、五輪
synthetic 證據、`.qa/` 的 Supabase smoke、live RAG Golden Query、Playwright 視覺 QA。
這個快照同樣不可取代當次驗證。

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

- 不因 route 或 optional provider adapter 存在，就宣稱功能已啟用、已部署或 production-ready。
- 不把 Memory API 當成 Agent Context、不把 RAG retrieval 當成 projection、不把 notification README
  當成 worker deployment。
- 不依賴舊 README 的 `allowed_tools` callback 敘述；以 proposal-only canonical path 為準。
- 不用 email 自動連結 Google／LINE 身份，不讓 Client 自稱角色或 scope。
- 不修改 frozen baseline migration，不以 dual write 更新 PostgreSQL 與 projection store。
- 不執行 `git reset --hard`、`git checkout --` 覆蓋變更，不直接 push `main`。
- Claude 執行 Git commit 時只寫本次變更的 subject／body；不得自行加入 `Co-Authored-By`、
  `Claude-Session`、`Generated-By` 或任何 AI／工具協作者署名與追蹤連結，除非使用者明確要求。
- 不為了 Windows Git ownership 問題改 repository owner 或全域安全設定；命令使用 scoped
  `git -c safe.directory=<repo> ...`（`<repo>` 是這台機器上的實際 checkout 路徑）。若 Supabase、
  網路、AWS 或沙箱受限，記錄限制，不以關閉安全檢查繞過。
- 本機直接啟動 Speech Gateway 要使用
  `uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002`；其
  `pyproject.toml` 設定 `tool.uv.package = false`，不可省略 `--app-dir src`。

## 尚待產品／平台決策

以下仍是 `TODO(待確認)`，不得自行選定：production hosting provider／IaC／region 與成本上限、正式 Bedrock model／fallback、
ASR/TTS endpoint 與 quality gate、LINE／email service credential、scheduler frequency、資料 retention／
legal hold／offboarding、production API／event client、voice／agent／TTS performance gate。

## 回報格式

完成工作時用精簡四段：

1. 結果：實際完成什麼。
2. 變更：關鍵檔案與行為。
3. 驗證：執行的命令與結果。
4. 未驗證／風險：只列真實存在的環境限制或待決事項。
