# Agent Runtime 架構總覽

`services/agent-runtime/` 的 M0 Foundation。目標是在不依賴任何 AWS 服務的前提下，
先把邊界、請求流程、契約驗證與測試策略立起來。

```text
HTTP Request
  → CorrelationIdMiddleware
  → Contract validation (Pydantic + JSON Schema)
  → Orchestrator
  → Companion Agent  → ModelProvider
  → Safety Evaluator
  → SuccessEnvelope

例外路徑：DomainError → error_handlers → ErrorEnvelope
```

## 分層

| 層 | 內容 | 位置 |
| --- | --- | --- |
| Middleware | Correlation ID 產生與回傳 | `src/agent_runtime/middleware/` |
| API | `GET /health`、`POST /api/v1/agent/runs`、例外處理 | `src/agent_runtime/api/` |
| Envelope | `SuccessEnvelope`／`ErrorEnvelope`（對應 `contracts/schemas/common/`） | `src/agent_runtime/core/envelopes.py` |
| Contract | Pydantic model；對應 `contracts/schemas/{agent,tools}/` 的 JSON Schema | `src/agent_runtime/contracts/models.py` |
| Orchestration | Agent 選擇、step 控制、Safety gate、狀態組裝 | `src/agent_runtime/orchestration/` |
| Agent | Companion Agent、Safety Evaluator | `src/agent_runtime/agents/` |
| Context | Context Manifest 建構（僅記憶體，無持久化） | `src/agent_runtime/context/` |
| Model | Provider 介面與 Mock 實作 | `src/agent_runtime/models/` |
| Tracing | `trace_id`、`agent_run_id` 產生器 | `src/agent_runtime/tracing/` |

## 為什麼沒有迴圈

M0 只跑一個決策步。沒有 Tool round、沒有 rewrite 路徑，第二輪會重跑一模一樣的
deterministic 流程，不可能改變結果，所以 orchestrator 是明確的單步執行而非迴圈。

這取代了原本的 `while True`——它的結尾是一個有條件 `break` 緊接一個無條件 `break`，
迴圈永遠只跑一輪，`StepLimitError` 永遠不會觸發，step 上限實際上是靠 API 層的重複前置
檢查達成的。真正會消耗 `MAX_TOOL_ROUNDS` 與 `MAX_REWRITE` 的多步迴圈，要與 Tool
執行引擎一起設計。

## Adapter 邊界

外部服務只能在這裡出現：

- `models/provider.py` — `ModelProvider` 介面
- `models/mock_provider.py` — 目前唯一實作，規則式輸出，不呼叫外部 LLM

接 Bedrock／AgentCore、OpenSearch、Neptune 時新增 Provider／Adapter 實作，
由 `settings.MODEL_PROVIDER` 之類的設定切換。**不要把 SDK 呼叫散進 orchestration
或 agent 層**，否則之後無法在沒有 AWS 憑證的環境跑測試。

## Context Manifest 的資料敏感度

`ContextManifestV1` 的 `items[].content` 目前直接放使用者輸入（逐字稿）。
現況是安全的——manifest 只存在於記憶體，API 回應只帶 `context_manifest_id`，
不回傳 manifest 本體。

但 `HandoffEnvelopeV1` **內嵌了整份 manifest**。一旦 handoff 真的跨服務傳遞，
逐字稿就會離開本服務，牴觸根目錄 `AGENTS.md` §8.1「contract 不得包含 Restricted Data」。
在那之前必須先決定：manifest 改成只帶 reference，或在 schema 標註 Restricted 並限制傳遞路徑。

## 目前不存在的東西

Tool 執行引擎、Event Extractor、Memory Candidate、RAG／Graph 實際查詢、
Prompt Registry、Model Router、Agent Trace 持久化、Evaluation runner。

`contracts/schemas/tools/` 已有 `ToolRequestV1`／`ToolResponseV1`，但**沒有任何程式使用它們**。
