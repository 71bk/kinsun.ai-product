# ADR 0020：Agent Run 使用單一 deadline 與顯式 execution counters

- 狀態：Accepted
- 日期：2026-09-03
- 相關：[ADR 0005](0005-agent-runtime-api-conventions.md)、
  [Agent Runtime 架構總覽](../architecture/agent-runtime-overview.md)

## 背景

`AgentRunRequestV1` 要求 `latency_budget_ms`，Runtime 也宣告 `MAX_AGENT_DECISIONS`、
`MAX_TOOL_ROUNDS` 與 `MAX_TOTAL_TOOLS`，但 canonical orchestrator 原本只檢查 `max_steps`，
沒有把 latency budget 套到 retrieval 或 Model Provider。Tool limits 也只存在設定物件，容易讓
呼叫者或維護者誤以為已有 bounded Tool loop。

目前 canonical flow 只有一個 Model decision；Event／Memory extraction 是 deterministic proposal，
不是 Tool call。此 ADR 不授權新增 Tool engine、Core callback、重試或 cross-agent handoff。

## 決策

1. 每個 Agent Run 由 `latency_budget_ms` 建立一個 monotonic end-to-end deadline，不在各階段重新
   起算 timeout。
2. Retrieval、Model Provider、Event extraction 與 Memory extraction 的 await 都使用相同的剩餘時間；
   orchestrator 外層同時保留整體 timeout，避免階段間的程式繞過 deadline。
3. Deadline 用盡時取消目前 await，回傳合約內的 `SAFE_FALLBACK` 與
   `LATENCY_BUDGET_EXCEEDED`，不回傳 partial model output 或 candidate proposal。
4. Structured warning 只記錄設定的毫秒數與 decision／Tool counters，不記錄 input、prompt、query
   或 provider error message。
5. `ExecutionBudget` 在任何 work 開始前原子保留 decision 或整輪 Tool 數量；超過 decision、round
   或 total ceiling 時，以 `StepLimitError` fail before call，且失敗 reservation 不改變 counters。
6. 現階段沒有 canonical Tool call，因此 Tool counters 在實際 request 中維持零。未來 Tool loop
   必須透過 `consume_tool_round()`，並另行定義 Core reauthorization、idempotency 與 failure state。

## 後果

- 呼叫者提供的 latency budget 現在是可執行的 request-level 上限，而非描述性欄位。
- 超時 recovery path 為 deterministic no-partial fallback；caller cancellation 仍直接向上傳遞。
- Async provider／retrieval 可由 task cancellation 中止；底層不支援取消的同步 SDK work 仍只能等其
  自身 transport timeout 結束，因此 adapter 自身仍必須具備 bounded timeout／capacity。
- `MAX_TOOL_ROUNDS`／`MAX_TOTAL_TOOLS` 不代表 Tool engine 已存在；它們只定義未來實作不可繞過的
  reservation primitive。
