# Wave 2 Caregiver Loop Traceability

- 更新日期：2026-09-07
- 狀態：C04／F02 PostgreSQL-backed HTTP／transaction slice 已通過 CI；真實登入與 Browser QA 的兩項 UI 問題已修正並本機重驗；live Agent E2E 尚未完成

| Requirement | Product linkage | Domain authority | Security gate | Executable evidence | Status |
| --- | --- | --- | --- | --- | --- |
| R1 formal Care Action | US-C04；Story Map Wave 2；WF-04／WF-05 | Core `CareAction`、optimistic `version`、deterministic state machine、transactional outbox | active App Session、`care_action:*` elder scope、professional role、tenant/elder/formal-event check、self-assignment | Core 969 tests、frontend 283 tests、production build、contract static/live validators、8 組 RWD 視覺 QA、development migration head | `VERIFIED_LOCAL` |
| R2 candidate action | US-F02；Story Map Wave 2 | Runtime proposal → private `CareEventVersion` proposal → VERIFY promotion → Core `CareActionCandidate`；只有 ADOPT 呼叫 R1 formal command | `care_action:*` elder scope、professional role、allowlisted source/action、medical text deny gate、future ≤30-day due、optimistic candidate/source version、immutable provenance | Agent 515 tests；Core 1103 unit tests；frontend 299 tests；82-path contract validator；production build；8 組 RWD/locale visual QA | `VERIFIED_LOCAL` |

## Evidence boundary

以下為 R2 implementation slice 當時的證據邊界；後續實際執行結果見本文件的 DB 與 Real-auth Browser QA 段落。

目前已證明人工建立／更新 formal Care Action，以及 AI proposal、VERIFY promotion、Candidate 採納／拒絕／排除的 Core 與 UI contract。R2 Alembic graph 已驗證單一 head `d1f3a5c7e9b0`；2026-09-04 已對 Supabase development database 完成由 `b8d0f2a4c6e7` 至 `d1f3a5c7e9b0` 的 additive upgrade，並讀回 2 張新表、proposal 欄位、索引與 triggers。production build 與 zh-Hant／en 的 390／768／1024／1280 deterministic browser fixture QA 已通過。尚未執行真實登入、真實 Agent-to-database 或 production deployment E2E。

## PostgreSQL acceptance slice（2026-09-07）

新增 `services/core-api/tests/integration/test_care_action_workflow.py` 的 34 個案例，沿用
`core-db` job 的 disposable PostgreSQL 與既有 migration／request integration 分段，不新增 CI job。
身分使用 `FakeAuthenticator` 注入；elder authorization、repository、transaction、row lock、
optimistic write、idempotency snapshot 與 outbox 都使用實際資料庫。Candidate fixture 透過真實
promotion service 建立，不把它當成 live Agent／VERIFY HTTP 全鏈路的證據。

- C04：manual create、自我指派、來源 provenance、開始／延期／完成／取消、舊回應 replay、
  payload conflict、終態拒絕、existing cross-elder／tenant／unreviewed source 拒絕。
- F02：候選採納／拒絕／排除與 reason、正式 action 連結、minimal outbox；same-key／different-key
  adoption、adopt-vs-dismiss 與 formal update 的真實 row-lock contention。
- 故障／安全：candidate/source stale version、來源失效、過期 due、outbox INSERT 後 DB 故障的
  完整回滾與同 key retry；四種 command 在 assignment 過期後連成功 snapshot replay 也拒絕；
  cross-scope／不存在回應一致、非專業／無 assignment 拒絕、medical AI proposal 零寫入。
- 發現並修正 `OptimisticConcurrencyError` exact-type error mapping 遺漏：原本回 500，
  現依既有 contract 回 409／`VERSION_OR_IDEMPOTENCY_CONFLICT`；unit regression 先重現再通過。
- 第一輪 `core-db`（run `34094687215`）揭露 Candidate provenance ORM 錯誤繼承 `updated_at`，
  與 append-only migration 不符，造成真實 INSERT 失敗。已改為 `Base` 明確映射既有欄位並補
  unit regression；不變更已套用 migration，已通過下列 CI 重驗。
- 第二輪（run `34095985265`）有 13 個 update-response cases 回 500；為兩個 mutable Care
  aggregate 加入 `eager_defaults=True`，在 async flush 取回 server／on-update timestamp，避免
  DTO 讀取 expired `updated_at` 觸發隱含 SQL；修正後 13 個案例均通過。
- 本機：Core unit `1107 passed`、完整 Core Ruff lint／format、static contracts 通過；DB
  integration 僅收集。未對 Supabase development database 執行 fixture 或 rebuild。
- 遠端：[PR #29](https://github.com/71bk/kinsun.ai-product/pull/29)，code commit `473dad5`；
  [CI run 34097721039](https://github.com/71bk/kinsun.ai-product/actions/runs/34097721039) 的
  10 個 jobs（含 aggregate）全部成功。`core-db`：19 migration tests、142 request integration
  tests（包含此檔新增 34 個案例）、Core live contract 全通過。無新 migration／CI job。

Task 3.1a 已完成；此 DB slice 本身不是 Browser、live Agent 或 production E2E 證據。

## Real-auth Browser QA（2026-09-07）

已使用 production frontend build、既有 synthetic staff 的真實帳密登入與 Supabase，執行
Browser → BFF → Core → DB 的候選採納／拒絕／排除、人工建立、開始／延期／完成／取消、
雙擊、9 次成功 snapshot replay、真實舊分頁 409、未派案長者與授權失效後 fresh/replay 拒絕。
Mobile 375／390／430 與 desktop 1440 requested viewports 的截圖及 DOM 已檢查。
只將本次建立的兩筆臨時授權到期，保留 synthetic audit rows，沒有 reset 或重設 demo 密碼。

初次發現的兩項問題已修正：care-action 401/403/404 立即卸載舊內容，再查 live elder scope，
不把 resource 404 直接當成 elder-wide denial；登入入口改為中英文 Email/password 文案。
production rebuild 後使用另一批隔離 synthetic campaign 與真實登入，在兩個分頁重驗 create/adopt：
各一次 POST 404，重查請求發出時所有長者名稱／卡片／輸入／對話框已消失，無 reload／自動重送。
前端 315 tests（含 14 權限回歸）／typecheck／lint／build 通過；375／390／430／1440 denied 畫面、
中英文入口與有限 keyboard／reduced-motion 檢查通過；新舊 campaign 權限都已到期，bounded DB digest 未變。
Task 3.1b 與文件同步 3.2 已完成；上述為 commit 前的本機驗證，沒有新的遠端 CI 證據。
Task 3.1c 的 live Agent／VERIFY HTTP 不在這次 fixture 範圍，完整 Wave 2 closeout 仍開放。
完整結果、限制與本機截圖檔名見
[Browser QA report](../../../docs/project/wave2-browser-qa-20260907.md)。

## Remaining product gaps

- US-C04 的 manual create、reason/source/creator/due/status、complete/postpone/cancel reason，以及 US-F02 的 adopt/reject/exclude reason 均已覆蓋。
- Arbitrary assignee／轉派未實作；第一切片刻意只允許 self-assignment。
- Dashboard `open_care_action_count` 尚未接入，屬 US-C01 overview 增量，不影響本 detail workflow 的 Core command 完成度。
