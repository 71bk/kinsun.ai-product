# Repository Code Review Fix Plan

> 來源：repository-wide code review（commit `be25802`）
>
> 本文件追蹤 review findings、修正進度與驗證結果。

## 整體狀態

- Critical：目前未確認有 Critical issue。
- High：需要在 production rollout 前處理。
- Medium：需要排入近期 hardening / reliability sprint。
- Low：需要在 CI、文件或維護性工作中補齊。
- 2026-09-03 GitHub Actions Gate1 已在 PostgreSQL 16 + pgvector service 上完整通過 Core unit／integration suite；H-01 另以 development Demo verifier 完成真實 concurrent transaction 驗證，H-02 已完成 runtime-role deny matrix，H-03 已完成 cross-replica 與 concurrent nonce claim 驗證。
- Frontend typecheck 與 lint 已恢復綠燈。

## 修正順序

### P0 — Production blocker / security control

- [x] H-01 修正 idempotency 首次併發 race condition。
- [x] H-02 收窄 Core runtime database role 權限。
- [x] H-03 將 service identity replay protection 移至 shared durable store。
- [ ] H-04 完成 Speech Gateway 的 deployment 與 frontend endpoint wiring。
- [x] H-05 為 Speech TTS 加入認證、quota、rate limit 與 concurrency limit。
- [x] H-06 加入 production fail-closed configuration，禁止 mock Agent / disabled RAG。
- [x] H-07 修正 RAG policy overlay 的 live governance validation。
- [ ] H-08 若 deletion compliance 已在 production scope，完成所有外部 storage deletion adapter。

### P1 — Reliability / privacy / tenant isolation

- [x] M-01 完成 idempotency TTL、scope 與 replay response redesign。
- [ ] M-02 BFF/Core URL 在非 loopback production environment 強制 HTTPS。
- [ ] M-03 OpenSearch 強制 HTTPS 並加入 timeout/concurrency control。
- [ ] M-04 修正 Agent latency/tool budget 沒有實際 enforcement 的問題。
- [ ] M-05 降低 preferred address 造成 prompt injection 的風險。
- [x] M-06 修正 audit request context 注入。
- [x] M-07 清理 exception、traceback 與 database URL logging。
- [ ] M-08 加入 RLS 或等價的 database-level tenant isolation。
- [ ] M-09 為 email/password auth 加入 distributed abuse limiting。
- [ ] M-10 為 Care Action provenance 保存 immutable event version/hash。
- [ ] M-11 建立 outbox publisher、recovery、DLQ 與 duplicate-safe consumer。

### P2 — API / frontend / tooling / documentation

- [ ] L-01 實作 Care Action 與 source event pagination。
- [ ] L-02 為 frontend API response 加入 runtime schema validation。
- [ ] L-03 嚴格驗證 correlation ID 為受限格式的 UUID v4。
- [x] L-04 修復 frontend typecheck。
- [x] L-05 修復 frontend lint。
- [ ] L-06 將 Core formatting 納入 CI，並統一 contract validator 的依賴環境。
- [x] L-07 更新 migration head，並以 ADR 0019 退役過期的 AWS staging profile。

---

## P0 詳細項目

### H-01 — Idempotency 首次併發 race condition

- Severity：High
- 位置：`services/core-api/app/repositories/idempotency_repo.py:50-102`，`begin()`
- 問題：不存在的 idempotency row 不會被 `SELECT ... FOR UPDATE` 鎖住。兩個 concurrent transaction 都可能查到不存在，第二個 insert 會因 primary-key conflict 失敗。
- 影響：同一個 write request 在 retry 或高併發下可能回傳 500，而不是 deterministic replay。
- 修正：使用 database-native `INSERT ... ON CONFLICT`、advisory lock，或捕捉唯一鍵衝突後重新讀取既有紀錄。
- 驗證：以 PostgreSQL 同時送出兩個相同 `Idempotency-Key` 的 POST，確認只執行一次且兩邊收到一致 response。
- 應新增測試：是，concurrent integration test。
- 修正結果：使用 PostgreSQL `INSERT ... ON CONFLICT DO NOTHING` 原子 claim；loser transaction 會等待 winner commit 後讀取 immutable snapshot。development PostgreSQL verifier 證明 `execution_count=1`、第二個 request replay 且 snapshot 一致。

### H-02 — Core runtime database role 權限過寬

- Severity：High
- 位置：`services/core-api/app/database_runtime_principal.py:158-178,199-222`
- 問題：runtime role 對 `eldercare_ai` schema 所有 table 擁有 `SELECT, INSERT, UPDATE, DELETE`，也包含 sequences。
- 影響：application compromise、SQL injection 或錯誤 query 可直接修改 audit、consent、security、outbox、idempotency 等敏感資料。
- 修正：改用 table allowlist、分離 read/write roles、stored procedures；audit/consent/security tables 不應由一般 application role 任意更新。
- 驗證：建立 database permission deny matrix，確認 application role 不能直接修改受保護表。
- 應新增測試：是，database integration test。
- 修正結果：runtime role 改用明確 table allowlist 與 column-scoped lifecycle UPDATE；未分類與未來新增的 table/sequence 預設無 DML，audit、policy、consent、outbox、idempotency、identity 與 credential immutable 欄位均有 deny matrix。以一次性 PostgreSQL 16 + pgvector 容器完成全部 migrations 並驗證通過；同時修正 psycopg 對 `information_schema.sql_identifier[]` 的 domain-array 解碼差異，改採逐欄分組以維持跨環境一致性。

### H-03 — Service identity replay protection 只存在 process memory

- Severity：High
- 位置：`services/core-api/app/adapters/service_identity.py:113-140,201-204`；`services/agent-runtime/src/agent_runtime/security/service_identity.py:102-130,185-188`
- 問題：已使用 nonce 儲存在單一 process 的 dictionary；不同 replica 互相看不到 replay state。
- 影響：相同 signed request 可在不同 replica 被接受，導致重複 Agent run、proposal 或 provider cost。
- 修正：使用現有 PostgreSQL 的 unique constraint＋`INSERT ... ON CONFLICT DO NOTHING` 建立 atomic
  nonce claim；production 啟動時拒絕 process-local replay mode。專案目前不使用 Redis 或 AWS 服務，
  不為單一 nonce use case 新增基礎設施。
- 驗證：將同一 signed request 送到兩個 replica，第二個 replica 必須拒絕。
- 應新增測試：是，multi-replica replay integration test。
- 修正結果：新增 migration `e2f4a6c8b013`，在 `eldercare_ai` 之外建立 `service_identity.credential_nonce`
  （PK `(audience, credential_id)`、expiry index、`REVOKE ALL ... FROM PUBLIC`）。replay 判定改由
  `INSERT ... ON CONFLICT DO NOTHING` 在**獨立短交易**完成，即使被認證的請求之後 rollback，claim 仍然成立；
  同一交易先做上限 200 筆的 expiry purge，只清已過期列。兩側 verifier 的 `replay_store` 改為**必填**，
  忘記注入會直接 `TypeError`，不再靜默退回 process-local。Core 一律使用 `DatabaseReplayStore`；
  Agent Runtime 以 `SERVICE_IDENTITY_REPLAY_DATABASE_URL` 選用 `PostgresReplayStore`，
  `APP_ENV=production` 缺少該設定時**啟動即失敗**。claim 無法判定（driver 失敗）時 fail closed，
  且錯誤訊息只帶 exception type。Runtime 只取得 `service_identity` schema 的 USAGE 與該表的
  SELECT/INSERT/DELETE，`UPDATE`／`TRUNCATE`／`REFERENCES`／`TRIGGER` 在 deny matrix 內，
  對 `eldercare_ai` 沒有任何新 grant。development database verifier
  （`scripts/verify_service_credential_replay.py`）回報
  `sequential_replay_rejected=true`、`concurrent_accepted=1`、`concurrent_rejected=1`。

### H-04 — Speech Gateway 尚無 production deployment 與 endpoint wiring

- Severity：High
- 位置：`packages/frontend/src/lib/voice/speech-gateway-client.ts:48-50`；`packages/frontend/src/lib/voice/canonical-voice-turn.ts:65-69`；ADR 0019
- 問題：frontend voice flow 依賴 `NEXT_PUBLIC_SPEECH_GATEWAY_URL`，但 production hosting provider／IaC
  尚未定案，也沒有已部署的 Speech Gateway endpoint。舊 AWS CDK profile 已退役，不能再當作修正位置。
- 影響：部署後啟用 voice surface，ASR 會因 gateway URL 缺失而失敗；TTS 只會 fallback 為文字。
- 修正：先以 ADR 選定 production hosting／network topology，再部署 Speech Gateway 並注入 endpoint，
  或統一經由 authenticated BFF proxy。
- 驗證：部署環境執行登入、錄音、transcription、TTS 的 browser smoke test。
- 應新增測試：是，deployment smoke/E2E test。

### H-05 — Speech TTS endpoint 沒有認證與 abuse controls

- Severity：High
- 位置：`services/speech-gateway/src/speech_gateway/app.py:262-310`
- 問題：`POST /api/v1/speech/syntheses` 沒有 Core voice ticket、service identity、user auth 或 per-user rate limit。
- 影響：公開或可達的 gateway 可被任意呼叫，消耗 TTS provider quota、造成費用或 DoS。
- 修正：透過 BFF/Core capability flow 呼叫；驗證 user/session ticket；加入 IP/user/tenant quota、字數限制、concurrency limit 與 `Retry-After`。
- 驗證：未認證請求應拒絕；超過 quota 應回傳 429；provider failure 不得造成資源洩漏。
- 應新增測試：是。
- 修正結果：Core companion turn 只在 completed Agent run 與 live actor／tenant／session binding
  一致時，為**去除引用區塊後的 exact UTF-8 reply**簽發 15–120 秒的一次性 opaque HMAC
  capability；capability 綁定 session、Agent run、actor、tenant、文字 SHA-256、字數、語言與
  completed time，且三個 synthesis response 欄位在 DTO 與 JSON Schema 都是 all-or-none。
  Speech Gateway 的 TTS route 現在必須收到 bearer capability，先以既有 request-bound Speech
  service identity 向 Core 兌換，再呼叫 provider；production 若未啟用該 service identity 會在
  startup fail closed。migration `f3a5b7c9d024` 在 `service_identity` schema 新增 immutable
  `speech_synthesis_claim`：以 advisory transaction locks 將 client-IP HMAC pseudonym／actor／tenant
  三個 scope 的 request 與 character window quota 序列化，並以 capability digest PK 保證跨 replica
  single use。超限回 429、`retryable=true` 與 bounded `Retry-After`。Gateway 另有 1–64 的 process
  concurrency limit，超量立即回 429，所有 Core／provider exception path 都在 `finally` 釋放 slot。
  Frontend 不再自行重建 TTS 文字，只傳 Core 回傳的 exact text、session／run binding 與 bearer
  capability；reply language 不一致或 capability 未簽發時維持 text-only。新增 Core codec／DTO／quota
  unit tests、PostgreSQL single-use integration test、Gateway auth／quota／concurrency tests、frontend
  binding tests、OpenAPI／JSON Schema 與 valid／invalid examples。2026-09-03 本機驗證 Core unit
  `1046 passed`、Speech Gateway `91 passed`、Agent Runtime `488 passed`、frontend `284 passed`，以及
  Ruff、frontend typecheck／lint／build、contract validator／live drift verifier 全數通過；PostgreSQL
  integration 由含 PostgreSQL 16 + pgvector disposable service 的 GitHub Actions 執行。

### H-06 — Production 可使用 mock Agent 或 disabled RAG

- Severity：Medium/High
- 位置：`services/agent-runtime/src/agent_runtime/settings.py:14-32`；`services/agent-runtime/src/agent_runtime/app.py:28-32,77-82,183-207`
- 問題：`APP_ENV=production` 時沒有拒絕 `MODEL_PROVIDER=mock` 或 `RAG_MODE=disabled`。
- 影響：錯誤配置可成功啟動，但實際產生 synthetic response 或完全沒有 governed retrieval。
- 修正：加入 production configuration validator，強制 approved model/provider/RAG mode；staging 與 production 使用不同設定模板。
- 驗證：production + mock/disabled config 必須在 startup fail closed。
- 應新增測試：是，configuration matrix tests。
- 修正結果：`app.py` 新增 `validate_production_configuration()`，是 `create_app()` 的第一件事，只在
  `APP_ENV=production` 生效，`local`／`test`／`staging` 行為完全不變。一次收集所有違規再拋一個
  `ValueError`，訊息只帶設定名稱，不回填設定值、endpoint 或 secret。approved provider 為
  `bedrock`／`gemini`／`openai-compatible`，normalization 與 `build_provider()` 完全一致；
  `RAG_ALLOW_NEEDS_REVIEW_CITATIONS`、`RAG_STAGING_ALLOW_ALL_AUDIENCES` 在 production 必須為 false。
  **`PRODUCTION_APPROVED_RAG_MODES` 目前刻意是空集合**：`disabled` 等於沒有受治理檢索，`staging`
  綁的是 `production_approved=false` 的 release，因此在 Owner 核准 production retrieval release 之前，
  `APP_ENV=production` 一律啟動失敗。這是 §11 待決事項的 fail-closed 表述，不是暫時 workaround；
  解除條件是 Owner 核准 release 後把該 mode 加進該常數。另新增測試釘住 Dockerfile 的
  `APP_ENV=production`＋`MODEL_PROVIDER=mock`＋`RAG_MODE=disabled` 預設組合會被拒絕——image 因此
  無法以出廠預設啟動成 production runtime。Agent Runtime `pytest` 由 473 個測試通過（新增 27 個），
  `ruff check` 與 `ruff format --check` 皆通過。

### H-07 — RAG policy overlay 可能服務已撤回資料

- Severity：Medium/High
- 位置：`services/agent-runtime/src/agent_runtime/rag/filters.py:22-29`；`retriever.py:240-307`；`postgres_backend.py:92-102`
- 問題：policy overlay 主要以 `chunk_id` 過濾，沒有完整重新檢查 live `current_status`、`stop_normal_rag`、`retrieval_eligible`、review/production flags。
- 影響：stale projection 或撤回後的 chunk 可能仍被服務。
- 修正：overlay 也套用完整 governance predicate，並在 response 階段以 authoritative metadata fail closed。
- 驗證：將 chunk 改為 withdrawn/expired/review 狀態後，overlay 必須拒絕該 chunk。
- 應新增測試：是。
- 修正結果：OpenSearch 與 PostgreSQL 的 policy-overlay 搜尋路徑現在都必須通過 live
  `current_status=current`、`stop_normal_rag=false`、`retrieval_eligible=true`、空的
  `retrieval_block_reasons` 與 review／production gate；immutable policy 只可補足固定候選的
  risk／audience／purpose／assessment／citation metadata，不能覆蓋撤回狀態。Retriever 在建立
  response 前會以搜尋結果的 authoritative live metadata 再做一次相同的 fail-closed 檢查。
  新增 withdrawn、expired、stop、retrieval-disabled、block reason 與 review／production mismatch
  測試；Agent Runtime 全套 `485 passed`，Ruff check／format 皆通過。

### H-08 — External deletion 尚未完成

- Severity：High（若已屬 production compliance scope）
- 位置：`services/core-api/app/services/deletion_service.py:187-250,283-290`
- 問題：S3、Neptune、OpenSearch、Cache 等 targets 尚未有完整 adapter；未配置時會產生 `TARGET_NOT_CONFIGURED` / `PARTIAL_FAILED`。
- 影響：consent revocation 後，外部儲存仍可能保留個人資料。
- 修正：完成每個 system 的 durable worker、retry、verification、DLQ 與 completion criteria。
- 驗證：建立跨 storage system deletion job，確認所有 target 都刪除並被驗證。
- 應新增測試：是，end-to-end deletion verification test。

## P1 詳細項目

### M-01 — Idempotency TTL、scope 與 replay semantics 不完整

- Severity：Medium
- 位置：`services/core-api/app/repositories/idempotency_repo.py:56-123`；`services/core-api/app/models/idempotency.py:16-36`
- 問題：`expires_at` 未被檢查；key 只有 global primary key；只保存 response hash，沒有原始 response snapshot。
- 影響：key 永久阻擋、跨 tenant/actor 碰撞，以及 replay-after-delete/update 回傳不同結果。
- 修正：使用 tenant/actor scoped unique key；實作 expiry cleanup；保存 status/body/headers 或 immutable response snapshot。
- 驗證：測試跨 tenant collision、expiry retry、resource mutation/delete 後 replay。
- 應新增測試：是。
- 修正結果：v2 physical key 由 tenant／actor／client key 雜湊產生，保留同 scope legacy-key fallback；到期 row 可原子 reclaim，並提供 indexed expiry purge；完成時保存有期限的 JSONB snapshot 與 integrity hash。一般 write API 直接 replay snapshot，單次秘密 invitation／voice ticket 與 companion turn 維持 fail-closed 不回放明文。

### M-02 — BFF/Core URL 允許 HTTP

- Severity：Medium/High
- 位置：`packages/frontend/src/lib/server/core-proxy.ts:13-25,48-55,98-105`；`assisted-elder-session-core.ts:3-35`；`core-app-session.ts:6-39`
- 問題：設定可使用遠端 `http:`，而 BFF 會將 session cookie 轉為 bearer token 傳送。
- 影響：錯誤 production configuration 會以明文傳輸 session credential。
- 修正：非 loopback environment 強制 HTTPS；startup/request 時拒絕不安全 URL。
- 驗證：遠端 HTTP URL 必須被拒絕；localhost development exception 應有明確測試。
- 應新增測試：是。

### M-03 — OpenSearch transport 安全與 timeout 不足

- Severity：Medium
- 位置：`services/agent-runtime/src/agent_runtime/rag/client.py:91-111,134-143,204-218`
- 問題：允許遠端 HTTP；blocking search 透過 `asyncio.to_thread()` 執行，timeout 可達 60 秒，沒有 bounded semaphore 或 end-to-end cancellation。
- 影響：RAG credential/content 可能明文傳輸；慢速 OpenSearch 可耗盡 thread pool，並超過 voice/Core latency budget。
- 修正：遠端強制 HTTPS；加入 certificate validation、semaphore、較短一致的 deadline 與 cancellation。
- 驗證：模擬 60 秒延遲與高併發，確認 request 可取消且不耗盡 worker。
- 應新增測試：是，security、timeout、load tests。

### M-04 — Agent latency/tool budgets 沒有 enforcement

- Severity：Medium
- 位置：`services/agent-runtime/src/agent_runtime/contracts/models.py:256-303`；`orchestration/orchestrator.py:42-85`
- 問題：API 接收 `latency_budget_ms`、`max_tool_rounds`、`max_total_tools`，但流程沒有完整執行這些限制。
- 影響：呼叫者得到錯誤的 bounded-execution 保證，可能造成長時間或過量 provider/tool work。
- 修正：將 deadline 傳遞至 provider/retrieval，實作 tool counters；或移除尚未支援的欄位。
- 驗證：測試 timeout、tool round、tool count 邊界值。
- 應新增測試：是。

### M-05 — Preferred address 可形成 prompt injection

- Severity：Medium
- 位置：`services/agent-runtime/src/agent_runtime/models/prompting.py:66-70`
- 問題：`preferred_address` normalization 後仍直接插入 system prompt。
- 影響：使用者可輸入 instruction-like text，干擾 system-level policy。
- 修正：將所有 user-controlled text 放入 delimited data/user section；限制長度與字元。
- 驗證：輸入 instruction-like preferred address，確認不會改變 system policy 或洩漏資料。
- 應新增測試：是，adversarial prompt tests。

### M-06 — Audit request context 沒有被設定

- Severity：Medium
- 位置：`services/core-api/app/middleware/logging.py:33-37,89-100`；`services/core-api/app/middleware/auth.py:179-188`
- 問題：logging middleware 讀取 `request.state.actor_id/tenant_id` 與 ContextVar，但 auth flow 沒有找到對應 setter。
- 影響：authenticated 4xx/5xx logs 可能缺少 actor/tenant，降低 audit 與 incident investigation 能力。
- 修正：auth 成功後設定 request state/ContextVar，request 結束時 reset。
- 驗證：authenticated request 觸發錯誤時，structured log 必須包含正確 actor、tenant、correlation ID。
- 應新增測試：是。
- 修正結果：`app/middleware/logging.py` 新增 `bind_request_actor_context()`，由
  `app/middleware/auth.py` 的 `get_actor_context()` 在 `authenticate()` 成功後立即呼叫——那是每條
  受保護 route 唯一都會經過、且手上已有可信身分的位置。只寫入解析後的 `ActorContext`，不接受任何
  client 傳入值；認證失敗刻意不綁定，因為沒有可信身分可記錄。同時寫 `request.state`（主要載體，
  存在 ASGI scope 上，可跨 `BaseHTTPMiddleware` 的 task 邊界）與兩個 ContextVar（ambient fallback）。
  `RequestLoggerMiddleware.dispatch` 每個請求開始時重設、`finally` 中 `reset()`，避免跨請求殘留。
  無帳號長者（`es1_`）與 speech service identity 沒有 Actor，維持不綁定。

### M-07 — Exception、traceback 與 database URL logging 可能洩漏敏感資料

- Severity：Medium/High
- 位置：`services/core-api/app/main.py:76-110`；`app/db/engine.py:95-98`；`app/api/error_handlers.py:295-301,320-333,365-373`；`app/core/config.py:41-42,68,493-509`
- 問題：多處直接記錄 `str(exc)` 或 traceback；`database_url` 未被列入 sensitive field。
- 影響：可能將 DB credentials、host、SQL 或受保護資料寫入 logs。
- 修正：只記錄 exception type、internal code、correlation ID；redact DSN authority/password；traceback 只進受控 sink。
- 驗證：觸發 DB/config exception，確認 logs 不包含 password、DSN 或 SQL parameters。
- 應新增測試：是；現有 `tests/unit/test_config.py:445-449` 的安全預期應改寫。
- 修正結果：新增 `app/core/log_safety.py`，集中兩條規則。`redact_dsn()` 只保留 scheme
  （`postgresql+asyncpg://***`）——scheme 正是 `validate_database_url` 會拒絕的部分，其餘
  authority 與 database name **整段丟棄而非解析**，避免畸形 DSN 從解析失敗的路徑漏出。traceback
  改送 `app.diagnostics`：`propagate=False` ＋ `NullHandler`，預設不寫任何地方，要由 operator 自行
  掛上受治理的 handler；一般 log 只留 exception type、內部 code 與 correlation ID。
  `config.py` 新增 `_DSN_FIELD_NAMES`（`database_url`、`test_database_url`）依形狀而非名稱子字串
  redact——原本的名稱比對（`password`／`secret`／`key`／`token`）在結構上就看不到藏在**值**裡面的
  credential。`main.py` 的 settings 失敗只輸出欄位名稱，連 sink 都不送 traceback，因為該例外的
  訊息本身就是被拒絕的 DSN。`db/engine.py` 兩處 `exc_info=True` 與 `error_handlers.py` 的
  `traceback.format_exc()`／`str(exc)`／`str(handler_exc)` 全部改為 code ＋ exception type。
  `hide_parameters=True` 未更動，`DomainException → error_handlers → ErrorEnvelope` 與所有回應
  形狀不變（三支 contract 驗證重跑通過）。`test_config.py` 原本斷言 `database_url` 必須原樣回傳，
  等於把洩漏釘死成預期行為；已拆成四個測試：保留「真正非敏感欄位仍可讀」的原始意圖，並新增
  scheme-only、`repr`／`str` 皆不含帳密主機、以及未設定的 `test_database_url` 維持空字串
  （不得變成 `***` 而讓人誤以為有值）。Core unit 由 990 增至 1028 passed。

### M-08 — 缺少 database-level tenant isolation

- Severity：Medium
- 位置：Core migrations/schema setup；目前未找到 `ENABLE ROW LEVEL SECURITY`、`FORCE ROW LEVEL SECURITY` 或 `CREATE POLICY`
- 問題：tenant isolation 主要依賴 application query predicates。
- 影響：新增漏加 tenant filter 的 query 即可能造成 cross-tenant data exposure。
- 修正：對敏感 tenant tables 啟用 RLS/forced RLS，並配合 request-bound tenant context 與最小權限 roles。
- 驗證：以同一 database role 執行 cross-tenant read/write deny matrix。
- 應新增測試：是，database integration tests。

### M-09 — Email/password authentication 缺少 distributed abuse limiting

- Severity：Medium
- 位置：`services/core-api/app/api/kinsun_email_auth.py:97-215`；`services/core-api/app/services/password_auth_service.py:118-139`
- 問題：有 actor lockout/OTP attempt limit，但沒有 per-IP、per-subject、device、challenge 的 distributed limiter，也缺乏明確 challenge issuance cooldown。
- 影響：可大量發送 email、消耗 provider quota，或透過輪換 subject 繞過單一 actor lockout。
- 修正：加入 Redis/distributed limiter、IP/subject quota、email cooldown、generic 429 與 `Retry-After`。
- 驗證：測試相同 IP、相同 subject、多 actor、跨 replica 的限流行為。
- 應新增測試：是。

### M-10 — Care Action provenance 只保存可變 UUID reference

- Severity：Medium
- 位置：`services/core-api/app/services/care_action_service.py:133-156`；`services/core-api/app/models/care_action.py:42-46`
- 問題：`related_event_ids` 是 plain UUID array，沒有 FK、event version 或 hash snapshot。
- 影響：related event correction/deletion 後，無法重建 Care Action 當時引用的 evidence。
- 修正：保存 immutable event version/hash，或限制已被 action reference 的 event destructive mutation。
- 驗證：建立 action 後修改/刪除 event，確認 provenance 仍可驗證或操作被拒絕。
- 應新增測試：是。

### M-11 — Outbox 缺少 production publisher/recovery/DLQ

- Severity：Medium
- 位置：`services/core-api/app/events/relay.py:50-115`；`events/consumer.py:86-93`；`events/synthetic_projection.py:1-5,51-104`
- 問題：目前 relay/projection 偏向 synthetic/foundation implementation，沒有完整 queue adapter、DLQ、lease recovery 或 production consumer。
- 影響：event 可能只寫入 outbox 而未可靠送達，downstream failure 也沒有可操作的恢復流程。
- 修正：加入 worker lease、stale `PUBLISHING` recovery、at-least-once delivery、idempotent consumer、DLQ 與 runbook。
- 驗證：模擬 publish crash、downstream failure、duplicate delivery 與 worker restart。
- 應新增測試：是，failure/recovery integration tests。

## P2 詳細項目

### L-01 — Frontend 未實作 API pagination

- Severity：Medium
- 位置：`packages/frontend/src/lib/api/care-actions.ts:102-117`；`packages/frontend/src/components/care/CareActionPanel.tsx:127-150,326,352`
- 問題：Core 支援 cursor，但 frontend 固定 `limit=100` 且只載入一次；source events 也未完整處理 cursor。
- 影響：資料超過 100 筆後會被靜默截斷。
- 修正：加入 cursor pagination、load-more/infinite scroll、完整 `has_more` UI。
- 驗證：建立超過 100 筆 Care Actions/source events，確認全部可瀏覽。
- 應新增測試：是，component/API pagination tests。

### L-02 — Frontend API response 缺少 runtime validation

- Severity：Medium/Low
- 位置：`packages/frontend/src/lib/api/client.ts:39-67`
- 問題：`response.json()` 直接 cast，沒有 schema validation。
- 影響：API drift 或 malformed response 會在 component 層以 undefined state 或 late error 失敗。
- 修正：使用 Zod 或等價 schema guard，統一處理 malformed success/error envelope。
- 驗證：回傳缺欄位、錯誤型別、錯誤 envelope 時，client 應產生可預期錯誤。
- 應新增測試：是。

### L-03 — Correlation ID 沒有嚴格 UUID v4 validation

- Severity：Low/Medium
- 位置：`services/core-api/app/middleware/logging.py:65-68,105-106`；`services/agent-runtime/src/agent_runtime/middleware/correlation.py:42-50`
- 問題：任意非空 header 都可成為 correlation ID；規格要求 UUID v4。
- 影響：超長值、控制字元或偽造格式可能污染 logs 與 tracing。
- 修正：限制長度、只接受 UUID v4；無效值重新生成。
- 驗證：malformed、oversized、control-character headers。
- 應新增測試：是。

### L-04 — Frontend typecheck 失敗

- Severity：Medium
- 位置：`packages/frontend/src/components/ui/ConfirmationDialog.test.ts:15`
- 問題：`LocaleProvider` props 缺少必要的 `children`。
- 影響：CI typecheck gate 失敗。
- 修正：補上 `children` 或修正 test wrapper type。
- 驗證：`npm run typecheck --workspace @elderly-care/frontend` 通過。
- 應新增測試：否，修正既有測試型別即可。

### L-05 — Frontend lint 失敗

- Severity：Low
- 位置：`packages/frontend/src/components/care/CareActionPanel.tsx:4`
- 問題：`CalendarBlank` unused import。
- 影響：CI lint gate 失敗。
- 修正：移除 unused import 或實際使用。
- 驗證：frontend lint 通過。
- 應新增測試：否。

### L-06 — Core formatting 與 contract validator 依賴環境不一致

- Severity：Low
- 位置：Core repository-wide；`scripts/validate_contracts.py:20`
- 問題：Core `ruff format --check` 約 33 個檔案不通過；root contract validator 需要 `PyYAML`，但 Core venv 沒有，必須靠 CI 額外注入。
- 影響：本機與 CI 結果不一致，降低 review/reproduction 品質。
- 修正：將 PyYAML 加入明確 dev dependency，將 formatting 納入 CI，統一驗證命令。
- 驗證：在 clean environment 執行 lint、format、contract validation。
- 應新增測試：是，CI/tooling smoke test。

### L-07 — Migration head 文件過時與已失效 AWS staging metadata

- Severity：Low/Medium
- 位置：`AGENTS.md`；`CLAUDE.md`；ADR 0019
- 問題：文件仍指向舊 migration head `b8c2d4e5f607`；實際 head 已為 `d0e4f6a8b901`。舊 AWS
  staging `ExpiresAt` 也已過期，但該 deployment profile 並非現行環境。
- 影響：migration review 可能依據錯誤資訊；過期 IaC 會使讀者誤認 AWS 是現行部署路徑。
- 修正：文件更新為 29 個 revisions、head `d0e4f6a8b901`；依 ADR 0019 退役 AWS CDK workspace、
  deployment scripts 與 active runbook，而不是延長一個未使用環境的 expiry tag。
- 驗證：`alembic heads`、repository reference scan、root workspace lockfile consistency check。
- 應新增測試：可新增 CI validation，不需 runtime test。
- 修正結果：完成上述文件校準與 AWS CDK profile 退役；歷史 AWS spec／ADR／handover 保留但標記為
  非現行部署證據。

---

## Specification / deferred work

以下項目不是目前第一 slice 的單檔 bug，但若要宣稱 production-complete，仍需排程：

- [ ] Real login、browser、voice deployment E2E。
- [ ] Wave 2 R2 candidate Care Action。
- [ ] Agent-created Care Action、任意 assignee/transfer、通知流程。
- [ ] WebSocket speech event、AI Care Action、notification/email、Agent handoff、Graph projection contracts。
- [ ] Governed RAG embedding rebuild、approved release、rollback、evaluation evidence、production integration。
- [ ] External deletion verification、operational runbook 與 compliance evidence。
- [ ] `RequestLoggerMiddleware` 在 `call_next` 拋例外時不會輸出 `request_completed`：真正未處理的
  例外由位於 logger **之上**的 `ServerErrorMiddleware` 接住，因此該類 500 只剩
  `_unhandled_exception_handler` 帶 correlation ID 的紀錄。修正會改動 middleware 的錯誤語意，
  應獨立處理（M-07 期間發現，刻意未擴大範圍）。
- [ ] `lifespan()` 中 `DatabaseEngine(settings)` 的建構未包保護：若 `create_async_engine` 拋例外，
  DSN 仍可能出現在 uvicorn 自己的 stderr traceback。加保護會改動 startup 語意（同上）。

## 建議完成定義

每一個 P0/P1 項目完成時，至少應同時具備：

1. 實作修正。
2. 對應 unit test 或 integration/E2E test。
3. 失敗情境與 recovery path。
4. Logs/metrics/traces 可觀測性。
5. 更新 contracts/spec/ADR/runbook。
6. 在 disposable PostgreSQL 與 deployment-like environment 驗證。

## 已知基準測試結果

- Core unit tests：1028 passed。
- Agent tests：473 passed。
- RAG unit tests：200 passed。
- Speech tests：83 passed。
- Frontend tests：283 passed。
- Frontend production build：passed。
- Frontend typecheck：passed（L-04 已修正）。
- Frontend lint：passed（L-05 已修正）。
- Core Ruff lint：passed。
- Core Ruff format check：failed，對應 L-06。
- PostgreSQL integration tests：未執行，缺少 disposable `TEST_DATABASE_URL`。
