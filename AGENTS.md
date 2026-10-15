# AGENTS.md

- 適用範圍：整個 `kinsun.ai` repository。所有代理在分析、設計、實作、測試與文件更新時遵守本檔與 `docs/spec/` 的產品規格。
- 子目錄 `AGENTS.md` 補充該模組的細節與地雷；衝突時以本檔為準。安全、授權與資料規則不得被子目錄放寬。
- 本檔只放跨模組必要規則。現況、進度、指令細節與歷史依下方索引按需讀取；描述進度以可執行程式、contract、
  migration、測試與部署證據為準，不以 README、舊 handover、commit 標題或文件快照判定完成。
- 整理日期：2026-10-15。

## 0. 按需讀取索引

| 要做的事 | 先讀 |
| --- | --- |
| 改 `services/core-api/`（API、service、ORM、migration、Core 測試） | [`services/core-api/AGENTS.md`](services/core-api/AGENTS.md) |
| 改 `packages/frontend/`（頁面、BFF、i18n、Vitest、Browser QA） | [`packages/frontend/AGENTS.md`](packages/frontend/AGENTS.md)＋[MASTER.md](docs/design-system/MASTER.md) |
| 新增或修改 API、Event、Schema、contract | [`contracts/AGENTS.md`](contracts/AGENTS.md)＋core-api AGENTS |
| 改 `services/agent-runtime/`、模型 provider、RAG | [`services/agent-runtime/AGENTS.md`](services/agent-runtime/AGENTS.md)＋[RAG 現況與規則](docs/project/rag-release-history.md) |
| 改 `services/speech-gateway/` 或語音流程 | [`services/speech-gateway/AGENTS.md`](services/speech-gateway/AGENTS.md) |
| 改 CI、`scripts/ci/`、新增跨服務依賴 | [CI Gate 1](docs/runbooks/ci-gate1.md) |
| 啟停本機服務、QA 埠號、清理 worktree、檢查 `.env` | [本機開發與 QA](docs/runbooks/local-dev.md) |
| 了解各元件現況與已退役項目 | [系統現況](docs/architecture/current-state.md) |
| 查某功能做到哪、上次驗收結果 | [進度紀錄](docs/project/progress-log.md)、[交付索引](docs/project/README.md) |
| 產品需求、Persona、驗收條件 | §2 的 `docs/spec/`、[ADR](docs/adr/) |

## 1. 專案狀態

- Voice-first 智慧長照 AI 陪伴系統，源自 AWS Hackathon，現為可獨立維護、可替換雲端 provider 的 Monorepo；可在本機執行與測試。
- 元件：`services/core-api`（唯一 Domain Core）、`services/agent-runtime`（受控 Agent／RAG）、`services/speech-gateway`
  （ASR／TTS 邊界）、`services/rag-ingestion`（staging-only）、`services/notification-worker`（單次 CLI，未部署排程）、
  `packages/frontend`（唯一前端＋BFF）、`packages/shared`（前端型別，非權威）。細節見 [系統現況](docs/architecture/current-state.md)。
- 沒有 production IaC、沒有使用中的 AWS 服務；RAG 全庫 `needs_review`、production 未啟用；真人語音未驗收。
- 功能旗標預設關閉；未經明確授權不啟用 OIDC、ASR、通知、RAG activation 或其他 staging／production 功能。
- 不得把 Target Architecture、mock、adapter、disabled gate、本機或合成測試描述成已實作、已部署或 production-ready。
- 數字型現況（migration head、表數、operation 數、測試數）以當次命令輸出為準，不沿用文件快照。
- 開始實作前，確認工作項目對應的 Persona、User Story、Acceptance Criteria、Domain State、Security Gate 與 Test Gate。

## 2. 規格來源與優先順序

需求解讀依序：

1. `docs/spec/01…產品方向與範圍基準`、`01A…使用者研究與 Demo Persona`。
2. `docs/spec/02…使用者故事與驗收條件`、`03…Story Map`（Wave、Gate、Backlog、Demo Traceability）。
3. `docs/spec/` 的 `06`、`07`、`10`、`11`：Domain、Security、Contract、Test；其他 spec 為 UX、Workflow、Agent、交付、維運。
4. 明確取代舊條款的 Accepted spec／ADR：Spec 17（Account／Elder 分離）、Spec 18（Memory Policy，在其衝突範圍內優先）。

- `docs/spec/*.md` 是唯一權威格式；原始檔由 git 歷史取回。退役的 Kiro 文件不得作為進度或授權依據。
- 文件衝突時：不挑最方便的版本，採較安全、較不洩漏、較可回復的行為，並在變更說明列出衝突、暫定解讀與需 Owner 決策項目。
  已知待收斂：01／02 與 07／11 的延遲門檻、Story Map 總覽 Wave 標籤。

## 3. 核心交付順序

Gate 1 Vertical Slice 是實作脊柱：明確同意後開始語音互動 → 低信心 ASR 要求確認 → 安全簡短的回覆 → Agent 的 Event／Memory
只能是 proposal → Memory 依 Spec 18 的 Consent／Speaker／風險分級決策、照護事件人工覆核 → 正式狀態寫 PostgreSQL 並經 Outbox
發布 → 可重建的 Projection → 後續對話只重用通過 deterministic gate 的 Trusted Memory → 有來源連結的 Daily Summary → 保存
Demo／Trace／Contract／Safety／Failure-path 證據。Wave 與 Backlog 見 `docs/spec/03`。除非使用者明確改變優先順序，不為後期功能犧牲已可演示的閉環。

## 4. 不可違反的產品與安全邊界

- 不提供診斷、治療建議或取代專業照護決策；個人診斷、長照資格、等級、補助額度不由 AI 判定。
- 不把模型輸出、推論、缺少資料或失敗結果描述成已確認事實。
- 不符合 Spec 18 final gate 的 Memory（unverified Speaker、MEDIUM 未確認／stale、HIGH、失效 Consent、不符 lifecycle／scope）
  不得進 Trusted Memory、Graph、報表或後續對話；未覆核的 Event Candidate 不得成為 Verified Event。
- Draft Family Report 不得被家屬或通知預覽取得；`PUBLISHED` Report 是正式內容來源，LINE／Email 只做最小通知與安全連結。
- 長者的「不要記」、「不要再提」、「停止」與 Consent Revocation 立即優先於 Retry、Replay、Backfill、Scheduler 與主動陪伴。
- 不用恐懼、內疚、壓力、欺騙或情緒依賴設計提高互動率。
- Demo、測試、Eval、截圖、Prompt、fixture 只用 Synthetic 或已去識別資料；不得代替真實使用者授予 Consent。

零容忍：

- Cross-elder 或 Cross-tenant 資料暴露；未授權讀寫、Tool 執行或 Consent bypass。
- Secret、Token、完整 Prompt、完整 Transcript／Audio、DSN 出現在一般 log、tool output、錯誤回應或 contract。
  一般 log 不得出現 `str(exc)`、`exc_info=True`、`traceback.format_exc()`；SQLAlchemy 維持 `hide_parameters=True`。
- 檢查 `.env` 只用 dotenv parser 在程序內讀取，輸出 allowlist 名稱、存在與否或相等布林值（細節見[本機開發](docs/runbooks/local-dev.md)）。
- 醫療危險建議；未確認記憶被當成事實；已刪除或撤回資料因 Replay／Projection rebuild 再次出現；
  Draft Report、錯誤收件或超出 Family Share Scope 的內容外洩。

## 5. Authorization、Consent 與資料範圍

- RBAC＋ABAC，預設拒絕。每次正式讀取、寫入及 Agent Tool Command 由 Core 重新驗證 tenant、elder、care unit、
  relationship／family share scope、assignment、consent purpose／version、actor role、resource state、time／purpose。
- 不信任 Client 或模型傳入的 Actor、Tenant、Elder、Assignment、Role 或 Permission Scope；email 不是 Actor authority，不得依 email 自動合併或連結帳號。
- 單一資源的「未授權」與「不存在」回一致回應；失敗的授權不得產生資料修改、Outbox Event 或其他副作用。
- Consent 檢查在資料查詢與超限判斷之前。Consent Purpose 分離，不以總開關代替：`BASIC_VOICE`、`TRANSCRIPT_STORAGE`、
  `CARE_EVENT_EXTRACTION`、`LONG_TERM_MEMORY`、`COMPANION_SIGNAL_ANALYSIS`、`PROACTIVE_COMPANION`、`FAMILY_SHARING`。
  新 scope（如個人記憶自動保存）需明確 opt-in，舊同意不自動升級。撤回後先停止未來處理，再依 Retention／Deletion 處置。
- 家屬報表每次讀取重驗目前 `family_relationship.share_scope`；Consent 或發布 snapshot 不能替代。
- 憑證不可互換：一般 endpoint 只收 `ks1_` Core App Session；`ep1_`／`es1_` 只限 assisted session；服務間呼叫用
  request-bound 短效憑證。照服員代錄的平板同意只建立 `BASIC_VOICE`。
- 測試 fixture 缺權限時修 fixture，不放寬產品 gate 或既有帳號授權。

## 6. 架構不變量

- PostgreSQL／Domain Core 是正式資料與狀態的 Source of Truth；provider 為 Supabase PostgreSQL，不用 Supabase Auth 或專有 Data API。
- Supabase development database 不得承接 integration rebuild、`downgrade base`、reset、truncate 或 fixture 全量重建；
  這些只可用獨立、可丟棄的 `TEST_DATABASE_URL`，沒有就略過並如實回報。
- Graph、Search、Cache、Agent Memory 是 Projection 或 Working State，必須可由正式資料重建；不從它們或模型輸出反推授權或狀態。
- 正式寫入與 Outbox 寫入位於同一交易；投遞依 ADR 0021（PostgreSQL `outbox_event` 為 delivery control plane 與 DLQ 權威）。
  不做 Database＋Graph／Index／Event Bus 的無保護 Dual Write。
- Projection 只接受已通過狀態、授權、同意與刪除檢查的資料；非同步 Consumer 必須 Idempotent、可重試、可觀測，處理前重查撤回、刪除與 Scope。
- 長流程／人工流程用顯式 State Machine，不以 Prompt 狀態代替 Domain State。
- 正式刪除使用 Tombstone，防止 DLQ Replay、Backfill、rebuild 或 Backup restore 復活資料。

## 7. Agent 與 AI 實作規則

- 受控 Orchestrator；不做 Agent Debate、無限遞迴或自由互相呼叫。上限依 Agent 規格（最多 3 次模型決策、2 輪 Tool、5 次 Tool Call、1 次 Rewrite）；
  目前 runtime 只有單一模型決策與 deterministic proposal，沒有通用 Tool loop。
- Agent 只產生不可信 proposal；Core 重新授權、重驗 Consent 並寫入。Agent 不 callback Core、不寫 Domain DB；只能呼叫 Allowlist 中有版本的 Tool，高風險 Tool 由 Core 重做授權、Consent、State、Idempotency 檢查。
- Context 層次：Policy → Auth → Consent → Current turn → Session → Trusted memory → Verified care data → Graph → RAG → Tool results → Output constraints。
  Knowledge／RAG purpose 不得夾帶私人記憶。Current 與 Target（Spec 18／ADR 0014）分開描述，未實作前不得把 Target 當 Current。
- LLM 判斷（含 LLM-as-Judge）不得覆蓋 deterministic Security／Schema／Permission Gate；provider 錯誤不 fallback 到 mock。
- RAG 保存來源、版本、有效日期、覆核狀態與 Metadata Filter；無可靠來源時明確回覆資料不足。外部 RAG 寫入或 activation 需逐次明確授權；
  不得把 needs_review、AI 判定或 synthetic 結果冒充人工 verified。
- 重要 Agent 執行需可追溯 Agent、Prompt、Model route、Policy、Guardrail、Tool schema、Context manifest 與 Release Version。

## 8. API、Event 與版本規則

- REST 用 `/api/v1/...` Major Path Version；WebSocket 只傳 Voice Session State 與已定義事件，不暴露 Prompt、Trace、Secret 或其他長者 Context。
- API、Domain Event、Agent Handoff、Tool、Candidate、Report、Export 都需 Schema Validation。
- 已發布 Event 為不可變契約，破壞性變更建新 `event_version`；Consumer 先支援新舊版本，Producer 才切換。Database 變更採 Expand → Migrate → Contract。
- 使用 Idempotency Key、Optimistic Concurrency、Correlation／Causation ID 與明確 Error Code。
- 保存實際使用的 API、Event、Schema、Agent、Prompt、Model、Policy、Speech、RAG、Graph、Export 與 Release Version，不只記 `latest`。

## 8.1 Contract 規格

- `contracts/`（OpenAPI 3.1、AsyncAPI、JSON Schema）以目前實作為準，與文件 10 的差異記在 `contracts/DIVERGENCE.md`。
- 硬規則：`additionalProperties: false`、enum 與 DB 一致、只用 opaque cursor 分頁（不得有 `offset`／`total`）、不含 Restricted Data、
  invalid 範例必須被拒絕。命名、`$ref`、範例與驗證細節見 [`contracts/AGENTS.md`](contracts/AGENTS.md)。

## 8.2 何時要新增或更新 Contract

- 新 endpoint、Domain Event、Agent Tool 在實作完成後、合併前登記；欄位、狀態碼、分頁或 enum 變更同步更新。
- **尚未實作的 API 不寫進 contract**（`contracts/` 的語意是「這個可以現在打」；設計放 `docs/` 或 Kiro spec）。不為通過驗證放寬 schema。
- 靜態 validator 與 live verifier 都通過才算完成。

## 8.3 回應與例外處理慣例

- 對外回應一律統一 envelope；例外流程固定 `DomainException → error_handlers → ErrorEnvelope`，service 不組裝 HTTP 錯誤。
- 細節（exact-type mapping、404 隱藏資源、跨層值對照）見 [`services/core-api/AGENTS.md`](services/core-api/AGENTS.md)。

## 9. 程式與 Repository 工作方式

- 技術棧（不得自行替換）：Core／Agent／Speech 用 Python 3.12＋FastAPI＋uv（各服務獨立 `pyproject.toml`／`uv.lock`）；Core 用
  SQLAlchemy 2 async＋Alembic＋PostgreSQL；Frontend 用 Next.js 16 App Router＋React 19＋TypeScript＋CSS Modules＋npm workspaces。
  不引入 Django／Flask、同步 ORM、第二套 schema 管理器、Vite、Tailwind、pnpm、自由 Agent loop、直接 SQL／DSL 生成或 browser-held token。
- Production hosting、IaC 與 region 未定案；需要時先提出候選、Trade-off 與 ADR，不復原歷史 CDK profile。
- 結構：Python 服務在 `services/`，npm workspace 成員在 `packages/`；不建 `apps/`、不建獨立 elder／care／family app、不用空目錄表達規劃；
  `projection-worker`／`report-worker` 需要時依 ADR 建立。`config/rag/` 被多個服務與測試寫死，不要搬。
- 分層：route 只處理 HTTP；service 協調 domain／policy／repository／outbox；policy deny-by-default；repository 明確帶 tenant scope；
  外部 Provider／SDK 只在 adapter 邊界。
- Schema 只由 Alembic 管理（`eldercare_ai`）；baseline 與已套用 migration 不可改，新增 revision；autogenerate 必須人工檢查。
- 不建立第二份 schema、authorization mapping 或 response mapping 作為競爭權威。狀態或契約變更同步 Schema、Migration、Test、Traceability 與必要文件。
- `.env` 不進版控；新增設定同步維護只含安全假值的 `.env.example`。新文件使用 LF；保留根目錄 `.gitattributes`。
- 優先做最小、可測試、可回復且能貫穿 Vertical Slice 的變更；不做與任務無關的重構、格式化、依賴升級或文件重寫。
- 保留使用者既有變更；不以 Reset、Checkout 或大量覆寫清除未知修改。
- 需要 Push 時先從最新 `origin/main` 建新分支；禁止直接 Push `main`，不沿用混有其他任務的分支。PR 標題與說明用英文；與 Owner 對話用繁體中文。

## 10. 驗證與完成條件

每個變更依 Acceptance Criteria 驗證，至少涵蓋：

- 正常、低信心、拒絕、撤回、失敗與重試路徑。
- Cross-elder／Cross-tenant／Expired assignment／Revoked share 的 Negative Test；不合格 Memory、Unreviewed Event、Draft Report 進不了正式讀取路徑。
- Assisted session 憑證分離、pairing token 單次使用、replay、過期、cross-tenant 與撤回後對話取消。
- Agent Tool Allowlist、Schema、Max-step、Timeout、Fallback 與 Core reauthorization。
- Outbox、Consumer Idempotency、DLQ、Projection Lag 與 Rebuild；Delete／Revoke 後不會被 Retry、Replay 或 Restore 復活。
- Log、Metric、Trace、Error Response 不含 Restricted Data；測試資料全為 Synthetic。

| 範圍 | 最低命令（細節見各模組 AGENTS） |
| --- | --- |
| 每次 | `git diff --check`、`git status --short` |
| Python 服務 | `uv sync --extra test --extra dev`、`uv run pytest`、`uv run ruff check .`、`uv run ruff format --check .`（Core 為 `tests/unit`；integration 只用 disposable DB） |
| Frontend | `npm run test`／`typecheck`／`build --workspace @elderly-care/frontend`、`npm run lint` |
| Contract | `scripts/validate_contracts.py` 與對應 live verifier |
| Schema | 對 Supabase 先唯讀 `alembic current`／`heads`，人工審查後 additive `upgrade head`；不得 downgrade、reset 或空庫重建 |

- 不虛構測試結果。交付時列出已驗證、未驗證與受環境限制的項目；CI、合成或本機結果不等於外部部署 E2E。
- 本機測試單工、BelowNormal 優先序；subagents 不同時跑測試；已有完整測試後只重跑實際變更涵蓋的定向檢查。
- 尚未建立（不要描述成已完成）：Python type check、自動化 browser E2E、外部部署跨服務 E2E、production IaC。

## 11. 仍待 ADR／Owner 決策

- Production hosting provider、Region、Account／Environment、IaC 工具與成本上限（歷史 AWS profile 不構成決策）。
- 正式模型與 Fallback；Neptune、OpenSearch、LINE、Email、Custom ASR／TTS 採真實服務或 Demo Adapter；service credential。
- Scheduler 頻率；Production API／Event／Client 支援期限；Retention、Export、Legal Hold 與 Offboarding；Voice／Agent／TTS Performance Gate。

不要用暫時實作偷偷取代這些決策；暫時方案標示 Owner、Expiry、Fallback 與移除條件。

## 文件維護規則

- 本檔維持 200 行以內，只放跨模組規則；章節編號 §1–§11 被 ADR 與其他文件引用，不要重新編號。
- 模組地雷寫進該模組的 `AGENTS.md`；交付進度寫進 `docs/project/` 報告並在[進度紀錄](docs/project/progress-log.md)加一筆；
  操作步驟寫進 `docs/runbooks/`。不要在本檔頂部追加日期紀錄。
- 會變動的數字不要寫死，改寫成「以某命令輸出為準」。
