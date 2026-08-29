# Gate 1 Acceptance／State／Security／Test Traceability

- 更新日期：2026-08-29（原始矩陣校準於 2026-08-19；本次只新增五次 evidence 的覆蓋邊界說明與
  對應的 Core 側 integration 覆蓋，未重跑 2026-08-19 的 executable baseline）
- 校準提交：矩陣為 `3e2a15d`；邊界補記為 2026-08-29 工作樹
- 適用範圍：canonical synthetic Gate 1；production provider、部署與效能核准仍由 Owner gate 管理

本檔把 [`requirements.md`](requirements.md) §5 與 [`design.md`](design.md) §13 連回產品故事、
Domain State、Security Gate 與 executable test evidence。狀態只代表列出的證據，不把 adapter、
未執行 integration test 或 target architecture 誤寫成已部署能力。

## 狀態定義

- `VERIFIED_LOCAL`：2026-08-19 已執行列出的本機測試並通過；DB 項目使用 Docker 的獨立
  `kinsun_test`，未連 development Supabase。
- `VERIFIED_LOCAL_SYNTHETIC`：ADR-0009 synthetic functional acceptance 已通過；不包含 production
  provider、部署、效能、品質、data region、availability 或成本核准。
- `RELEASE_BLOCKED`：不阻擋本 Spec 的 synthetic completion，但在 production release 前必須由
  Owner 核准且以目標環境 evidence 解除。

## 五次 evidence 的覆蓋邊界（2026-08-29 補記）

`scripts/verify_gate1_cross_service.py` 只驗 **Core `AgentRuntimeClient` adapter → Agent Runtime
HTTP** 這一段。它自行組出 request payload（含 `requested_outputs`），因此 `CompanionService`
從未執行，Core 的 authorization、Consent、ASR Gate 與 speaker evidence 判斷**不可能讓這五輪失敗**；
每一輪也都是 `input_text`，沒有任何語音路徑。

這個邊界曾造成實際漏網：語音輪次的 speaker evidence 一律為 UNKNOWN，US-D01／US-D02 在語音介面上
無法達成，卻在 Gate 1 標記完成後第 9 天（2026-08-28、`31f7a81`）才被發現。因此讀到
`5/5 passed` 時，不得推論 Core 側判斷已被驗證。

Core 側對應覆蓋在
`services/core-api/tests/integration/test_companion_voice_memory_path.py`（真實 DB 上的 gated
Elder-only voice session、staff-initiated session、缺 ASR evidence 與 Consent 過期四種情形），
由 CI 的 `pytest tests/integration` 執行。

## Requirement matrix

| Requirement | Persona／User Story | Domain State／正式權威 | Security Gate | Test Gate／executable evidence | Current status |
| --- | --- | --- | --- | --- | --- |
| R1 Canonical topology | 林阿嬤；US-A01、US-A06 | Browser → BFF → Core；Core-owned `AgentRun`；Voice Ticket 單次 consume | BFF-only、signed service credential、server-derived empty Tool scope、未驗 caller／replay deny | `test_service_identity.py`、`test_companion_service.py`、`test_voice_ticket_codec.py`、`test_voice_ticket_api.py`、Agent API integration、五次 Core→Agent HTTP | `VERIFIED_LOCAL_SYNTHETIC` |
| R2 Purpose-separated Consent | 林阿嬤；US-A06 | `BASIC_VOICE`、`TRANSCRIPT_STORAGE`、`CARE_EVENT_EXTRACTION`、`LONG_TERM_MEMORY` 分離；revoke 先停止處理 | Core 每次重驗 purpose/version；revoke 取消 active voice，失敗零 Candidate／outbox | `test_consent_service.py`、`test_consent_voice_session_cancellation.py`、`test_asr_gate_service.py`、Docker DB integration | `VERIFIED_LOCAL` |
| R3 Voice／low confidence | 林阿嬤；US-A01、US-A02、US-A03、US-A05 | `CREATED → RECORDING → PROCESSING → LOW_CONFIDENCE_CONFIRMATION／RESPONDING → COMPLETED`，另有 cancel／timeout／fail | server-side ASR Gate；未確認 transcript 不進 Agent；audio／transcript 不進一般 error／log | `test_asr_gate_service.py`、`test_asr_gate_agent_input.py`、Speech Gateway 25 tests、`canonical-voice-turn.test.ts` | `VERIFIED_LOCAL_SYNTHETIC`；production 語言品質／provider 為 `RELEASE_BLOCKED`；五次 evidence 全為文字輸入，不驗語音路徑 |
| R4 Safe companion | 林阿嬤；US-A03、US-A04、US-A05 | Core 組合 trusted Context；Runtime proposal-only；dependency fail 使用 no-guess fallback | service auth、bounded decision、Safety block、私人記憶只供 voice purpose | `test_companion_service.py`、`test_companion_request.py`、Agent Runtime 317-test suite | `VERIFIED_LOCAL`（synthetic／mock） |
| R5 Event candidate review | 照服員；US-B01、US-B03 | `CANDIDATE／NEEDS_REVIEW → VERIFIED／CORRECTED／REJECTED`；正式 transition＋outbox 同交易 | assignment／tenant／elder／Consent／version／idempotency；未覆核事件不進正式 read | `test_care_event_api.py`、`test_event_consumer.py`、Event review UI tests、Docker DB integration | `VERIFIED_LOCAL` |
| R6 Risk-tiered Memory | 林阿嬤；US-D01～D04 | LOW all-of 可 ACTIVE；MEDIUM fixed version confirmation；HIGH 零 Memory row；inactive/delete tombstone | verified Elder speaker、Core policy、version/digest/question/Consent binding、retrieval-time final gate；witness 只證明回答 | `test_memory_policy.py`、`test_memory_service.py` 17 tests、`test_memory_retrieval_policy.py`、Speech affirmative／low-confidence zero-side-effect tests、`test_companion_voice_memory_path.py`（DB 上的語音 speaker gate） | `VERIFIED_LOCAL_SYNTHETIC`；五次 evidence 不涵蓋語音與 Core 側判斷，見上方邊界節 |
| R7 Formal state＋Outbox | 維運／Domain Owner | PostgreSQL Source of Truth；formal state 與 outbox 同 transaction | rollback、idempotency、correlation／causation、禁止 dual write | `test_outbox_writer.py`、`test_event_publisher.py`、`test_property_outbox_atomicity.py`、Docker PostgreSQL 108 tests | `VERIFIED_LOCAL` |
| R8 Projection／reuse | 林阿嬤；US-D03、US-B04 | synthetic projection reference 可重建；Core formal state 最後決定可見性 | process/replay 前重驗 state／scope／tombstone；cross-scope 零結果 | `test_graph_projection.py`、`test_synthetic_projection.py`、`test_event_consumer.py`、`test_companion_service.py` | `VERIFIED_LOCAL`（ADR 0009 synthetic adapter；非 production Graph） |
| R9 Daily Summary | 照服員；US-B02、US-C01、US-C02 | verified/corrected-event-only draft；review／stale／rebuild；Gate 1 不發布 Family Report | authorized elder scope、bounded source references、missing-data 明示 | `test_summary_generation.py`、`test_summary_api.py`、Frontend summary tests、Docker DB integration | `VERIFIED_LOCAL` |
| R10 Privacy／observability | 三位 synthetic Persona | bounded trace metadata；Restricted Data 不複製進一般觀測資料 | unauthorized/nonexistent equivalence、restricted-key guard、service caller denial | `test_restricted_keys.py`、`test_correlation.py`、live contract denial、五次 response-key scan | `VERIFIED_LOCAL_SYNTHETIC` |
| R11 Gate evidence | 林阿嬤主線、張阿姨 cross-elder、陳伯伯 assignment | 不新增正式 state；保存 fixture、五次可重跑 evidence 與 CI artifact | failure path 不得有 cross-scope、confirmation bypass、Restricted Data 或 resurrection | versioned fixture、Core 893＋108、Agent 320、Speech 25、Frontend 220、contracts、五次 HTTP evidence | `VERIFIED_LOCAL_SYNTHETIC` |
| R12 Owner decisions | Project／Security／Architecture Owner | ADR 保存 synthetic boundary、Fallback 與 production release blockers | 未核准 production provider／threshold 不得由 runtime 默認 | ADR-0009 synthetic profile 已採用；evidence 明列 `production_approved: false` 與 excluded claims | Synthetic Spec complete；production 為 `RELEASE_BLOCKED` |

## Product／spec linkage

- Persona 與去識別邊界：`docs/spec/01A智慧長照 AI 陪伴系統－使用者研究與 Demo Persona v0.2.md`。
- User Story／Acceptance Criteria：`docs/spec/02智慧長照 AI 陪伴系統－使用者故事與驗收條件 v1.3.2.md`。
- Gate 1 thin slice 與 US-A／B／C／D 對照：`docs/spec/03智慧長照 AI 陪伴系統－Story Map v1.2.md`。
- Voice、Event、Memory、Summary 與恢復狀態：`docs/spec/05智慧長照 AI 陪伴系統－核心工作流、狀態機與錯誤恢復 v0.1.md`。
- Domain／RLS／Scope：`docs/spec/06智慧長照 AI 陪伴系統－資料模型、事件模型與 RLS 權限規格 v0.1.md`。
- Security／Consent／Restricted Data：`docs/spec/07智慧長照 AI 陪伴系統－資安、隱私、同意、資料治理與 Trust Model v0.1.md`。
- Executable contract 規則：`docs/spec/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`。
- Unit／Integration／E2E／zero-tolerance gate：`docs/spec/11智慧長照 AI 陪伴系統－測試策略、Agent Evaluation 與品質門檻 v0.1.md`。
- Memory 衝突範圍以 Spec 18／ADR 0014 優先；synthetic service boundary 以 ADR 0009 為準。

## 2026-08-19 executable baseline

| Component | Command | Result |
| --- | --- | --- |
| Core API unit | `uv run pytest tests/unit -q` | `893 passed` |
| Core API integration（Docker `kinsun_test`） | `uv run pytest tests/integration -q` | `108 passed` |
| Agent Runtime | `uv run pytest -q` | `320 passed` |
| Speech Gateway | `uv run pytest -q` | `25 passed`，另有 1 個 dependency deprecation warning |
| Frontend | `npm run test --workspace @elderly-care/frontend -- --run` | `220 passed` |
| Core／Agent live contracts | `verify_contract_live.py`＋`verify_agent_contract_live.py` | 全部通過；Core 73 runtime operations 均有 contract |
| ADR-0009 five-run | `python scripts/verify_gate1_cross_service.py` | `5/5 passed`；每次含 blocked zero-candidate path |

Docker PostgreSQL 使用 `postgresql+asyncpg://…@localhost:5432/kinsun_test`；integration fixture 只在此
獨立資料庫建表、migration、seed 與清理，不使用 development `kinsun` 或 Supabase。Frontend typecheck、
lint、production build，三個 Python service 的 Ruff checks，以及 contract static validator 亦已通過。

## Open decision／blocking register

| Blocker | Owner／required input | Safe fallback |
| --- | --- | --- |
| Production ASR／TTS provider、語言 quality gate、data region、cost／latency threshold | Product＋Architecture＋Security Owner | 繼續 ADR 0009 synthetic profile，只記 functional baseline |
| Production Graph／Model／Guardrails／cost ceiling | Architecture＋Safety＋Project Owner | synthetic projection＋mock model；不得宣稱 production ready |
| AWS staging deployed E2E／availability evidence | Architecture＋Security＋Operations Owner 與可操作的 staging runtime | 本機 Docker＋ADR-0009 synthetic acceptance；不得描述成 AWS staging 已完成 |
