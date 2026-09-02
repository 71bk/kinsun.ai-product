# Wave 2 Caregiver Loop Traceability

- 更新日期：2026-09-02
- 狀態：C04 第一切片已完成並通過本地驗證；F02 not started

| Requirement | Product linkage | Domain authority | Security gate | Executable evidence | Status |
| --- | --- | --- | --- | --- | --- |
| R1 formal Care Action | US-C04；Story Map Wave 2；WF-04／WF-05 | Core `CareAction`、optimistic `version`、deterministic state machine、transactional outbox | active App Session、`care_action:*` elder scope、professional role、tenant/elder/formal-event check、self-assignment | Core 969 tests、frontend 283 tests、production build、contract static/live validators、8 組 RWD 視覺 QA、development migration head | `VERIFIED_LOCAL` |
| R2 candidate action | US-F02；Story Map Wave 2 | 尚未建立 proposal/candidate formal boundary；Core Tool 仍 blocked | 待定 deterministic medical boundary 與 human adoption gate | 尚無 | `NOT_STARTED` |

## Evidence boundary

目前已證明人工從 formal Care Event 建立／更新 Care Action 的 Core 與 UI contract；development DB migration 已套用至 `c9d3e5f7a809 (head)`，既有 fixed synthetic Demo authorization rows 也已透過受限同步模式補上 `care_action:*` scopes。production build 與 zh-Hant／en 的 390／768／1024／1280 deterministic browser fixture QA 已通過。尚未執行真實登入 E2E，也尚未建立 Candidate 採納閉環。`contracts/DIVERGENCE.md` 已將 Care Action API 移出未實作清單，但保留 AI Candidate／採納流程為未實作。

## Remaining acceptance gaps

- US-C04 的 manual create、reason/source/creator/due/status、complete/postpone/cancel reason 已覆蓋；candidate confirmation 與 candidate exclusion reason 屬 R2，未完成。
- Arbitrary assignee／轉派未實作；第一切片刻意只允許 self-assignment。
- Dashboard `open_care_action_count` 尚未接入，屬 US-C01 overview 增量，不影響本 detail workflow 的 Core command 完成度。
