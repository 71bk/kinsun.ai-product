# AGENTS.md — core-api

本檔補充根目錄 [`AGENTS.md`](../../AGENTS.md)，只涵蓋 `services/core-api/`；根目錄規則一律適用，
衝突時以根目錄為準。改 API 或 schema 時另讀 [`contracts/AGENTS.md`](../../contracts/AGENTS.md)。

## 分層與回應

- Route 只處理 HTTP 邊界、呼叫 service 並包裝 envelope；service 協調 domain、policy、repository
  與 outbox，回傳 domain 型別（例如 frozen dataclass），不認識 HTTP。
- 對外回應一律 `SuccessEnvelope`／`ErrorEnvelope`（`app/core/envelopes.py`），不得自行拼頂層結構。
- 例外流程固定 `DomainException → app/api/error_handlers.py → ErrorEnvelope`；狀態碼對應只有一份
  `EXCEPTION_MAP`。service 層不組裝 HTTP 錯誤 payload。
- `error_handlers` 以 **exact exception type** 查表；新增子類要明確登記。`OptimisticConcurrencyError`
  必須對應 409／`VERSION_OR_IDEMPOTENCY_CONFLICT`，只登記父類 `ConflictError` 會讓真實並行失敗變 500。
- 非 `DomainException` 需特定狀態碼時在 `register_exception_handlers()` 註冊，否則落入 catch-all 500；
  已知：`NoAuthenticatorConfiguredError` 必須是 401（fail closed）。
- `AuthorizationDeniedError` 回 404（隱藏資源存在），不是 403。新 endpoint 補不依賴 DB 的
  route／error-handler 回歸，並同步 OpenAPI error response。
- Production 錯誤訊息經 `_sanitize_message()` 過濾；結構化資訊放 `code`／`reason_code`，不靠訊息文字。

### 跨層 mapping（不要自行猜）

| 邊界 | 外部／Runtime 值 | Core／DB 值 |
| --- | --- | --- |
| ORM 主鍵 | Python 一律 `model.id` | 實體欄位如 `actor_id`／`elder_id`，由 `__pk_name__` 對應 |
| Agent actor role | `elder`／`family`／`system`，其他可信角色映成 `staff` | `ELDER`／`FAMILY_MEMBER`／`SYSTEM_SERVICE` 等 |
| 語言 | `zh-TW`／`nan-TW`／`hak-TW`／`en-US` | `ZH_TW`／`NAN_TW`／`HAK_TW`／`EN_US`；`MIXED`、`UNKNOWN` 暫映 `zh-TW` |
| Agent result | `SUCCESS`／`BLOCKED`／`SAFE_FALLBACK`／`FAILED` | AgentRun 保存 `SUCCESS`／`BLOCKED`／`HUMAN_REVIEW`／`DEPENDENCY_FAILED` |
| Auth credential | 一般 endpoint 只收 `ks1_`；`ep1_`／`es1_` 只由 assisted-session 專屬 dependency 解析；`X-Kinsun-Service-Credential` 供服務間呼叫 | Session／Actor／Membership 每次由 live DB 重查；失敗不得 fallback |

Executable authority：`app/services/companion_service.py`、`app/middleware/auth.py` 與各 ORM model。
跨層改值時同步 contract、migration、adapter、前端 label 與測試。

## 資料庫、Alembic 與 ORM

- uv（ADR 0001）、FastAPI＋SQLAlchemy 2 async（ADR 0003）。Alembic 用同步 psycopg、應用層用 asyncpg；
  `DATABASE_URL` 只維護一份 asyncpg 形式，由 `alembic/env.py` 轉換。
- Domain schema 是 `eldercare_ai`；Alembic 另擁有 `rag_public` 與 `service_identity`，兩者沒有 ORM model，
  由 `database_runtime_principal.py` 的 `RUNTIME_SHARED_SCHEMA_PRIVILEGES` 逐表授權，不要放進
  `RUNTIME_TABLE_PRIVILEGES`（有 ORM 交叉檢查測試）。新表同步 runtime principal allowlist。
- Alembic 版本表在 `public.alembic_version`。手動 DB 檢查用 `app.database_url.to_psycopg_database_url`
  （含 asyncpg `ssl` → psycopg `sslmode`），錯誤只輸出類型／SQLSTATE，不印 DSN。
- v0.1 baseline 是凍結 SQL＋SHA-256（ADR 0002）；已套用 migration 不可變，改 schema 就新增 revision。
  Checksum 不符先查 CRLF：`.gitattributes` 須維持 `services/core-api/alembic/versions/sql/*.sql text eol=lf`，
  不得改凍結 SQL 或預期 checksum。`docs/project/smart_eldercare_schema_v0_1.sql` 與 baseline 逐位元相同，
  只是 ER 圖來源，不是 schema 權威。
- `alembic revision --autogenerate` 會把未映射表誤判為應刪除；產出一律人工檢查。
- 新功能沒有 ORM 不代表沒有表：先查 baseline `.sql`。`service_record` 已存在（JSONB content、
  `worker_actor_id`、DRAFT default）；只做 additive 擴充，legacy rows 不自動升為正式 v1。
- Domain enum 的每個值都必須存在於 baseline／migration（PG ENUM label 或 CHECK）；否則 INSERT 才爆。
- ORM 屬性統一 `id`，新增 model 必須宣告 `__pk_name__`。只有 `created_at` 的 append-only 表
  （如 `CareActionCandidateEventProvenance`）繼承 `Base` 明確映射，不繼承帶 `updated_at` 的 `BaseModel`；
  不為錯誤 ORM 改已套用 migration。
- Async flush 後 DTO 立即讀 server／on-update timestamp 時，用 `eager_defaults=True` 或明確 async refresh；
  `expire_on_commit=False` 不足以防 `MissingGreenlet`（CareEvent VERIFY、CareAction 曾因此 500）。
- `report_version` 由 DB 強制不可變：provenance 在首次 INSERT 一併保存，不可先建草稿再 UPDATE；
  發布前重讀當前摘要版本／狀態。
- Agent proposal 寫入 JSONB 前保存通過 schema／policy 的 `model_dump(mode="json")`，不存含 `datetime`
  的 adapter dict；回歸測試用標準 JSON serializer，不以 `default=str` 掩蓋。
- SQL regex 須經 SQLAlchemy `text()` 編譯檢查 bind keys（POSIX `[:space:]` 的冒號會被當參數）；
  pgvector cosine 查詢拒絕零向量與非有限數值。
- SQLAlchemy engine 維持 `hide_parameters=True`，development `echo` 也不得輸出 bind parameter。

## 授權與業務規則細節

- Repository 查詢明確攜帶 tenant scope；scope 重驗 query 用 `populate_existing=True`，避免 identity map
  沿用鎖等待前的關係／派案。
- 派案：`IN_PROGRESS` 對應 `assignment:start`、`COMPLETED` 對應 `assignment:complete`（以
  `app/schemas/assignment.py` 的 `AssignmentScope` 為準），不得用 `target.lower()` 拼 scope。紀錄與完成命令
  先鎖 assignment 再 claim idempotency，等鎖後重讀版本。指定派案的本人、即時 membership／時窗與 scopes
  共用 `AssignmentAccessService`，不得借同長者其他派案授權。
- 同一居服員／長者有多筆有效派案時，elder-level lookup 不得因 `scalar_one_or_none()` 回 500；
  未指定派案且來源有歧義時拒絕授權，不任選第一筆或聯集 scopes。
- 收案管理（`/staff/enrollments`）不能依賴一般 ElderAccessPolicy（否則暫停後無法恢復），但仍須 live Actor、
  tenant、據點／機構會員、原建立人及同一筆 `enrollment:read`＋`enrollment:manage`。寫入先鎖 Elder 再鎖
  Enrollment；一般照護 query 用 `enrollment_allows_service`，日期行程的收案 gate 用目前時間。歷史表只
  SELECT／INSERT，收案只允許狀態欄位 UPDATE。暫停／結案原子停止平板、對話與派案；恢復不復活舊 token。
- 家屬報表讀取每次重驗目前 `family_relationship.share_scope` 與報表類型；`care_relationship.scope`、
  Consent 或發布 snapshot 都不能替代。摘要來源事件單筆 API 只給目前版本，不可標成生成當時快照或逐字稿。
- 資料用途的 Consent 在查詢與超限判斷前檢查，避免提前錯誤透露資料量。
- Care Event evidence ref 一律 `evidence:<UUID>`（測試也是）；`synthetic:evidence` 這類字串會被 API 過濾，不得為 fixture 放寬格式。
- 長者資料維護（profile／care-profile／history）寫入需獨立 `elder:profile:update`／`care_profile:write`，含版本、冪等、
  受限前後歷史與同交易 outbox；無帳號長者另驗有效收案。
- Native Email 註冊以 `PendingExternalIdentity.provider="KINSUN"` 進入共用 onboarding／invitation
  redemption；新增登入路徑要穿過實際下游 service 驗證 provider allowlist 與 invitation／consent gates，
  不能只 mock redemption。
- Assisted Elder Session：`ks1_`／`ep1_`／`es1_` 不可互換；token 不帶可信 claim，每次由 Core 重建 initiator
  的 live ActorContext 再跑 ElderAccessPolicy。`ASSISTED_TABLET_ACKNOWLEDGEMENT` 只建立 `BASIC_VOICE`，
  `granted_by_actor_id` 必須為 NULL（照服員是記錄者，不是同意當事人）。`ASSISTED_ELDER_SESSIONS_ENABLED`
  預設 false，`APP_ENV=production` 一律拒絕。
- 服務間 request-bound 憑證：綁 method／path／body digest／correlation ID／single-use ID，TTL 1–60 s，
  `hmac.compare_digest`，所有失敗回同一句 "Authentication required"。Replay claim 用
  `service_identity.credential_nonce` 的 `INSERT ... ON CONFLICT DO NOTHING` 在獨立短交易提交；verifier 的
  `replay_store` 必填（漏注入是 `TypeError`，不會退回 process-local），Core 一律用 `DatabaseReplayStore`。
  `SPEECH_SERVICE_IDENTITY_ENABLED`／`CORE_API_SERVICE_IDENTITY_ENABLED` 兩側預設關閉；Speech 與通知各用獨立 secret，
  不得重用其他 secret；`X-Kinsun-Service-Credential` 已列入 log redaction；legacy bearer 只供遷移，不得併用。
  通知端點（`ksvc1`）只限非 production，從 server-configured actor 重查 live tenant membership。
- 個人自述記憶（ADR 0022／0023）：只有本人回合＋明確 `personal_memory_auto_save=true`（語音另需
  `personal_memory_voice_auto_save=true`）的 `LONG_TERM_MEMORY` 同意、STANDARD profile、
  `EVIDENCE_AWARE_MEMORY` 與 `PERSONAL_MEMORY_ENABLED` 全部符合才自動保存（不需 `AUTO_LOW_RISK_MEMORY`，也不偽造
Graph SYNCED 或 Care Event VERIFIED）；擷取範圍有界（音樂、嗜好、
  稱呼、飲食偏好、早餐習慣）。來源標示為本人自述，不得改成已核實照護紀錄；舊同意不自動升級；
  receipt 撤銷與記憶修正／刪除都檢查當前版本。語音保留 ASR evidence 與 voice extractor，ASR TTL 只限制
  新回合；TTS 失敗不得宣稱記憶未保存。
- Log：一般 log 只留 exception type、內部 code 與 correlation ID（`app/core/log_safety.py`）；traceback
  只送 `app.diagnostics`（預設不落地）。`redact_dsn()` 只保留 scheme。值內含 credential 的新設定要登記到
  `_DSN_FIELD_NAMES`。`Settings.model_dump()` 會遮蔽 secret，重驗設定時在程序內用
  `{name: getattr(settings, name) for name in Settings.model_fields}`，不得列印。

## 測試

```powershell
cd services/core-api
uv sync --extra test --extra dev
uv run pytest tests/unit          # 不需資料庫；無 .env 時給合成 localhost DATABASE_URL
# 只可用獨立、可丟棄的 TEST_DATABASE_URL，且 migration lifecycle 須獨立 process 先跑
uv run pytest tests/integration/test_migrations.py
uv run pytest tests/integration --ignore=tests/integration/test_migrations.py
uv run ruff check .
uv run ruff format --check .      # 兩者都在 CI 內；新增 import 後必跑（ASCII 排序易錯）
```

- 新增 migration：同步 `tests/integration/test_migrations.py` 的 `_HEAD_REVISION`、
  `_TOTAL_HEAD_TABLE_COUNT` 與預期表名集合；`alembic heads` 或 collect-only 抓不到過期預期。
- Alembic 另開連線：schema reset、UPDATE、constraint 驗證的 transaction context 都要先 commit／離開，
  再 upgrade／downgrade；不得在同一 `test_engine.begin()` 先 drop 再 upgrade，否則等鎖到 CI timeout。
- `asyncio_default_fixture_loop_scope="session"` 不改 test body 的 loop；`committed_session`／`db_session`
  及相依 async seed fixture 明確 `loop_scope="function"`。NullPool 不能修持有中的跨 loop session；
  不靠測試尾端 commit 掩蓋。Disposable DB 清理先釋放連線再 truncate，保留原始與清理失敗。
- Integration 會對 `TEST_DATABASE_URL` 執行 `alembic upgrade head`，預設 `kinsun_test`，不要指向 `kinsun` 或
  Supabase development。共享 development DB 上不得執行 `committed_session` 的 TRUNCATE teardown。
- Membership 過期 fixture 要合法過去期間（effective_from < effective_to < now）；只把結束時間改成 now−1 秒會違反
  `ck_membership_period`，測不到授權拒絕。不以 sleep 或拆 constraint 處理。
- Real-auth fixture 需要 tenant-level membership（`care_unit_id IS NULL`、role 與 Actor type 一致）；
  測撤權要讓所有可授權路徑到期。修 fixture，不放寬產品 gate。
- PostgreSQL `now()` 是交易起點；模擬既有資料的 effective_from 須早於它。
- JSONB receipt 物件鍵順序可能不同；冪等測試比較物件內容，不比字串。
- 可清除欄位的 idempotency fingerprint 區分省略與 explicit null，保留舊 default 欄位；不要全域改
  `exclude_unset=True`。
- JSON Schema `format: date-time` 依賴 optional format 套件；timezone pattern 與 Pydantic `AwareDatetime` 一起維護。
- `AsyncSession.execute` 的 mock 用 `AsyncMock` 回傳同步 `MagicMock` Result（`all()` 不是 coroutine）。
- pytest `parametrize` 的參數不設 Python 預設值（collection 會失敗）；無獨立 DB 時可用合成設定跑
  `--collect-only`，但不代表 SQL 已驗證。Consent request 新增欄位時同步前端 `core-integration.test.ts`。
- Native-auth integration 測試提供四個獨立合成 secret（含 `FAMILY_INVITATION_HMAC_SECRET`）並停用
  Settings dotenv；先驗 Settings 再寫 DB。Profile HTTP 測試以 scoped monkeypatch 自行啟用
  `assisted_elder_sessions_enabled`，不依賴本機 `.env`。
- Unit test 載入根目錄 `scripts/` 工具時用 `importlib.util` 依檔案路徑載入（Core 自己的 `scripts`
  package 會遮蔽）；手動 DB 工具的 import 不得讀 `.env`、連線或 provisioning。

Schema 變更流程（Supabase development）：先唯讀 `uv run alembic current`／`uv run alembic heads`，人工審查
migration，再 additive `uv run alembic upgrade head`；不得 downgrade、reset 或空庫重建。

## 常用位置

| 工作 | 位置 |
| --- | --- |
| Routes／services／repositories | `app/api/`、`app/services/`、`app/repositories/` |
| Authentication／Session | `app/middleware/auth.py`、`app/adapters/auth/`、`app/services/*identity*`、`*session*` |
| 服務間憑證 | `app/adapters/service_identity.py`、`app/middleware/speech_service_auth.py`、`app/middleware/notification_service_auth.py` |
| Assisted Elder Session | `app/api/assisted_elders.py`、`app/services/assisted_elder_session_service.py`、`assisted_session_tokens.py`、`elder_onboarding_service.py` |
| Models／migrations | `app/models/`、`alembic/versions/` |
