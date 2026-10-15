# 系統現況與元件邊界

整理日期：2026-10-15（自根目錄 AGENTS.md §1 拆出）。本檔是架構知識，不是進度證明；描述現況以可執行程式、
contract、migration、測試與部署證據為準，數字以當次命令輸出為準。各功能交付細節見
[交付主題索引](../project/README.md)與[進度紀錄](../project/progress-log.md)。

## 整體

本專案源自 AWS Hackathon，現為可獨立維護、可替換雲端 provider 的 Voice-first 智慧長照 AI 陪伴系統。
Repository 是可在本機執行與測試的 Monorepo。一般 HTTP 主線：Next.js BFF → Python Core → Agent Runtime。
目前沒有 production IaC，也沒有使用中的 AWS 服務。

## services/core-api — 正式 Domain Core

- 已有 Identity／Actor、Kinsun-owned Email＋Password（Argon2id、bounded attempt／lockout）、Core App Session、
  direct Google／LINE OIDC handoff、受限帳號連結（ADR 0010／0011／0015）、Elder scope、Consent、Voice
  Ticket／ASR Gate、Care Event、Memory、Daily Summary、Family Report、Assignment、Enrollment、Elder profile
  維護、Deletion、Agent Run、受控 Tool、LINE Messaging／通知、家屬通知偏好，以及 transactional outbox 與
  provider-neutral publisher／consumer（ADR 0021）。正式狀態只由 Core database 與 Command Gate 擁有。
- 寄信只有 synthetic development delivery；production email、password reset／change、MFA 與
  breached-password screening 未完成。Cognito runtime 與 `actor.cognito_sub` 已移除。
- **Staff-assisted accountless Elder Session**（預設關閉）：`elder_enrollment`、`elder_care_profile_entry`、
  `assisted_elder_session` 等表與 `app/api/assisted_elders.py`。照服員建立沒有 Actor 的長者，發一次性
  `ep1_` pairing token 換 HttpOnly `es1_` Elder Session。無帳號長者沒有 Elder Actor，speaker gate 無法判定
  verified Elder speech，Event／Memory proposal 維持關閉。2026-09-29 起可記錄長者口頭意願後交付平板語音，
  `conversation_session.assisted_session_id` 綁定當次 handoff；只以合成 MediaStream 驗證，真人未驗收。
  `consent_grant` 另有 `confirmation_method`／`recorded_by_actor_id`／`assisted_session_id`。Kiro spec 與 release blocker：
  `.kiro/specs/staff-assisted-elder-session/`（見其 `traceability.md`）。
- **服務間 request-bound identity**：取代長效 bearer；replay state 由 `service_identity.credential_nonce`
  跨 replica 保存。Speech→Core 與 notification-worker→Core（`ksvc1`，限非 production）各有獨立 profile。
- Schema：Alembic 管理，domain schema `eldercare_ai`（baseline 48 表；2026-10-15 為 43 個 revision 檔、
  head `a1c3e5f7b902`、70 張業務表），另有 `rag_public` 與 `service_identity`。

## services/agent-runtime — 受控 Agent Runtime

- 單輪閉環：contract 驗證 → 受控 Orchestrator → Companion Agent → deterministic Safety Evaluator →
  Event Candidate proposal 與 bounded Memory Candidate proposal。Runtime 不 callback Core、不寫 Domain DB。
- Memory current first slice：只辨識明確固定早餐習慣，proposal 綁 Event Candidate version，照護者 VERIFY
  後由 Core 重驗 `memory:candidate:create` 與 `LONG_TERM_MEMORY` Consent，建立仍需長者本人以 `ELDER_UI` 確認才可 ACTIVE
  的 Memory Candidate。另有個人自述記憶分支（ADR 0022／0023）。Target 依
  Spec 18／ADR 0014（LOW all-of 自動保存、MEDIUM 固定版本確認、HIGH 不建 row），未實作前不得當 Current。
- `BASIC_VOICE` 可帶 Core 重驗 `memory:read` 與 active `LONG_TERM_MEMORY` 後最多 5 筆 Confirmed Memory（尚無語意排序）；
  `trusted_care_profile`（`CARE_PROFILE_AI_CONTEXT_ENABLED`，預設關閉）只帶
  `RECORDED`／`VERIFIED` 未退場條目並加固定安全 prompt 規則。Verified care data／Graph 未接入 Context。
- Model provider：`mock`（repository 預設）、`bedrock`、`openai-compatible`、`gemini`（`AQ.` key 走 Vertex AI，
  其他走 Gemini Developer API，不混用）。錯誤不 fallback 到 mock。本機 development 已以真實 Vertex 驗收
  （generation `gemini-3.8-flash`、embedding `gemini-embedding-001`）。
- RAG：provider-neutral `SearchBackend`／`EmbeddingProvider`，PostgreSQL FTS／trigram＋pgvector Hybrid 為預設；
  V3 自然問句生成附 1–5 筆引用。版本沿革見 [RAG release 歷史](../project/rag-release-history.md)。
  全庫仍 `needs_review`、`production_approved=false`，production 未啟用。legacy OpenSearch adapter 保留，不接 Neptune。

## services/speech-gateway

ASR／TTS adapter 與 Core Voice Ticket／server-side ASR Gate 邊界（`asr.py`、`tts.py`、`sagemaker_asr.py`、
`core_voice_gate.py`）。Browser 有 Voice Ticket 保護的 JSON audio upload 與低信心確認 UI。真實 endpoint、
WebSocket binary transport、成本與 quality gate 未部署／驗證。

## services/rag-ingestion

RAG 文件 ingestion 與 allowlist 建置，staging-only；與 `config/rag/` 共用設定（路徑寫死在 agent-runtime
settings、Dockerfile、`.env.example` 與測試，不要搬）。本機整理入口另有 `scripts/rag/prepare_knowledge.py`、
`embed_knowledge.py`（預設 dry-run）。

## services/notification-worker

LINE Daily Notification 單次 CLI（`run_daily.py`），預設 dry-run，明確工作時間、有限重試、安全摘要；job 邏輯在
Core。沒有常駐 worker framework、每日 Scheduler、SQS 或 DLQ deployment。`projection-worker`／`report-worker` 不存在。

## packages/frontend 與 packages/shared

- `packages/frontend`：唯一前端，單一 multi-role PWA＋BFF（ADR 0006）。三角色 route group、平板交接、
  家屬／專業公開問答（`/family/knowledge`、`/staff/knowledge`）、家屬通知設定（`/family/notifications`）。
  Next.js 已依 ADR 0008 升至受支援 release；本機 production audit／Linux image smoke 通過，不代表已部署。
- `packages/shared`：前端使用的 TypeScript 型別（可能有未使用型別）；不是 Domain authority，跨服務形狀以
  `contracts/` 為準。

## 其他目錄

`config/`（RAG 與 LINE 設定）、`data/`（RAG chunks、manifest、seed）、`evals/`（speech、RAG 評估）、`.qa/`（手動 smoke／schema
驗證，需真實 Supabase、不在 CI，執行前確認唯讀或可回復）、`scripts/`（contract、CI、RAG、image 工具）、`docker/`（參考用）。

## CI 與部署相關

- CI：`.github/workflows/gate1.yml`，見 [CI Gate 1](../runbooks/ci-gate1.md)。
- 四個 runtime／migration image 可由 `scripts/build_runtime_images.ps1`／`.sh` 本機建立驗證，不 push registry；
  外部 endpoint 可用 `scripts/smoke_test_deployment.py`（[runbook](../runbooks/deployment-smoke.md)）。兩者都不代表
  hosting infrastructure 已完成。

## 已退役與歷史

- **ADR 0007 判定為 legacy 的整套已於 2026-08-06 刪除**：原 TypeScript 後端、legacy CDK app／stack／constructs、
  `infra/lambda-stubs/`。要查歷史用 `git log --follow`。
- 可執行 CDK profile、AWS preflight／deployment scripts、active runbook 與 `.github/workflows-disabled/pr.yml` 已於
  2026-09-02 依 ADR 0019 退役；歷史 AWS spec／ADR／handover 只保留決策與證據。
- 歷史 AWS Target Architecture 曾包含：ECS/Fargate modular monolith、API Gateway、Bedrock AgentCore／Guardrails、
  Aurora、Neptune Serverless、OpenSearch Serverless、S3、EventBridge、SQS／DLQ、Step Functions、Scheduler、SES。
  只是歷史規劃，不是現行 baseline。
- 文件 12 的三-app 骨架（`apps/`）、空 `/tests`、`/ops` 已移除。目錄分類軸線是 runtime／toolchain：Python 服務在
  `services/`，npm workspace 成員在 `packages/`；不套用 Turborepo／Nx 的 `apps/` 慣例，不用空目錄表達規劃。
- 規格曾有 `.md`／`.json`／`.csv`／`origin/` 原始檔四種格式且無人同步；2026-08-06 起只留 `.md`，原始檔用
  `git show <commit>:docs/spec/origin/<檔名>` 取回。
- `.kiro/steering/` 原有 5 個重述規則的檔，已併回 AGENTS.md，現只轉發。
