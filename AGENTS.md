# AGENTS.md

- 更新日期：2026-09-02
- 校準基準：`main` at `03cd170`
- 適用範圍：整個 `kinsun.ai` repository；`services/agent-runtime/AGENTS.md` 在該子目錄追加規則，衝突時以本檔為準。
- 協作流程：先讀本檔，再讀根目錄 `CLAUDE.md`；每次 AI 因專案特性犯錯，都要把該地雷補回這兩份文件。

所有代理在分析、設計、實作、測試與文件更新時，都必須遵守本文件及 `docs/` 中的產品規格。描述進度時以可執行程式、contract、migration、測試與部署證據為準，不以 README、舊 handover 或 commit 標題單獨判定完成。

## 1. 專案狀態

- 本專案源自 AWS Hackathon，現為可獨立維護、可替換雲端 provider 的 Voice-first 智慧長照 AI 陪伴系統。
- 目前 repository 是可在本機執行與測試的 Monorepo，不只是文件 12 的空骨架；主要單元如下：
  - `services/core-api`：正式 Domain Core。已有 Identity／Actor、Kinsun-owned Email＋Password、Core App
    Session authentication、direct Google／LINE OIDC handoff、受限帳號連結、Elder scope、Consent、Voice
    Ticket／ASR Gate、Care Event、Memory、Daily Summary、Family Report、Assignment、Deletion、Agent
    Run、受控 Tool、LINE Messaging／通知，以及 transactional outbox 與 provider-neutral event
    publisher／consumer foundation。正式狀態仍只由 Core database 與 Command Gate 擁有。
    2026-09-01 另加入兩條軸線，兩者都**預設關閉**：
    - **Staff-assisted accountless Elder Session**（migration `f7a9b1c3d456`）：新增
      `elder_enrollment`、`elder_care_profile_entry`、`assisted_elder_session` 三張表與
      `app/api/assisted_elders.py` 的 8 個 route。照服員可建立沒有 Actor／identity 的長者，
      再發一次性 `ep1_` pairing token 換成 HttpOnly `es1_` Elder Session；`ks1_`／`ep1_`／`es1_`
      是三種不同憑證，一般 Core endpoint 只收 `ks1_`。Token 不攜帶任何可信 role／tenant／elder／
      scope／expiry claim，每次請求都由 Core 重建 initiator 的 live ActorContext 再跑既有
      ElderAccessPolicy。migration `b8c2d4e5f607` additive 補上 `consent_grant` 的
      `confirmation_method`／`recorded_by_actor_id`／`assisted_session_id`：
      `ASSISTED_TABLET_ACKNOWLEDGEMENT` 要求 `granted_by_actor_id` 為 NULL，只會建立
      `BASIC_VOICE`，不得授予 Memory、event extraction、family sharing 或 Care Profile projection。
      無帳號長者沒有 Elder Actor，speaker gate 無法判定為 verified Elder speech，Event／Memory
      proposal 因此維持關閉。`ASSISTED_ELDER_SESSIONS_ENABLED` 預設 `false` 且在
      `APP_ENV=production` 一律拒絕。Kiro spec 為 `.kiro/specs/staff-assisted-elder-session/`，
      7 項任務全部完成，release blocker 見該目錄 `traceability.md`。
    - **Speech Gateway → Core request-bound service identity**（`app/middleware/speech_service_auth.py`
      ＋ `app/adapters/service_identity.py`）：取代原本 `require_system_service_actor` 的長效
      bearer。憑證綁 issuer／subject／audience／method／path／body SHA-256／correlation ID 與
      single-use credential ID，TTL 1–60s，claim 必須完全相符，比對用 `hmac.compare_digest`，
      所有失敗都回同一句 "Authentication required"，不得當成資源存在與否的 oracle。replay state
      是 process-local，ADR 0009 要求多 replica 部署前換掉。`SPEECH_SERVICE_IDENTITY_ENABLED`／
      `CORE_API_SERVICE_IDENTITY_ENABLED` 兩側都預設關閉，secret 必須相等且**不得**重用
      Core→Agent Runtime 或任何 Voice／OAuth／provider secret；`X-Kinsun-Service-Credential`
      已加入 log redaction。legacy bearer 只保留給遷移，不得與 request-bound identity 併用。
  - `services/agent-runtime`：M0 單輪閉環——contract 驗證、受控 Orchestrator、Companion Agent、
    deterministic Safety Evaluator、Event Candidate proposal 與明確固定早餐習慣的 bounded
    Memory Candidate proposal。Memory proposal 先私下綁在 Event Candidate version；只有照護者
    VERIFY 來源事件、且 Core 重驗 memory authorization／Consent 後，才建立待長者本人確認的
    Memory Candidate。這是 **Current first slice**；Target 已由
    [Spec 18](docs/spec/18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)
    與 [ADR 0014](docs/adr/0014-risk-tiered-memory-speaker-verification.md) 改為總體 Consent＋Core
    deterministic risk policy＋Speaker Gate＋version-bound confirmation：LOW 嚴格 all-of 可自動保存、
    MEDIUM 由長者確認固定版本、HIGH 不建立 Memory row。尚未實作前不得把 Target 當 Current。
    2026-09-01 另加入 bounded `trusted_care_profile` context：只有 `BASIC_VOICE` purpose、只有
    `CARE_PROFILE_AI_CONTEXT_ENABLED=true`（預設 `false`）、且只取目前 tenant／elder 的
    `RECORDED`／`VERIFIED` 未退場條目，Runtime 以 source-labelled context item 帶入並固定加上
    prompt 規則：健康資料只是安全互動的背景，不是診斷、治療、用藥建議、症狀推論或指令的依據。
    Care Profile 與 Memory 表之間沒有任何關聯或寫入。
    `MODEL_PROVIDER=mock` 是 repository 與本機預設；程式另有 `BedrockModelProvider`，以及只依 runtime
    URL／model／optional Bearer key 的 provider-neutral `OpenAICompatibleModelProvider`，以及原生
    Google Gen AI SDK 的 `GeminiModelProvider`。`MODEL_PROVIDER=gemini` 會依 key 類型選路：`AQ.`
    開頭的 Vertex AI Express key 必須走 Vertex AI，其他 key 走 Gemini Developer API；兩者不得
    混用 endpoint。provider 設定錯誤或呼叫失敗時都不會 fallback 到 mock。這些 provider 都可使用
    受控 Context／RAG chunk 生成回答，但除本機 synthetic smoke 外尚無真實
    staging／production 連線證據。RAG Retriever 已以不含 executable DSL 的 provider-neutral
    `SearchBackend`／bounded plan 隔離搜尋實作；query embedding 也已由 provider-neutral
    `EmbeddingProvider` 隔離，現有 Bedrock 與 opt-in Google query adapters。Core 已有本機驗證的
    `rag_public` PostgreSQL／pgvector migration 與 17 sources／726 candidate chunks 的 deterministic、
    idempotent staging projection importer。2026-08-25 已對目前 Supabase development database 套用
    migration `e6f8a0b2c345`，並匯入 release `rag-v2-v002-bab68588963b`；遠端讀回為 17 sources、
    726 chunks、全部 record/text/embedding-text hash 一致、`needs_review=726`、
    `production_approved=0`。2026-08-25 已使用確認的 Google
    `gemini-embedding-001`／1024／`RETRIEVAL_DOCUMENT` profile 產生 726 成功、0 失敗的 repository 外
    staging artifact，SHA-256 為
    `599d194db552433710ec6aff69318e962cb5b4b1c9f7a3050d527b369a3df7d5`；經使用者確認後已以單一
    transaction 匯入 726 document embeddings，Supabase 獨立讀回的 profile、embedding-text hash 與
    vector fingerprint 全部 `VERIFIED`。2026-08-25 已新增固定模板、全參數化的 PostgreSQL
    FTS／trigram＋pgvector hybrid `SearchBackend`，runtime 可用
    `RAG_SEARCH_BACKEND=postgresql` 精確綁定上述 release／profile；Supabase data-plane smoke 與
    Google `RETRIEVAL_QUERY` → Supabase → V2 citation smoke 均回傳 5 筆合規 staging chunks。
    2026-08-26 已依 Owner 明確人工確認，在 repository 內產生 immutable successor
    `data/rag-v3/candidates/v003/`：17 sources／726 chunks 全部 `review_status=verified`，文字與
    embedding text 均未變更，且 726／726 通過既有 embedding profile reuse 檢查；這是尚未同步的
    本機 staging candidate，Supabase 目前仍維持上述 v002／`needs_review=726`。
    2026-08-26 已另建本機 source-family policy v002：13 個缺少 license URL 的來源改以 Owner 已記錄的
    staging project-use review 作為依據，不再因 URL 缺少而自動封鎖，且不改寫既有 `license_status`；
    5 筆表單範例的「一般風險值」以 policy overlay 映射為 canonical `low`，v003 Chunk bytes 保持不變。
    14 個官方來源對 Elder／Family／Care Professional／System Admin 形成 554 筆 ordinary retrieval
    candidates。2026-08-27 已依 Owner 明確決定建立 hash-pinned runtime policy v002：ordinary runtime
    candidates 的 220 筆 professional assessment null 與 5 筆 official assessment null 映射為 true，
    不改寫 v003 Chunk bytes；522 筆具完整 response metadata，其中 372 筆命中時由 Runtime 固定附上
    主管機關／專業人員諮詢提醒，個人診斷、長照資格、等級與補助額度仍禁止由 AI 判定。32 筆空
    purpose、69 筆 high／high-red-line、`stop_normal_rag` 與非 current 內容持續 fail closed。Runtime
    先在固定 554 筆 v002 chunk IDs 搜尋最多 50 筆，再以 v003 text SHA-256、角色、purpose 與
    assessment metadata 決定可回覆的 3–5 筆。9 個離線 policy／advisory／citation Golden cases 已通過；
    2026-08-27 長者帳號詢問「長照法是什麼？」的 live smoke 已為 `SUCCESS/ALLOW`，取得 5 筆長照法
    chunks，最終顯示 2 個去重引用與 deterministic advisory；完整 backend relevance／ranking Golden
    Query suite 仍為 `NOT_EXECUTED`。2026-08-27 已在其上建立 successor runtime policy v003，不改寫
    v002 bytes：以 staging-only purpose overlay 分類原本空白的 32 筆 A 單位手冊 chunks，沿用既有
    enum 並讓來源層與 chunk 層都含 `general_information`，554 筆因此全部具備 response metadata
    （v002 為 522），Core 的自然語言知識提問才能通過 purpose gate。這 32 筆仍標記 `needs_review`，
    不等於人工確認或 Production 核准，v003 Chunk bytes 未修改。啟用必須同時提供
    `RAG_SOURCE_FAMILY_POLICY_PATH`（`data/rag-v3/governance/source-family-policy/runtime/candidates/v003/source-family-runtime-policy.json`）
    與 `RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256`；path／digest 缺一或不符、或仍開著
    `RAG_STAGING_ALLOW_ALL_AUDIENCES`，Agent Runtime 就不建立 Retriever 並 fail closed。Runtime
    image 不內建任何 `data/rag*`，container staging 必須以唯讀 config mount 注入。
    `config/rag/source-family-golden-queries-v003.json` 固定 10 個離線 case ＋ 2 個 exclusion case，
    本機全部通過。完整啟用方式、限制與尚未解除的封鎖（Supabase／外部 backend 未同步、32 筆
    purpose 待 Owner 逐筆確認、獨立 read-only principal 與 activation／rollback 未建立、Production
    不得使用 `RAG_ALLOW_NEEDS_REVIEW_CITATIONS=true`）見
    [`docs/project/rag-v3-runtime-policy-integration.md`](docs/project/rag-v3-runtime-policy-integration.md)。
    遠端現行治理資料仍只有 14 筆 official/public chunks 通過普通 RAG filter，來源
    metadata 全都只允許 `care_professional`。2026-08-25 經 owner 明確要求，本機 development `.env` 以
    `RAG_STAGING_ALLOW_ALL_AUDIENCES=true` 暫時讓具明確 audience 的 Elder／Family／Staff 共用仍通過
    public／official／risk／purpose gate 的資料；Elder Google query → Supabase smoke 回傳 5 筆。
    Production 仍不得放寬 audience；runtime policy 啟用時不得與這個 legacy override 併用。這不是
    production deployment；本機暫時重用 Core DB URL，獨立 read-only DB principal、live relevance
    Golden Query／quality gate、v003 Supabase sync／
    activation／rollback 尚未完成，外部 runtime activation／Production 仍封鎖。legacy OpenSearch adapter 保留，
    不接 Neptune，不得描述成 production runtime
    （[ADR 0004](docs/adr/0004-agent-runtime-into-monorepo.md)）。
  - `services/rag-ingestion`：RAG 文件 ingestion 與 allowlist 建置。搭配
    agent-runtime 的 **staging-only** RAG 路徑，尚未對真實 AWS／OpenSearch 環境驗證，
    不得描述成可用於 production（見 `services/agent-runtime/AGENTS.md`）。
  - `packages/frontend`：**唯一的前端**，單一 multi-role PWA，Next.js 16 App Router + React 19，
    同時是 BFF（direct Google／LINE OIDC exchange 與 Core App Session 留在伺服器端，反向代理 core-api）
    （[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）。
    [ADR 0010](docs/adr/0010-provider-neutral-oidc-and-application-sessions.md) 的 direct Google／LINE
    OIDC＋Core-owned opaque Session application flow 已實作：BFF start／callback／onboarding routes、Core
    verifier／handoff／pending identity、App Session authenticator／logout，以及 Google→LINE explicit
    linking 都已存在。[ADR 0015](docs/adr/0015-email-password-primary-authenticator.md) 的 Kinsun-owned
    Email＋Password primary flow 也已實作：credential 綁 Actor、password 使用 Argon2id、verification／
    login 採 bounded attempt 與 lockout，Browser 只經 private BFF→Core boundary 換取 Core App Session。
    目前寄信只有 synthetic development delivery；production email delivery、password reset／change、MFA 與
    breached-password screening 仍未完成。[ADR 0011](docs/adr/0011-bounded-empty-account-consolidation.md) 只允許對沒有正式
    domain data 的 ELDER onboarding 骨架做二次確認後的受限合併；其他情況一律人工覆核，不得依 email
    自動合併 Actor。Cognito runtime、Hosted UI callback、SDK、IaC reference 與 `actor.cognito_sub` 已
    從目前 repository 移除；committed example 的 direct OIDC／App Session gates 仍預設關閉，實際環境
    必須明確注入 provider、transaction、handoff 與 identity secrets。不得把本機可登入描述成雲端 E2E
    已部署驗證。
    前端不拆成多個應用：長者端、照護端、家屬端以 route 區分角色。**不要建立
    `apps/elder-web`／`care-web`／`family-web`**（文件 12 的三-app 骨架，已由 ADR 0006 取代）。
    2026-08-31 起三個角色各自只有一個 route prefix，且 shell 由 route group layout 擁有：
    `app/elder/(app)/*`（layout＝ElderShell）、`app/staff/(app)/*`（layout＝CareSidebar）、
    `app/family/(app)/*`；sign-in 頁刻意留在 group 外，因為 shell 帶著登出與尚無 session 時
    沒有意義的連結。`data-surface="voice"` 由 layout 統一掛上，**不要在 page 自行 import
    ElderShell 或手寫該屬性**——那正是舊寫法讓新頁面靜默失去 640px measure、64px 觸控目標
    （MASTER.md §6.1）與較粗 focus ring 的原因。舊 URL（`/dashboard*`、`/consent` 等）由
    `next.config.mjs` 以 **307 暫時** redirect 承接，IA 未定案前不得改成永久 redirect；
    `src/lib/server/oauth-transaction.ts` 的登入後 allowlist 隨 route 搬移而**不是**新增別名。
    route 搬移由 `src/lib/server/route-migration.test.ts` 釘住 redirect map 與 allowlist。
    2026-09-01 新增平板交接路徑：`/staff/elders/new`（建立長者＋一次性交接）、`/elder/pair`
    （由 URL fragment 或手動貼上 token，POST 給同源 BFF 交換）、`/elder/session`（首次使用
    白話說明、文字陪伴、二次確認的停止、明確結束），BFF 邊界在
    `app/backend/elder-session/*`。BFF 固定 acknowledgement body，**不接受 client 指定的
    policy、actor、reason、deletion、tenant 或 elder scope**；交換 token 時會先清掉該瀏覽器
    既有的 App Session cookie，再設定獨立的 Elder Session cookie。
    ADR 0006 當時要求以 `apps/README.md` 承載這個警告；該檔與空的 `apps/` 目錄已於
    2026-08-06 移除，警告改由本檔承載。要拆成獨立部署單元請先寫 ADR 推翻 0006。
  - `packages/shared`：前端使用的 TypeScript 型別（原本也被已刪除的 legacy backend 共用，
    現在只剩前端一個 consumer，可能有未使用的型別）；不是 Domain authority，
    跨服務形狀以 `contracts/` 為準。
  - `services/speech-gateway`：ASR／TTS adapter 與 Core Voice Ticket／server-side ASR Gate
    整合邊界（`asr.py`、`tts.py`、`sagemaker_asr.py`、`core_voice_gate.py`）。Browser 已有受 Voice
    Ticket 保護的 JSON audio upload 與低信心確認 UI；Gateway 先 consume，再把
    ASR Final 交給 Core 判定，前端不得自行 threshold。華語／英語 managed adapter 與台語／客語
    SageMaker adapter 已有程式與本機測試；WebSocket binary transport、production service credential、
    真實 endpoint、成本與 quality gate 尚未部署／驗證，不得描述成 production 語音路徑。
    2026-09-01 起對 Core 的私有呼叫改用 `src/speech_gateway/service_identity.py` 簽出的
    request-bound 短效憑證（見上方 core-api 條目）；secret 少於 32 bytes 或 TTL 不在 1–60s
    會在啟動時失敗，不是等到第一次呼叫。`/internal/.../voice-confirmation` 與 voice-session
    endpoint 現在於認證後從已存的 ConversationSession 解析 tenant／actor scope，不再信任
    呼叫端傳入的任何值。
  - `services/notification-worker`：只有 LINE Daily Notification 的 scheduler boundary README；可執行
    job 邏輯仍在 Core。沒有 Worker framework，也沒有 Scheduler／SQS／DLQ deployment。
  `projection-worker` 與 `report-worker` 目前不存在；需要時依 §9 的結構與 ADR 建立，不要先放空殼。
- **ADR 0007 判定為 legacy 的那一整套已於 2026-08-06 刪除**（原 `packages/backend`
  → `legacy/backend` 的 TypeScript 後端 155 檔、`infra/bin/app.ts`、`cdk.legacy.json`、
  `infra/lib/elderly-care-stack.ts` 與其專屬 constructs `api`／`data-store`／
  `voice-workflow`、`infra/lambda-stubs/`）。
  [ADR 0007](docs/adr/0007-canonical-backend-and-aws-deployment-authority.md) 的決策不變，
  只是被判死的程式碼不再留在工作樹；要查歷史用 `git log --follow`。
  一般 HTTP 主線只走 Next.js BFF → Python Core → Agent Runtime。歷史紀錄顯示 AWS Hackathon 曾有
  staging foundation 與 application template，但目前沒有使用中的 AWS 服務；可執行 CDK profile、
  AWS preflight／deployment scripts 與 active runbook 已於 2026-09-02 依
  [ADR 0019](docs/adr/0019-retire-aws-cdk-deployment-profile.md) 退役。歷史 AWS spec／ADR／handover
  只保留決策與證據，不得當成現行 resource inventory 或部署能力。四個 runtime／migration image
  仍可由 provider-neutral 的 `scripts/build_runtime_images.ps1`／`.sh` 在本機建立與驗證，但不會
  push registry 或部署資源。Frontend 已依
  [ADR 0008](docs/adr/0008-next-16-supported-release-upgrade.md) 升至受支援 release，且本機
  production audit／Linux image smoke 已通過；這只解除 framework dependency blocker，
  不代表 registry push、provider callback、application deploy 或公開流量 gate 已完成。
- **CI quality gate 已啟用**：`.github/workflows/gate1.yml`（Gate 1 Quality Gate）於 2026-08-26
  建立，在對 `main` 的 pull request 與 push 觸發，在 `ubuntu-latest` 搭 pinned pgvector service
  container 執行，timeout 30 分鐘。涵蓋範圍：
  - Core API `ruff check`、`scripts/rag/project_postgres.py dry-run`、`tests/unit` 與
    **`tests/integration`**。CI 自建 disposable `kinsun_test` database，**這是目前唯一會實際執行
    Core integration 測試的環境**；本機因為沒有獨立 `TEST_DATABASE_URL` 一直略過。
  - Agent Runtime、Speech Gateway、RAG Ingestion 三者各自的 `ruff check` ＋ `ruff format --check`
    ＋ `pytest`。
  - 靜態 `validate_contracts.py` 與兩支 live verifier。live verifier 以 `httpx.ASGITransport`
    就地 `create_app()`，不需要另外啟動服務。
  - 五輪 synthetic Core-to-Agent 證據（`scripts/verify_gate1_cross_service.py`），成功時上傳
    artifact 保留 30 天。
  - Frontend `npm ci`／typecheck／test／lint／production build。
  - **注意：core-api 只跑 `ruff check`，不跑 `ruff format --check`**，所以本機 format 未通過的
    既有檔案不會擋 CI；不要因為 CI 綠燈就認定 core-api format 是乾淨的。
  - **新增 router／model 時，import 字母序是 CI 等級的地雷。** `8adba0f` 把
    `assisted_elders` 排在 `assignments` 之前、`assisted_elder_session` 排在 `asr_gate` 之前，
    使 `app/main.py` 與 `app/models/__init__.py` 各出現一個 `I001`；`ruff check` **在 CI 內**，
    等於直接擋住 gate1。同一個 commit 也讓 agent-runtime 的 `context/manifest.py` 與
    `contracts/models.py` 沒過 `ruff format --check`，那項對 agent-runtime **同樣在 CI 內**。
    兩者已於 2026-09-01 修掉。排序是 ASCII 比較（`assignments` < `assisted_*`、
    `asr_gate` < `assisted_*`），肉眼很容易排錯：新增 import 後先跑一次該服務的
    `ruff check`／`ruff format --check`，不要靠 review 目測。
- 已被 `gate1.yml` 取代的 `.github/workflows-disabled/pr.yml` 已於 2026-09-02 隨 AWS CDK profile
  一併移除；不要重建或啟用該草稿。外部部署 endpoint 可用 provider-neutral 的
  `scripts/smoke_test_deployment.py` 驗證，但結果不代表 hosting infrastructure 已完成。
- 不得把 Target Architecture、建議目錄或候選服務描述成已實作功能。
- 開始實作前，先確認工作項目對應的 Persona、User Story、Acceptance Criteria、Domain State、Security Gate 與 Test Gate。

### 技術棧與刻意未採用項目

| 範圍 | 已採用 | 不要自行引入／誤判 |
| --- | --- | --- |
| Core | Python 3.12、FastAPI、SQLAlchemy 2 async、Alembic、PostgreSQL 16、uv | Django、Flask、同步 ORM、第二套 schema 管理器 |
| Agent／RAG／Speech | Python 3.12、FastAPI、Pydantic、boto3、OpenSearch adapter、uv | 自由 Agent loop、直接 SQL／DSL、未受控 SDK 呼叫 |
| Frontend／BFF | Next.js 16 App Router、React 19、TypeScript、CSS Modules、npm workspaces | Vite、Tailwind、獨立 elder／care／family apps、browser-held access token |
| Deployment | 目前沒有 production IaC；runtime 以環境變數／adapter 解耦 | 未經 ADR 選定 provider／IaC、legacy Lambda／DynamoDB backend、恢復 Cognito |
| Contract | OpenAPI 3.1、AsyncAPI、JSON Schema、Pydantic | 未實作先寫 executable contract、相對 `$ref`、寬鬆額外欄位 |

## 2. 規格來源與優先順序

需求解讀依下列順序：

1. `docs/spec/01智慧長照 AI 陪伴系統－產品方向與範圍基準 v1.2.md`：產品範圍、成功條件與非目標。
2. `docs/spec/01A智慧長照 AI 陪伴系統－使用者研究與 Demo Persona v0.2.md`：Persona、情境與證據邊界。
3. `docs/spec/02智慧長照 AI 陪伴系統－使用者故事與驗收條件 v1.3.2.md`：User Story 與 Acceptance Criteria。
4. `docs/spec/03智慧長照 AI 陪伴系統－Story Map v1.2.md`：Wave、Gate、Backlog 狀態與 Demo
   Traceability（原 .xlsx 的六個工作表都保留成 markdown 表格）。
5. `docs/spec/` 的 `06`、`07`、`10`、`11`：Domain、Security、Contract 與 Test 規格。
6. 其他 `docs/spec/` 文件：UX、Workflow、AWS、Agent、交付、維運、評估與退場規則。
7. 新增且明確取代舊條款的 Accepted Target spec／ADR。目前
   [Spec 17](docs/spec/17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md)
   處理 Account／Elder 分離；[Spec 18](docs/spec/18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)
   處理 Memory Policy，並在其明列的衝突範圍內優先於舊規格。

**`docs/spec/*.md` 是規格的權威版本。** 2026-08-06 之前同一份內容存在四種格式——`.md`、
結構化 `.json`、Story Map 的 `.csv`、以及 `origin/` 的 `.docx`／`.xlsx` 原始檔，其中
`origin/` 曾被指定為權威。四份無人同步維護，且 `.json` 沒有任何程式讀取、`.csv` 的內容
已完整含在 Story Map 的 `.md` 裡，二進位原始檔則無法 grep 或 diff。現已只留 `.md`。
需要原始檔時用 `git log --follow` 或 `git show <commit>:docs/spec/origin/<檔名>` 取回。
Google Drive 上的團隊文件若與此處不一致，依下方衝突規則處理。

若文件互相衝突：

- 不要自行挑選最方便的版本。
- 優先採取較安全、較不會洩漏資料、較可回復的行為。
- 在 PR／變更說明中列出衝突、採用的暫定解讀與需要 Owner 決策的項目。
- 目前已知需要收斂：01／02 與 07／11 的延遲門檻不完全一致；Story Map 總覽可能有 Wave 標籤重複。

## 3. 核心交付順序

第一條 Gate 1 Vertical Slice 是主要實作脊柱：

1. 林阿嬤明確同意後開始語音互動。
2. ASR 對低信心內容要求簡短確認，不假裝辨識成功。
3. Orchestrator 產生安全、簡短且符合語言偏好的回覆。
4. Agent 的 Event／Memory 輸出只能是 proposal；Event 先成為 Candidate，Memory 由 Core policy 決策。
5. 長期記憶先驗有效總體 Consent 與 Speaker：LOW all-of 才可自動保存，MEDIUM 由長者對固定版本
   明確確認，HIGH 不建立 Memory；照護事件仍依規格完成人工覆核。
6. 正式狀態寫入 PostgreSQL，並透過 Transactional Outbox 發布。
7. Neptune／OpenSearch 完成可追蹤、可重建的 Projection。
8. 後續對話只能重用每次通過 current ACTIVE、Consent、Speaker、verification、version binding、
   validity、tenant／elder scope 與 tombstone deterministic Gate 的 Trusted Memory。
9. 產生有來源連結的 Daily Summary，供照服員覆核。
10. 保存 Demo、Trace、Contract、Safety 與 Failure-path 證據。

Wave 順序：

- Wave 1：Voice、Event、Confirmed Memory、Graph reuse。
- Wave 2：照服員摘要、覆核與待辦。
- Wave 3：RAG、Care Signal、家屬報表／通知、受控主動陪伴、English。
- Wave 4：遊戲、Gamification、低資源語言與進階 ASR。

除非使用者明確改變優先順序，不要為後期功能犧牲 Gate 1 的可演示閉環。

## 4. 不可違反的產品與安全邊界

- 不提供診斷、治療建議或取代專業照護決策。
- 不把模型輸出、推論、缺少資料或失敗結果描述成已確認事實。
- MEDIUM 未確認／stale confirmation、HIGH、unverified Speaker、失效 Consent 或不符 lifecycle／scope 的
  Memory 不得進 Trusted Memory、Graph、報表或後續對話事實；LOW 必須通過 Spec 18 的 all-of policy。
- 未覆核的 Event Candidate 不得成為 Verified Event。
- Draft Family Report 不得被家屬或通知預覽取得。
- Family App／Web 的 `PUBLISHED` Report 是正式內容來源；LINE／Email 只能做最小通知與安全連結。
- 長者的「不要記」、「不要再提」、「停止」與 Consent Revocation 必須立即優先於 Retry、Replay、Backfill、Scheduler 與主動陪伴。
- 不使用恐懼、內疚、壓力、欺騙或情緒依賴設計提高互動率。
- Demo、測試、Eval 與截圖只能使用 Synthetic 或完成去識別的資料。

零容忍結果：

- Cross-elder 或 Cross-tenant 資料暴露。
- 未授權讀寫、Tool 執行或 Consent bypass。
- Secret、Token、完整 Prompt、完整 Transcript／Audio 出現在一般 Log。
- SQLAlchemy development `echo` 也不得輸出 bind parameter；engine 必須維持
  `hide_parameters=True`，避免 Email、credential hash、token digest 或其他 Restricted Data
  因本機 SQL diagnostics 寫入 log。
- 醫療危險建議。
- 未確認記憶被當成事實。
- 已刪除或已撤回資料因 Replay／Projection rebuild 再次出現。
- Draft Report、錯誤收件或超出 Family Share Scope 的內容外洩。

## 5. Authorization、Consent 與資料範圍

- 採 RBAC + ABAC，並預設拒絕。
- 每次正式讀取、寫入及 Agent Tool Command 都由 Core 重新驗證：
  - `tenant_id`
  - `elder_id`
  - `care_unit_id`
  - relationship／family share scope
  - assignment
  - consent purpose／version
  - actor role
  - resource state
  - time／purpose
- 不信任 Client 或模型傳入的 Actor、Tenant、Elder、Assignment 或 Permission Scope。
- 單一資源的「未授權」與「不存在」必須回一致的回應，避免以回應差異探測資源是否存在。
- 失敗的授權不得產生資料修改、Outbox Event 或其他副作用。
- Consent Purpose 必須分離，不得以單一總開關代替：
  - `BASIC_VOICE`
  - `TRANSCRIPT_STORAGE`
  - `CARE_EVENT_EXTRACTION`
  - `LONG_TERM_MEMORY`
  - `COMPANION_SIGNAL_ANALYSIS`
  - `PROACTIVE_COMPANION`
  - `FAMILY_SHARING`
- Consent 撤回後先停止未來處理，再依 Retention／Deletion Workflow 處置資料。

## 6. 架構不變量

- PostgreSQL／Domain Core 是正式交易資料與狀態的 Source of Truth；目前 provider 是 Supabase
  PostgreSQL，不使用 Supabase Auth 或專有 Data API。
- **開發與登入／註冊 E2E 預設直接連 Supabase PostgreSQL**：由 repository 根目錄未版控的
  `.env` 提供 `DATABASE_URL`，一般開發、除錯、migration 檢查與 E2E 不啟動 Docker、
  `docker compose` 或本機 PostgreSQL。只有使用者明確要求 Docker 隔離環境時才可例外。
- Supabase development database 不得承接破壞性的 integration rebuild、`downgrade base`、reset、
  truncate 或 fixture 全量重建。需要這類測試時，必須另有可丟棄且與 development database 分離的
  `TEST_DATABASE_URL`；沒有就略過並如實回報。
- Neptune、OpenSearch、Cache 與 Agent Memory 是 Projection 或 Working State，必須可由正式資料重建。
- 不從 Graph、Search 或模型輸出反推正式授權或正式狀態。
- 正式寫入使用 Transactional Outbox；採 Outbox → EventBridge → 每個 Consumer 專屬 SQS／DLQ。
  **正式寫入與 Outbox 寫入必須位於同一交易**，不得先 commit 再補發。
- Projection 只接受已通過狀態、授權、同意與刪除檢查的正式資料。
- 不使用 Database + Graph／Index／Event Bus 的無保護 Dual Write。
- 非同步 Consumer 必須 Idempotent、可重試、可觀測，並在處理前重新檢查撤回、刪除與 Scope。
- 長流程／人工流程使用顯式 State Machine；不得以隱含 Prompt 狀態代替 Domain State。
- 正式刪除使用 Tombstone 防止 DLQ Replay、Backfill、Graph rebuild、Index rebuild 或 Backup restore 復活資料。

歷史 AWS Target Architecture 曾包含：

- Single multi-role PWA。
- Python modular monolith on ECS/Fargate。
- API Gateway HTTP／WebSocket；身份驗證以 Kinsun Email／Password＋Core App Session 為 primary，
  direct Google／LINE OIDC 為 optional provider handoff。
- Bedrock AgentCore Runtime、Bedrock Models／Guardrails。
- Aurora PostgreSQL、Neptune Serverless、OpenSearch Serverless、S3。
- EventBridge、SQS／DLQ、Step Functions、Scheduler。
- SES／LINE Notification Adapter。

以上只保留為歷史規劃，不代表服務已建立，也不是現行 deployment baseline；可執行 CDK profile 已由
ADR 0019 退役。

## 7. Agent 與 AI 實作規則

- 採受控 Orchestrator，不建立 Agent Debate、無限遞迴或自由互相呼叫。
- 同步流程上限依 Agent 規格：最多 3 次模型決策、2 輪 Tool、5 次 Tool Call，以及 1 次 Rewrite／Context rebuild；若規格更新則依新版本執行。
- 上述是安全上限，不代表目前都已實作。現行 runtime 只有一次模型決策、optional RAG 與
  deterministic Event／bounded Memory Candidate proposal；沒有通用 Tool loop，也不會從
  `allowed_tools` callback Core。Memory first slice 只辨識明確固定早餐習慣，不推論健康、情緒、
  陪伴需求或一次性事件；proposal 必須先隨 Event Candidate 保存，來源事件 VERIFY 後才可由 Core
  建立仍需長者本人確認的 Memory Candidate。這段只描述 Current；Target 的 Agent＝proposal、Core＝
  decision、Event／Memory 分離、LOW／MEDIUM／HIGH 與 Speaker Gate 依 Spec 18／ADR 0014。
  Canonical path 由 Core 以 `requested_outputs` 要求最小 proposal，再由 Core 重驗授權與 Consent 後寫入。
- Agent 只能呼叫 Allowlist 中且有版本的 Tool。
- 高風險 Tool 即使由 Agent 選擇，也必須由 Python Core 重新執行 Authorization、Consent、State 與 Idempotency 檢查。
- Context 目標層次是 Policy → Auth → Consent → Current turn → Session → Trusted memory after deterministic
  retrieval gate →
  Verified care data → Graph → RAG → Tool results → Output constraints。`BASIC_VOICE` canonical path
  已能在 Core 重驗 `memory:read` 與 active `LONG_TERM_MEMORY` Consent 後，帶入同 tenant／elder、
  current version、`ACTIVE`、未刪除且不超過目前 Consent version 的最近 5 筆 Confirmed Memory；
  Knowledge／RAG purpose 不得夾帶私人記憶。這是 bounded first slice，尚未有語意相關性排序；
  Verified care data／Graph 仍未接入 Agent Context。
- 每次重要 Agent 執行需能追溯實際的 Agent、Prompt、Model route、Policy、Guardrail、Tool schema、Context manifest 與 Release Version。
- RAG 必須保存來源、版本、有效日期、覆核狀態與 Metadata Filter；沒有可靠來源時明確回覆資料不足。
- LLM-as-Judge 不得覆蓋 Deterministic Security／Schema／Permission Gate。

## 8. API、Event 與版本規則

- REST 使用 `/api/v1/...` Major Path Version。
- WebSocket 只傳輸 Voice Session State 與已定義事件，不暴露內部 Prompt、Agent Trace、Secret 或其他長者 Context。
- OpenAPI 3.1、AsyncAPI 與 JSON Schema 是機器可驗證 Contract，放在 `contracts/`。細節見 §8.1、§8.2。
- API、Domain Event、Agent Handoff、Tool、Candidate、Report 與 Export 都需要 Schema Validation。
- 正式 Event 發布後視為不可變歷史契約；破壞性變更建立新 `event_version`。
- Consumer 先支援新舊版本，Producer 才切換。
- Database 變更採 Expand → Migrate → Contract。
- 使用 Idempotency Key、Optimistic Concurrency、Correlation／Causation ID 與明確 Error Code。
- 不可只記錄 `latest`；需保存實際使用的 API、Event、Schema、Agent、Prompt、Model、Policy、Speech、RAG、Graph、Export 與 Release Version。

## 8.1 Contract 規格

### 目前狀態

`contracts/` **以目前實作為準，不是以文件 10 為準**。兩者在 envelope 結構、錯誤欄位與
狀態碼對應上有實質差異，以 [`contracts/DIVERGENCE.md`](contracts/DIVERGENCE.md) 追蹤。
**改動 contract 或 API 之前先讀那份清單並跑 validator**；其更新日期與末段「尚未實作」摘要可能
落後於 2026-08-10 之後的 Voice／LINE／Auth 變更，不能只看單一段落判定現況。

2026-09-01 靜態驗證基準：Core OpenAPI 76 paths／81 operations（`info.version` 1.6.0）、
Agent Runtime OpenAPI 3 paths、AsyncAPI 1 channel；Core app 實際有 80 paths／85 operations
（同一路徑可含多個 method）。多出來的 4 條全部是 FastAPI 自動掛的 `/docs`、
`/docs/oauth2-redirect`、`/openapi.json`、`/redoc`——**每一條實際 API path 都已登記在 contract**，
反向也沒有 contract 有而 app 沒有的 path。`contracts/openapi/core-api.v1.yaml` 副檔名是 `.yaml` 但
**內容其實是 JSON**（由 `scripts/export_core_openapi.py` 產生），用 YAML 縮排規則 grep 會得到 0。
數字會隨實作變更，應以 `scripts/validate_contracts.py` 與 live verifier 的當次輸出為準，
不要手動維護第二份 operation 清單。

若你的變更消除或新增了一項差異，同步更新 `DIVERGENCE.md`。

### 目錄與檔名

```
contracts/
├── openapi/<service>.v<major>.yaml   REST，一個服務一份
├── asyncapi/<service>.v<major>.yaml  Domain Event；目前有 core-events.v1.yaml
├── schemas/
│   ├── common/    跨領域共用：envelope、分頁、錯誤
│   ├── domain/    業務 DTO
│   ├── events/    Domain Event envelope／failure payload
│   ├── rag/       RAG ingestion／retrieval
│   ├── tools/     Agent Tool request／result
│   └── agent/     Agent Run、Handoff、Context Manifest、Safety Evaluation
└── examples/{valid,invalid}/
```

### 命名

- Schema 檔名與 `title` 為 PascalCase＋版本：`ElderSummaryV1.json`（文件 10 §3.1）。
- `$id` 用絕對 URI：`https://kinsun.ai/contracts/schemas/<dir>/<Name>.json`。
  跨檔 `$ref` 一律指 `$id`，不要用相對路徑，否則換工具就解不開。
- JSON 欄位 snake_case；REST 路徑複數名詞、kebab-case；時間 ISO 8601 UTC。
- ID 一律 UUID，不得暴露遞增流水號。

### 硬性規則

- **`additionalProperties: false`**。契約要能擋下多餘欄位，否則洩漏了也測不出來。
- **enum 必須與 `eldercare_ai` schema 一致**（PG ENUM 的 label 或 CHECK 的允許值）。
  contract 比資料庫寬鬆，錯誤會延到 INSERT 才爆；比資料庫嚴格則是合法的收斂。
- **分頁只能用 opaque cursor**，不得出現 `offset`、`page_number` 或 `total`。
  可猜測的 offset 違反文件 10 §4.6；`total` 會洩漏授權範圍外的長者數量。
- **不得包含 Restricted Data**：逐字稿、ASR 信心值、內部筆記、未覆核事件、
  診斷式分數、Secret、完整 Prompt。家屬版尤其要對照 §4 的零容忍清單。
- 錯誤訊息欄位不得回填被拒絕的原值，若該值本身是敏感資料。
- `security` 區塊描述的是目前 executable authentication；若 verifier 尚未實作，必須在 description
  明說，不得讓讀者誤以為 credential 已被驗證。

### 範例

- `examples/valid/` 至少一個，代表正常回應。
- `examples/invalid/` 至少一個，且**必須帶 `_why_invalid` 欄位**說明為何該被拒絕。
- invalid 範例通過驗證＝schema 太寬鬆，視同測試失敗。這些範例的用途是把
  「差點寫錯的地方」變成由測試守著，不是湊數。

## 8.2 何時要新增或更新 Contract

### 必須新增

- 新 endpoint、新 Domain Event、新 Agent Tool **實作完成之後、合併之前**。
- 既有 endpoint 新增欄位、新增狀態碼、或改變分頁／篩選行為。
- 新增 enum 值（同時檢查 §9 的 baseline 對齊要求）。

### 不得新增

- **尚未實作的 API 不寫進 contract**（§1）。需要先給前端一個形狀時，寫進
  `docs/` 的設計文件或 spec，不要放進 `contracts/`——`contracts/` 的語意是
  「這個可以現在打」。
- 不要為了讓驗證通過而放寬 schema。schema 與實作不符時，先判斷哪一邊錯了。

### 更新既有 contract

先判斷變更類型（文件 10 §22）：

| 類型 | 例子 | 做法 |
| --- | --- | --- |
| 相容 | 新增選填欄位、新增 enum 值、放寬長度上限 | 直接改，同一 major |
| 破壞性 | 刪欄位、改欄位名、改型別、收緊 enum、改 envelope 結構 | 走 Deprecation 流程，新 major |

破壞性變更依 §8 的規則：Consumer 先支援新舊版本，Producer 才切換。

### 流程

1. 確認實作真的完成，且能實際呼叫。
2. 改／新增 `schemas/` 底下的 JSON Schema。
3. 改 `openapi/`，以 `$ref` 指向 schema，不要把 schema 內嵌重複一份。
4. 補 `examples/valid/` 與 `examples/invalid/`。
5. 兩支驗證都要通過，缺一不可：

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts

cd services/core-api
$env:DATABASE_URL = "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun"
uv run --with pyyaml --with jsonschema --with referencing python ../../scripts/verify_contract_live.py ../../contracts
```

第 2 支是對**執行中的服務**驗證。沒有跑過它的 contract 不算數——契約的價值在於
它與現實一致，只通過自我驗證的契約只是散文。新增 endpoint 時，記得同步在
`scripts/verify_contract_live.py` 加上對應檢查，否則它永遠只驗舊的那幾條。

6. 若變更牽涉 `DIVERGENCE.md` 列出的任何一項，同步更新該檔。

## 8.3 回應與例外處理慣例

契約要能穩定，回應與錯誤的組裝方式就必須只有一條路。

- 對外 API 一律以 `SuccessEnvelope` / `ErrorEnvelope`（`app/core/envelopes.py`）
  作為統一回應格式，不得讓任何 endpoint 自行拼裝頂層結構。
- 服務層可以保留 `AuthorizedEldersResult` 這類明確的資料容器（frozen dataclass）
  來表達方法回傳結果。**服務層回傳 domain 型別，由 API 層轉成 envelope**，
  不要讓 service 認識 HTTP。
- **不要在 service 層拼裝 HTTP 錯誤 payload**。一律拋 `DomainException` 的子類，
  由 `app/api/error_handlers.py` 統一轉為 `ErrorEnvelope` 與對應狀態碼。
- 例外流程固定為：`DomainException → error_handlers → ErrorEnvelope`。
  這樣狀態碼對應只有一份（`EXCEPTION_MAP`），不會每個 endpoint 各寫一套而逐漸分歧。
- 非 `DomainException` 的例外若需要特定狀態碼，要在 `register_exception_handlers()`
  明確註冊，否則會掉進 catch-all 變成 500。已知案例：
  `NoAuthenticatorConfiguredError` 必須是 401（fail closed），不是 500。
- 錯誤訊息在 production 會經 `_sanitize_message()` 過濾；不要依賴訊息內容傳遞
  結構化資訊，那是 `code` 與（待補的）`reason_code` 的職責。

### 跨層 mapping（不要自行猜）

| 邊界 | 外部／Runtime 值 | Core／DB 值 |
| --- | --- | --- |
| ORM 主鍵 | Python 一律 `model.id` | 實體欄位如 `actor_id`／`elder_id`，由 `__pk_name__` 對應 |
| Agent actor role | `elder`／`family`／`system`，其他可信角色映成 `staff` | `ELDER`／`FAMILY_MEMBER`／`SYSTEM_SERVICE` 等正式 actor role |
| 語言 | `zh-TW`／`nan-TW`／`hak-TW`／`en-US` | `ZH_TW`／`NAN_TW`／`HAK_TW`／`EN_US`；`MIXED`、`UNKNOWN` 暫映 `zh-TW` |
| Agent result | `SUCCESS`／`BLOCKED`／`SAFE_FALLBACK`／`FAILED` | AgentRun 保存 `SUCCESS`／`BLOCKED`／`HUMAN_REVIEW`／`DEPENDENCY_FAILED` |
| Auth credential | 一般 endpoint 只收 `ks1_` Core App Session；`ep1_`（一次性 pairing）與 `es1_`（Elder Session）只由 assisted-session 專屬 dependency 解析，另有 `X-Kinsun-Service-Credential` 供 Speech→Core | Session／Actor／Membership 每次由 live DB 重查；assisted 憑證不帶可信 claim，initiator ActorContext 由 Core 重建；失敗不得 fallback |

上述 mapping 的 executable authority 分別位於 `services/core-api/app/services/companion_service.py`、
`services/core-api/app/middleware/auth.py` 與各 ORM model；跨層改值時要同時更新 contract、migration、
adapter、前端 label 與測試，不能只改其中一層。

## 9. 程式與 Repository 工作方式

- 已核准的主線不得自行替換：Core／Agent／Speech 用 Python＋FastAPI＋uv，Frontend 用 Next.js＋npm
  workspaces。Production hosting provider、IaC 與 region 尚未定案；需要選擇時先提出候選、Trade-off
  與 ADR，取得明確決策後再建立骨架，不得復原歷史 CDK profile 代替新決策。
- Repository 結構（2026-09-01 實際狀態，非文件 12 的原始骨架）：

```text
kinsun.ai/
├── .github/               CI；workflows/gate1.yml 已啟用
├── .kiro/                 Kiro specs 與 hooks；steering 只轉發本檔，不重述規則
├── .qa/                   手動執行的 smoke／schema 驗證腳本（Supabase、登入、RAG、assisted session）
├── config/                RAG 與 LINE 設定；config/rag 由 agent-runtime、rag-ingestion 共用
├── contracts/             OpenAPI、AsyncAPI、JSON Schema、valid/invalid examples
├── data/                  RAG chunks、manifest、seed
├── docker/                docker-compose 引用的 PostgreSQL 初始化腳本
├── evals/speech/          Synthetic speech evaluation 工具、fixtures 與結果
├── docs/
│   ├── spec/              17 份規格 Markdown（唯一保留格式，見 §2）
│   ├── design-system/     MASTER.md：視覺、RWD、無障礙規範
│   ├── adr/               ADR
│   ├── architecture/      架構文件
│   ├── handover/          交接紀錄
│   ├── ownership/         範圍與責任分工
│   ├── demo/              Demo 資產（含 demo/ui/，前端與 ADR 0006 引用）
│   ├── runbooks/          維運手冊
│   └── project/           Kiro 開發證據、交付狀態、DB schema 快照
├── packages/
│   ├── frontend/          單一 multi-role PWA＋BFF（Next.js App Router）
│   └── shared/            前端使用的 TypeScript 型別
├── scripts/               Contract 與 repository 驗證腳本
└── services/
    ├── core-api/          正式 Domain Core 與 API
    ├── agent-runtime/     受控 Agent Runtime
    ├── rag-ingestion/     RAG ingestion 與 allowlist 建置
    ├── speech-gateway/    ASR／TTS、Core Voice Gate 與 SageMaker adapter
    └── notification-worker/ 只有 scheduler boundary；job 邏輯仍在 Core
```

- **分類軸線是 runtime／toolchain，不是 app／library。** Python 服務進 `services/`，npm
  workspace 成員進 `packages/`（根 `package.json` 的 `workspaces` 字面上就是
  `["packages/*"]`）。**不要套用 Turborepo／Nx 的 `apps/` vs `packages/`
  慣例**——這個 repo 從未採用它，證據是 `services/core-api` 同樣是可部署應用卻也不在
  `apps/`。文件 12 的 `/apps` 是被 ADR 0006 廢掉的三-app 方案殘骸，已於 2026-08-06 移除。
- 文件 12 原本只有 `.gitkeep` 的 `/tests`、`/ops` 已移除；`evals/` 後來因 multilingual speech
  evaluation 重新建立，現在只有 `evals/speech/` 有實質內容。**不要用空目錄表達規劃**；真的有
  executable evaluation／test／ops artifact 時才建立對應目錄。
- **`config/rag/` 不要搬。** 路徑寫死在 `agent-runtime/src/agent_runtime/settings.py`、
  `agent-runtime/Dockerfile`、`Dockerfile.dockerignore`、`.env.example` 與
  `tests/unit/test_container_contract.py`（有測試在守），且由 agent-runtime 與 rag-ingestion
  共用。搬進任一服務底下都會讓另一個服務跨目錄取用。
- 在 Framework 與 Deployment 設計核准前，只維持中立的服務／責任邊界，不加入框架專屬內部結構。

### 分層規則

- API route 只處理 HTTP 邊界、呼叫 service 並包裝 envelope。
- Service 協調 domain、policy、repository 與 outbox，不組裝 HTTP 錯誤。
- Policy 採 deny-by-default，正式授權資料必須由 server-side context 取得。
- Repository 查詢必須明確攜帶 tenant scope。
- ORM model 只負責資料映射；schema 變更由新的 Alembic revision 管理。
- 外部 Provider／SDK 只能出現在 adapter 或 provider 邊界，不散入 domain 與 orchestration。
- Contract 只描述已實作、可實際呼叫的介面；未實作設計放在 `docs/` 或 Kiro Spec。

### 變更同步

- Endpoint 或 envelope 改變時同步 contract、examples、live verification 與 divergence 文件。
- Domain state 改變時同步 migration、tests、traceability 與必要文件。
- 不建立第二份 schema、authorization mapping 或 response mapping 作為競爭權威來源。
- 目前開發資料庫以 repository 根目錄 `.env` 的 `DATABASE_URL` 直接連 Supabase PostgreSQL：
  - 一般工作不得自行啟動 `docker-compose.yml`、本機 PostgreSQL 或 Adminer。
  - `docker-compose.yml` 與 `docker/postgres/init/` 只保留為可重建參考與使用者明確要求時的隔離工具，
    不是預設開發路徑；初始化腳本不得成為第二個 Schema Source of Truth。
  - Schema 仍只由 Alembic 管理；Supabase 只提供 PostgreSQL，不使用 Supabase Auth 或專有 Data API。
  - `.env` 不進版控；新增設定時同步維護無 Secret 的 `.env.example`。
- Core API 已定案，程式在 `services/core-api/`：
  - 套件與環境管理採 uv（[ADR 0001](docs/adr/0001-package-manager-uv.md)）；`uv.lock` 必須進版控。
  - Web Framework 採 FastAPI ＋ SQLAlchemy 2.0 async（[ADR 0003](docs/adr/0003-core-api-framework-and-schema-authority.md)）。
  - 兩個 driver 並存且刻意如此：Alembic 用同步的 psycopg，應用層用非同步的 asyncpg。
    `DATABASE_URL` 只維護一份，寫成 asyncpg 形式，`alembic/env.py` 自行轉換。
  - Table／Index／Constraint／Trigger 一律由 Alembic 管理，PostgreSQL schema 名稱為 `eldercare_ai`。
  - v0.1 baseline 是凍結的 SQL 快照並以 SHA-256 驗證（[ADR 0002](docs/adr/0002-alembic-baseline-strategy.md)）。
    已套用的 migration 不可變；要改 schema 就新增 revision。
  - Windows checkout 可能把 baseline SQL 從 LF 轉成 CRLF，導致內容看似相同但 SHA-256
    驗證失敗。`.gitattributes` 必須維持
    `services/core-api/alembic/versions/sql/*.sql text eol=lf`；遇到 checksum 不符時，
    先檢查並將工作樹換行正規化為 LF，不得修改凍結 SQL 內容或預期 checksum 來讓驗證通過。
  - `docs/project/smart_eldercare_schema_v0_1.sql` 與 baseline **逐位元相同**
    （122058 bytes），依 ADR 0002 §63 保留為設計產出物與 ER 圖匯入來源（`COMMENT ON
    TABLE／COLUMN` 匯進 DBeaver／DataGrip 可顯示欄位說明）。它**不是** schema 權威——
    §9「不建立第二份 schema 作為競爭權威來源」仍然適用，要改 schema 一律新增 Alembic
    revision。2026-08-06 前它沒有 `.gitattributes` 保護，Windows 工作樹上是 CRLF
    （123925 bytes），與 ADR 0002 宣稱的逐位元相同不符；現已補上
    `docs/project/*.sql text eol=lf`。兩份若出現實質差異，以 Alembic baseline 為準。
  - ORM model 的 Python 屬性統一是 `id`，實際對應各表自己的 PK 欄位（`__pk_name__`）。
    新增 model 時必須宣告 `__pk_name__`，否則 SQLAlchemy 會在 class 建立時失敗。
  - **domain enum 的每個值都必須在 baseline 中存在**（PG ENUM 的 label 或 CHECK 的允許值）。
    加了沒有 migration 的值，錯誤會在 INSERT 當下才爆，不是驗證期。
  - 2026-09-02 工作樹有 29 個 revision，head 是 `d0e4f6a8b901`。baseline 仍是 48 張 table，
    後續 revision 另外加了 `elder_enrollment`、`elder_care_profile_entry`、
    `assisted_elder_session` 等表；`app/models/` 目前宣告 51 個 `__tablename__`。
    `alembic revision --autogenerate` 仍會把未映射 table 誤判為應刪除；產生的 migration
    一律需人工檢查後才可使用。
- 前端已定案，程式在 `packages/frontend/`（[ADR 0006](docs/adr/0006-frontend-stack-and-app-topology.md)）：
  - Next.js 16 App Router + React 19 + TypeScript。**不是 Vite，不用 Tailwind**；
    樣式一律 CSS Modules ＋ `src/app/tokens.css` 的 CSS 變數。
  - TypeScript 側用 npm workspaces（根 `package.json` ＋ `package-lock.json`），
    與 Python 側的 uv 不共用。
  - 視覺、RWD 與無障礙規範見 [`docs/design-system/MASTER.md`](docs/design-system/MASTER.md)，
    建立任一頁面前先讀。元件內不得出現 raw hex（MASTER.md §14）。
  - 前端是 BFF：OAuth code exchange 與 access token 只存在伺服器端，
    token 不得進入瀏覽器可讀的位置。`src/app/backend/core/[...path]` 以 header
    allowlist 轉發，**不轉發 cookie**；新增轉發欄位前先確認不會夾帶憑證。
  - 家屬端的資料紅線（MASTER.md §11）在前端也要擋一次，不得只依賴後端不回傳。
  - UI 語言切換（`src/lib/i18n/`）只改瀏覽器偏好，**不得寫入任何 domain state**，
    尤其不得改動長者語言偏好或 consent。新增使用者可見字串時同時補 `zh-Hant` 與 `en`。
- 優先做最小、可測試、可回復且能貫穿 Vertical Slice 的變更。
- 不進行與任務無關的大規模重構、格式化、依賴升級或文件重寫。
- 保留使用者既有變更；不要以 Reset、Checkout 或大量覆寫清除未知修改。
- 任何變更需要 Push 到遠端時，必須先從最新的 `origin/main` 建立新的工作分支；
  禁止直接 Push `main`，也不得沿用混有其他任務變更的既有分支。
- 任何狀態或契約變更都同步更新相關 Schema、Test、Traceability 與必要文件。

### 常用檔案位置

| 工作 | 位置 |
| --- | --- |
| Core routes／services／repositories | `services/core-api/app/api/`、`app/services/`、`app/repositories/` |
| Authentication／Session | `services/core-api/app/middleware/auth.py`、`app/adapters/auth/`、`app/services/*identity*`、`*session*` |
| Service-to-service identity | `services/core-api/app/adapters/service_identity.py`、`app/middleware/speech_service_auth.py`、`services/speech-gateway/src/speech_gateway/service_identity.py` |
| Assisted Elder Session | `services/core-api/app/api/assisted_elders.py`、`app/services/assisted_elder_session_service.py`、`app/services/assisted_session_tokens.py`、`app/services/elder_onboarding_service.py` |
| 平板交接前端／BFF | `packages/frontend/src/app/elder/pair/`、`src/app/elder/session/`、`src/app/backend/elder-session/`、`src/lib/server/elder-session-cookie.ts` |
| 手動 smoke／schema 驗證 | `.qa/`（需要真實 Supabase 連線，不在 CI 內，執行前先確認是唯讀或可回復） |
| DB models／migration | `services/core-api/app/models/`、`services/core-api/alembic/versions/` |
| Agent request／orchestration／provider | `services/agent-runtime/src/agent_runtime/contracts/`、`orchestration/`、`models/` |
| RAG config／runtime／ingestion | `config/rag/`、`services/agent-runtime/src/agent_runtime/rag/`、`services/rag-ingestion/` |
| Speech boundary | `services/speech-gateway/src/speech_gateway/`；低資源模型在 `services/speech-gateway/sagemaker/` |
| Frontend pages／BFF／API client | `packages/frontend/src/app/`、`src/lib/server/`、`src/lib/api/` |
| UI tokens／translations | `packages/frontend/src/app/tokens.css`、`packages/frontend/src/lib/i18n/messages.ts` |
| Contracts／差異／驗證 | `contracts/`、`contracts/DIVERGENCE.md`、`scripts/validate_contracts.py`、`scripts/verify_*_live.py` |
| Portable runtime images／deployment smoke | `scripts/build_runtime_images.ps1`、`scripts/build_runtime_images.sh`、`scripts/smoke_test_deployment.py` |

## 10. 驗證與完成條件

每個變更至少驗證：

- Acceptance Criteria 的正常、低信心、拒絕、撤回、失敗與重試路徑。
- Cross-elder／Cross-tenant／Expired assignment／Revoked share 的 Negative Test。
- 不符合 Spec 18 final gate 的 Memory（含 unverified Speaker、MEDIUM unconfirmed／stale、HIGH、失效
  Consent、expired／inactive／deleted／cross-scope）、Unreviewed Event 與 Draft Report 無法進入正式讀取路徑。
- Assisted Elder Session 的憑證分離（`ks1_`／`ep1_`／`es1_` 不可互換）、pairing token 單次使用、
  replay、過期、重新發放、cross-tenant，以及 acknowledgement 撤回後既有對話確實被取消。
- Agent Tool Allowlist、Schema、Max-step、Timeout、Fallback 與 Core reauthorization。
- Outbox、Consumer Idempotency、DLQ、Projection Lag 與 Rebuild 行為。
- Delete／Revoke 後資料不會被 Retry、Replay 或 Restore 復活。
- Log、Metric、Trace 與 Error Response 不含 Restricted Data。
- 所有測試資料均為 Synthetic／De-identified。

不要虛構測試結果。

`services/core-api`：

```powershell
cd services/core-api
uv sync --extra test --extra dev
uv run pytest tests/unit          # 不需資料庫
uv run pytest tests/integration   # 只可使用獨立、可丟棄的 TEST_DATABASE_URL
uv run ruff check .
uv run ruff format --check .
```

`services/agent-runtime/tests/conftest.py` 會在 test module 匯入 app 前強制
`APP_ENV=test`、`MODEL_PROVIDER=mock`。不得讓 developer `.env` 的真實 provider／secret 進入
一般測試；完整 suite 必須維持不需網路。

`services/agent-runtime`（不需資料庫、AWS 憑證或網路）：

```powershell
cd services/agent-runtime
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`services/speech-gateway`（contract boundary test 不需資料庫、AWS 憑證或網路）：

```powershell
cd services/speech-gateway
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

本機直接啟動 Speech Gateway 時必須使用
`uv run uvicorn --app-dir src speech_gateway.app:app --reload --port 8002`。該元件在
`pyproject.toml` 設定 `tool.uv.package = false`，不能假設 `speech_gateway` 已安裝成可直接匯入的套件。

`services/rag-ingestion`（本機測試不需真實 AWS）：

```powershell
cd services/rag-ingestion
uv sync --extra test --extra dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

四個 Python component 各自維護 `pyproject.toml` 與 `uv.lock`，不共用虛擬環境。

Frontend：

```powershell
npm run test --workspace @elderly-care/frontend
npm run typecheck --workspace @elderly-care/frontend
npm run build --workspace @elderly-care/frontend
npm run lint
```

整合測試會對 `TEST_DATABASE_URL` 指向的資料庫執行 `alembic upgrade head`，
預設是 `kinsun_test`，不要指向 `kinsun`。測試資料全部由 fixture 產生，
均為 Synthetic，不得改用任何真實長者資料。

尚未建立的項目（不要描述成已完成）：Python Type Check（mypy／pyright）、自動化 browser E2E、
外部部署的跨服務 E2E。Frontend TypeScript typecheck、靜態 Contract validator 與兩支 live contract
verifier 已存在，但不能取代上述 E2E。Repository 目前沒有 production IaC；舊 CDK 的
typecheck／test／synth 已隨 ADR 0019 退役。

CI Quality Gate 已於 2026-08-26 啟用（§1 的 `gate1.yml`），它涵蓋四個 Python 服務的 lint／測試、
Core integration、contract 三支驗證、五輪 synthetic Core-to-Agent 證據與完整 Frontend build。
但它跑的仍是 synthetic in-process 驗證，**不等於外部部署的跨服務 E2E**，也不含 browser E2E、
Python type check 或 production IaC verification。

Contract 驗證分三支：`scripts/validate_contracts.py` 驗 schema 與範例的自我一致性
（會掃 `contracts/openapi/` 底下所有文件）；`scripts/verify_contract_live.py` 對執行中的
core-api 驗證；`scripts/verify_agent_contract_live.py` 對執行中的 agent-runtime 驗證
（不需資料庫、憑證或網路）。新增 endpoint 時要同步在對應那支加檢查，否則它永遠只驗舊的。

下列 2026-08-13 至 2026-09-01 快照中的 Infra 結果，是 ADR 0019 退役前的歷史驗證紀錄，
不表示目前仍有 CDK workspace 或應重跑該命令。

2026-08-13 provider-neutral text adapter 完成後的本機校準結果：Core unit `755 passed`、
Agent Runtime `296 passed`、Frontend `135 passed`、Infra `7 passed`；Core／Agent Runtime Ruff lint、
Frontend ESLint／typecheck／production build、Infra typecheck／兩個
synth、靜態 Contract 與 Core live verifier（68 operations）通過。較早且未受本次身份變更影響的
RAG ingestion `138 passed`、Speech Gateway `22 passed` 未重跑。沒有獨立
`TEST_DATABASE_URL`，所以未對遠端 Supabase 執行破壞性的 integration rebuild；只在確認
`actor.cognito_sub` 非空筆數為 0 後套用 fail-closed migration 至 `f2c6d8a1e490`。完整 Core Ruff
format 仍會指出兩個本次未修改的既有檔案；本次修改檔案的 format check 已通過。

2026-08-17 Kinsun Email＋Password contract closure 的本機校準結果：Core unit `808 passed`、Frontend
`220 passed`；Frontend typecheck／production build、靜態 Contract 與 Core live verifier（72 operations）
通過。完整 Frontend ESLint 仍有一個本次未修改的既有 unused argument；完整 Core Ruff 仍有兩個本次未
修改的既有問題。沒有獨立 `TEST_DATABASE_URL`，未執行破壞性的 integration rebuild；本機 Docker
設定檔因執行環境權限無法讀取，`docker compose config --quiet` 本次未驗證。

2026-08-27 runtime policy v003 併入 `main`（`a2b2b96`）後的本機校準結果：Core unit `913 passed`、
Agent Runtime `406 passed`、RAG ingestion `311 passed`、Frontend `224 passed`（35 files）；Frontend
ESLint 與 typecheck 通過。Speech Gateway、Infra、Frontend production build、兩支 live contract
verifier 與靜態 contract validator 本次未重跑。沒有獨立 `TEST_DATABASE_URL`，未執行 Core
integration 或破壞性 rebuild；v003 runtime policy 只有離線 policy／citation Golden cases 與單筆長者
live smoke，完整 live relevance／ranking Golden Query 仍為 `NOT_EXECUTED`。

2026-08-29 將 `origin/main` 合併回本機 `main`（合併後 `9f5bbe6`）後的本機校準結果：Core unit
`916 passed`、Agent Runtime `407 passed`、RAG ingestion `320 passed`、Speech Gateway `81 passed`、
Frontend `230 passed`（37 files）。Agent Runtime／Speech Gateway／RAG ingestion 的 `ruff check` 與
`ruff format --check` 全數通過；Core `ruff check` 通過，但完整 `ruff format --check` 仍指出 5 個
**既有**檔案（`app/core/config.py`、`app/services/kinsun_email_auth_service.py`、
`scripts/redrive_legacy_family_invitation_events.py`、`tests/integration/test_migrations.py`、
`tests/unit/test_memory_candidate_metadata.py`）——這 5 個在 `ba7569b..9f5bbe6` 之間完全未被修改，
與本次合併無關，且 CI 不對 core-api 跑 format check。Frontend typecheck、ESLint 與 production
build 通過，靜態 `validate_contracts.py` 全數通過。本次**未執行**：Core integration（仍無獨立
`TEST_DATABASE_URL`）、兩支 live contract verifier、Infra typecheck／test／synth，以及
`scripts/verify_gate1_cross_service.py` 的五輪 synthetic 證據——後三者會在 push 觸發 `gate1.yml`
時於 CI 執行，屆時以 CI 結果為準。

2026-09-01 對 `25f8d77` 的本機校準結果。同批另修掉兩個擋 CI 的 lint 失敗（見 §1）：
core-api `ruff check --fix` 調整 `app/main.py`、`app/models/__init__.py` 的 import 順序，
agent-runtime `ruff format` 重排 `context/manifest.py`、`contracts/models.py`；四個都只是
排序／換行，沒有語意變更。表中結果為修正後重跑：

| 項目 | 結果 |
| --- | --- |
| Core API `pytest tests/unit` | `953 passed` |
| Core API `ruff check` | 通過（修正前有 2 個 `I001`） |
| Core API `ruff format --check` | FAILED——12 檔（5 個 08-29 就有的既有檔案 ＋ 7 個 `9f5bbe6..25f8d77` 之間新增／修改的檔案）。**CI 不跑此項**，本次刻意不整批重排，以免混入與需求無關的 diff |
| Agent Runtime `pytest` | `426 passed` |
| Agent Runtime `ruff check` | 通過 |
| Agent Runtime `ruff format --check` | 通過（修正前有 2 檔未過；此項在 CI 內） |
| RAG Ingestion | `320 passed`；`ruff check`＋`format` 通過 |
| Speech Gateway | `83 passed`；`ruff check`＋`format` 通過 |
| Frontend | typecheck 通過、`277 passed`（44 files）、ESLint 乾淨、production build 通過 |
| Infra | typecheck 通過、`7 passed`、`synth` 與 `synth:application` 皆成功 |
| `scripts/validate_contracts.py` | all contract checks passed |
| `scripts/verify_contract_live.py` | all live contract checks passed |
| `scripts/verify_agent_contract_live.py` | all live contract checks passed |

本次**未執行**：Core `tests/integration`（仍無獨立 `TEST_DATABASE_URL`）、
`scripts/verify_gate1_cross_service.py` 五輪 synthetic 證據、`.qa/` 需要真實 Supabase 的
smoke、live RAG relevance／ranking Golden Query、Playwright 視覺 QA。
Frontend ESLint 在此次為完全乾淨，先前紀錄的那個既有 unused argument 已不存在。
這個快照同樣不可取代當次驗證。

每次變更至少執行：

```powershell
git diff --check
git status --short
```

動到 Database Schema 時，先對 Supabase 做唯讀 revision 檢查並人工審查 migration，再執行 additive
upgrade；不得對 Supabase 執行 downgrade、reset 或空庫重建：

```powershell
cd services/core-api
uv run alembic current
uv run alembic heads
uv run alembic upgrade head
```

文件 13 §六.6 的空 DB 重建只可在另行提供的 disposable `TEST_DATABASE_URL` 執行；沒有獨立測試
資料庫時標記未驗證，不得拿 Supabase development database 代替。

並在交付說明中清楚列出已驗證、未驗證與受環境限制的項目。

## 11. 仍待 ADR／Owner 決策

- Production hosting provider、Region、Account／Environment、IaC 工具與成本上限；歷史 AWS profile
  曾固定 `us-west-2`，但已退役且不構成未來 provider 決策。
- 若未來重新選用 AWS，service 規模、database、network 與費用都必須在新帳號重新設計、實測；
  舊 template 或歷史紀錄不能當成現在的部署基準。
- Bedrock Model／Inference Profile 與 Fallback。
- Neptune、OpenSearch、LINE、Email、Custom ASR／TTS 採真實服務或 Demo Adapter。
- Production API／Event／Client 支援期限。
- 正式 Retention、Export、Legal Hold 與 Offboarding 政策。
- 統一的 Voice／Agent／TTS Performance Gate。

不要用暫時實作偷偷取代這些決策；暫時方案必須標示 Owner、Expiry、Fallback 與移除條件。
