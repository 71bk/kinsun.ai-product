# Agent Runtime 架構總覽

`services/agent-runtime/` 目前是 M0 Foundation，加上 Core-owned Event proposal 與 bounded
Memory proposal 路徑。預設本機設定使用 `MockModelProvider`，可在沒有 AWS 服務的環境驗證主要邊界；程式另有
可設定的 Bedrock Converse／OpenAI-compatible text provider 與 staging-only RAG adapter，但尚無真實外部 staging 或
production runtime 驗證，不能把 adapter 存在描述成服務已部署。

```text
HTTP Request
  → CorrelationIdMiddleware
  → Contract validation (Pydantic + JSON Schema)
  → Orchestrator
      → ExecutionBudget（單一 latency deadline＋decision／Tool counters）
      → explicit knowledge purpose? → staging Retriever
          → SUCCESS: 3–5 個限長、帶引用 chunk → Context Manifest
          → NO_DATA/FAILED: no-guess SAFE_FALLBACK（不呼叫 ModelProvider）
      → Companion Agent → configured ModelProvider
      → Safety Evaluator
      → allowed RAG reply: deterministic citation append
      → Safety ALLOW + Core requested event_candidate?
          → deterministic Event Extractor → typed Event proposal
      → Event proposal exists + Core requested memory_candidate?
          → deterministic Memory Extractor → typed Memory proposal
  → SuccessEnvelope

一般例外：DomainError → error_handlers → ErrorEnvelope
Core→Runtime 依賴失敗：fail closed → sanitized 503

Staging RAG Request
  → RetrievalRequestV1
  → BedrockQueryEmbedder (`search_query`)
  → 受控 HybridSearch plan（固定 filter＋設定化權重）
  → OpenSearchClient
  → 3–5 個帶完整引用的 chunk，或明確 no-guess fallback
```

## 分層

| 層 | 內容 | 位置 |
| --- | --- | --- |
| Middleware | Correlation ID 產生與回傳 | `src/agent_runtime/middleware/` |
| API | `GET /health`、Agent Run、staging RAG Retrieval、例外處理 | `src/agent_runtime/api/` |
| Envelope | `SuccessEnvelope`／`ErrorEnvelope`（對應 `contracts/schemas/common/`） | `src/agent_runtime/core/envelopes.py` |
| Contract | Pydantic model；對應 `contracts/schemas/{agent,tools}/` 的 JSON Schema | `src/agent_runtime/contracts/models.py` |
| Orchestration | Agent 選擇、step 控制、RAG、Safety gate、受控 Candidate proposal、狀態組裝 | `src/agent_runtime/orchestration/` |
| Agent | Companion Agent、deterministic Event／Memory Extractor、Safety Evaluator | `src/agent_runtime/agents/` |
| Context | Context Manifest 建構（本輪輸入、Core 授權的 Confirmed Memory、可選 RAG；僅記憶體，無持久化） | `src/agent_runtime/context/` |
| Model | Provider 介面、共用安全 Prompt、預設 Mock、可設定 Bedrock Converse 或 OpenAI-compatible HTTP adapter | `src/agent_runtime/models/` |
| Legacy Core integration | 非 canonical 的早期 AgentRun register／complete adapter | `src/agent_runtime/core/` |
| Legacy Tool | 非 canonical 的早期 Core Tool request builder／executor | `src/agent_runtime/tools/` |
| Tracing | `trace_id`、本地識別碼工具；正式 Candidate run ID 由 Core 建立 | `src/agent_runtime/tracing/` |
| RAG | Bedrock query embedding、受控 hybrid plan、OpenSearch adapter、引用與 fallback | `src/agent_runtime/rag/` |

Agent Run 的 RAG intent gate 目前只接受明確的 `general_information` 或 `legal_reference`
purpose，不以自由文字猜測意圖。這讓一般 `conversation` 維持原流程，也讓知識檢索不可用時
能明確 fail closed。預設 Mock provider 不理解 RAG context；設定式 `BedrockModelProvider` 與
`OpenAICompatibleModelProvider` 都會讀取 Context Manifest 中的 approved excerpts，仍須經 deterministic
Safety 與 citation 後處理。這只證明 adapter 與離線測試邊界存在，不代表真實 Bedrock、
OpenSearch 或 production Guardrails 已驗證。

## 為什麼沒有通用迴圈

目前 Companion 固定只跑一個 bounded model decision。若 Safety 允許，Runtime 只依 Core 明確
推導的 `requested_outputs` 執行 deterministic Event／Memory extraction 並回 typed proposal；
Runtime 不 callback Core，也不寫 Domain DB。每個 Agent Run 現在以 request 的
`latency_budget_ms` 建立單一 monotonic deadline，RAG、Model Provider 與 deterministic extraction
共用剩餘時間；超時取消目前 await、回 `SAFE_FALLBACK`，並只記錄 bounded counters。
`MAX_TOOL_ROUNDS`／`MAX_TOTAL_TOOLS` 已進入 `ExecutionBudget` 的原子 reservation 邊界，但目前
canonical 流程不執行 Tool，因此兩個 counter 固定為零；`MAX_REWRITE` 仍未使用。

因此目前不是通用多 Tool 迴圈，也沒有自由重試、Agent Debate 或 cross-agent handoff。真正會
消耗多輪 Tool／rewrite budget 的控制流程，必須另行設計顯式停止條件、Core reauthorization
與可測試的 failure state，不能把現有單次 Candidate 路徑描述成已完成的 Tool engine。

完整決策與限制見 [ADR 0020](../adr/0020-agent-run-execution-budget.md)。

## 受控 Event／Memory Candidate proposal 路徑

Canonical Core 路徑依序套用以下 Gate：

1. Core 先以 live authorization 與 `CARE_EVENT_EXTRACTION` Consent 決定是否要求
   `event_candidate`。
2. 只有另外通過 `memory:candidate:create` 與 `LONG_TERM_MEMORY` Consent，才加上
   `memory_candidate`。
3. Safety 必須為 `ALLOW`；Memory proposal 還必須同時有 Event proposal。
4. Runtime proposal 不含 actor／tenant／elder／session／consent／source ID 或逐字稿。
5. Core 完成 session 後重新授權並建立 `NEEDS_REVIEW` Event Candidate；Memory proposal 只私下
   保存在該 Event version。
6. 照護者 VERIFY 來源事件後，Core 再重驗 memory authorization／Consent 與 verified source，
   才建立仍為 `CANDIDATE` 的 Memory。
7. 只有長者本人後續以 `ELDER_UI` 明確確認，Memory 才能轉為 `ACTIVE`。

Memory first slice 只辨識「我每天早餐都吃粥」這類明確固定早餐習慣；不處理一般聊天、一次性
事件、健康／情緒／陪伴需求推論、其他 Memory 類型或 conflict detection。現有早期 `core/` 與
`tools/` adapter 只為相容保留，canonical orchestrator 不使用它們。

## Adapter 邊界

外部服務只能在以下 Provider／Adapter 邊界出現：

- `models/provider.py` — `ModelProvider` 介面
- `models/mock_provider.py` — 預設本機規則式實作，不呼叫外部 LLM
- `models/bedrock_provider.py` — 可設定 Bedrock Converse adapter；model ID 仍是 Owner 決策
- `models/openai_compatible_provider.py` — provider-neutral 文字 Chat Completions adapter；URL、
  model 與 optional Bearer key 由 runtime 注入，可接相容本機服務或 Google Gemini API
- `models/prompting.py` — 所有文字模型共用的 Companion／RAG 安全 prompt 建構
- `core/` — Core AgentRun register／complete adapter
- `tools/` — allowlisted Core Tool request／result adapter
- `rag/query_embedder.py` — Bedrock query embedding adapter
- `rag/client.py` — SigV4 OpenSearch adapter

接其他文字模型或 Neptune 時新增 Provider／Adapter 實作，由設定切換。**不要把
SDK 呼叫散進 orchestration 或 agent 層**，否則之後無法在沒有 AWS 憑證的環境跑測試。

## Context Manifest 的資料敏感度

`ContextManifestV1` 的 `items[].content` 目前直接放使用者輸入（逐字稿）；`BASIC_VOICE` 也可放
最多 5 筆由 Core 重驗 `memory:read`、active `LONG_TERM_MEMORY` Consent、tenant／elder、status、
current version 與 consent version 後提供的 Confirmed Memory。這些項目以 `confirmed-memory`
標記並明示為資料而非指令；Knowledge／RAG purpose 由 request contract 禁止攜帶。
現況下 manifest 只存在於記憶體，API 回應只帶 `context_manifest_id`，不回傳 manifest 本體。

但 executable `AgentRunRequest.input_text` 已能在 Core→Agent 呼叫中攜帶 current turn。正式
canonical path 在啟用前必須採 reference，或建立經核准的 private Restricted Data service
contract，涵蓋雙向 service authentication、傳輸加密、資料最小化、bounded retention／timeout
cleanup 與 audit；「不寫一般 log」本身不足以構成安全傳輸邊界。

此外，`HandoffEnvelopeV1` **內嵌了整份 manifest**。一旦 handoff 真的跨服務傳遞，逐字稿就會
離開本服務，牴觸根目錄 `AGENTS.md` §8.1「contract 不得包含 Restricted Data」。在啟用
handoff 前，必須先決定 manifest 改成只帶 reference，或建立明確的 Restricted Data 傳輸、
授權與 retention 邊界。

## 目前不存在的東西

目前尚未實作：通用多 Tool 執行迴圈、其他 Memory 類型的自動擷取與 conflict detection、
Memory confirmation 問答 E2E、Confirmed Memory 語意相關性排序、Graph／Neptune
實際查詢、Prompt Registry、Model Router、cross-agent handoff、完整 Agent Trace 持久化、
Evaluation runner，以及 production RAG／Guardrails。

Staging RAG 程式路徑雖已存在，supplied Allowlist 尚未簽署、Human Review 未完成，也尚無可
驗證的 AWS／OpenSearch 環境。Staging 只有在 `RAG_REQUIRE_OWNER_SIGNATURE=false` 時可採
unsigned development override；`RAG_ALLOWLIST_EXPECTED_SHA256`、來源、Chunk、數量與完整
Allowlist 驗證仍不可略過。Override 永不構成 production 核准。

`contracts/schemas/tools/` 的 Core `ToolRequestV1`／`ToolResultV1` 已由受控
`create_event_candidate` adapter 使用；`HandoffEnvelopeV1` 與 legacy `ToolResponseV1` 仍是
未接入 executable path 的目標形狀。
