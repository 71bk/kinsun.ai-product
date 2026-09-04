# Wave 2 Caregiver Loop Traceability

- 更新日期：2026-09-04
- 狀態：C04 與 F02 repository implementation 均已完成並通過本地驗證

| Requirement | Product linkage | Domain authority | Security gate | Executable evidence | Status |
| --- | --- | --- | --- | --- | --- |
| R1 formal Care Action | US-C04；Story Map Wave 2；WF-04／WF-05 | Core `CareAction`、optimistic `version`、deterministic state machine、transactional outbox | active App Session、`care_action:*` elder scope、professional role、tenant/elder/formal-event check、self-assignment | Core 969 tests、frontend 283 tests、production build、contract static/live validators、8 組 RWD 視覺 QA、development migration head | `VERIFIED_LOCAL` |
| R2 candidate action | US-F02；Story Map Wave 2 | Runtime proposal → private `CareEventVersion` proposal → VERIFY promotion → Core `CareActionCandidate`；只有 ADOPT 呼叫 R1 formal command | `care_action:*` elder scope、professional role、allowlisted source/action、medical text deny gate、future ≤30-day due、optimistic candidate/source version、immutable provenance | Agent 515 tests；Core 1103 unit tests；frontend 299 tests；82-path contract validator；production build；8 組 RWD/locale visual QA | `VERIFIED_LOCAL` |

## Evidence boundary

目前已證明人工建立／更新 formal Care Action，以及 AI proposal、VERIFY promotion、Candidate 採納／拒絕／排除的 Core 與 UI contract。R2 Alembic graph 已驗證單一 head `d1f3a5c7e9b0`；development database 仍停在 parent `b8d0f2a4c6e7`，本次未把 schema deployment 納入 repository implementation。production build 與 zh-Hant／en 的 390／768／1024／1280 deterministic browser fixture QA 已通過。尚未執行真實登入、真實 Agent-to-database 或 production deployment E2E。

## Remaining acceptance gaps

- US-C04 的 manual create、reason/source/creator/due/status、complete/postpone/cancel reason，以及 US-F02 的 adopt/reject/exclude reason 均已覆蓋。
- Arbitrary assignee／轉派未實作；第一切片刻意只允許 self-assignment。
- Dashboard `open_care_action_count` 尚未接入，屬 US-C01 overview 增量，不影響本 detail workflow 的 Core command 完成度。
