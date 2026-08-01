# ADR 0005：agent-runtime 對外 API 採 `/api/v1` 與統一 Envelope

- 狀態：Accepted
- 日期：2026-07-31
- 決策者：成員 C（Isaac）
- 相關文件：10｜API、Event、Tool 與 Data Contracts v0.1 §4、§15、§16
- 相關：[ADR 0004](0004-agent-runtime-into-monorepo.md)
- 取代：ADR 0004「這次刻意不做的事」中的兩項延後決策

## 背景

ADR 0004 把 agent-runtime 併入 monorepo 時，刻意保留了兩個與團隊慣例不符的地方，
因為兩者都是破壞性變更，當時未定案：

1. 路徑是 `/v1/agent/runs`，缺 AGENTS.md §8 要求的 `/api` 前綴。core-api 已全部使用
   `/api/v1/...`。
2. 回應是裸 `AgentRunResponse`，不走 AGENTS.md §8.3 要求的
   `SuccessEnvelope`／`ErrorEnvelope`。

沒有任何 Consumer 已接上這個 endpoint，所以現在改的成本是零；一旦 D 的語音端接上去，
就要走 Deprecation 流程。

## 決策

### 1. 路徑改為 `/api/v1/agent/runs`

與 core-api 一致。`/health` 維持在根層、不加前綴，也與 core-api 一致。

### 2. 採用與 core-api 相同的 Envelope

成功：`{"data": <payload>, "meta": {"correlation_id", "timestamp"}}`
錯誤：`{"error": {"code", "message", "correlation_id", "details"}}`

`agent_runtime/core/envelopes.py` 逐欄對應 `core-api/app/core/envelopes.py`，
JSON Schema 直接**共用** `contracts/schemas/common/` 的 `ResponseMetaV1` 與
`ErrorEnvelopeV1`，不另建一份。兩個服務各自發明一套「統一格式」是這裡要避免的失敗。

這個決定同時解掉一個實際問題：`scripts/validate_contracts.py` 直接讀 example 的
`["data"]`，本來就假設了 envelope。不採用的話得為 agent-runtime 在共用腳本開特例。

### 3. `RequestValidationError` 也轉成 ErrorEnvelope

**這一項與 core-api 目前的行為不同，是刻意的。** core-api 只註冊了
`DomainException`、`NoAuthenticatorConfiguredError` 與 catch-all，所以 pydantic 的
body 驗證失敗會回 FastAPI 預設的 `{"detail": [...]}`。

對 agent-runtime 而言 schema 拒絕是**最常見**的錯誤回應，讓它成為唯一逃出 envelope
規則的形狀說不過去。因此多註冊一個 handler。

`details[].reason` 帶的是 pydantic 的 error type（`extra_forbidden`、`missing`…），
**不帶被拒絕的值**——request body 是長者逐字稿，AGENTS.md §8.1 禁止回填敏感原值。
這條由 `test_validation_details_do_not_echo_rejected_input` 與 live verifier 兩處守著。

建議 core-api 後續也比照，但那是 B 的範圍，本 ADR 不代為決定。

### 4. 產出 OpenAPI，並讓驗證器掃描整個目錄

新增 `contracts/openapi/agent-runtime.v1.yaml`（2 個 path）。

`scripts/validate_contracts.py` 的 `check_openapi()` 原本寫死只驗 `core-api.v1.yaml`，
改為掃 `openapi/*.yaml`。這比修檔名重要：寫死的話，第二份文件會被**靜默跳過**，
gate 保持綠燈但契約其實沒被檢查過——比直接失敗更糟。

### 5. 新增 `scripts/verify_agent_contract_live.py`

AGENTS.md §8.2 要求新 endpoint 同步加 live 驗證。core-api 那支寫死
`from app.main import create_app` 且需要 `DATABASE_URL`，無法沿用。

新腳本檢查 6 件事：`/health`、正常回合、**安全阻擋回合仍是 200 且 envelope 相同**、
schema 拒絕的 422、超過 step 上限的 422（走 domain handler 而非 catch-all）、
以及錯誤回應不回填被拒絕的輸入。因為走 Mock Provider，不需資料庫、憑證或網路。

## 一併修掉的既有缺陷

ADR 0004 記錄了兩項刻意保留的缺陷，都在這次修掉，因為它們與本決策直接相關：

- **Orchestrator 的假迴圈**：`while True` 結尾有一個有條件 `break` 緊接一個無條件
  `break`，導致迴圈恆只跑一輪、`StepLimitError` 永遠不會觸發，step 上限實際上是靠 API
  層的重複前置檢查達成的。改為明確的單步執行並保留 `LoopController` 檢查；
  `stop_conditions.is_terminal_decision()` 一併移除——它讀作 `decision != ALLOW`，
  對停止條件而言語意是反的（ALLOW 才是成功終止態），應該與真正需要它的多步迴圈一起設計。
- **例外未註冊 handler**：`InvalidRequestError`／`StepLimitError` 會掉進 catch-all
  變成 500。註冊 `DomainError` handler 後，兩者都是 422。

第二項是第一項的前提：API 層的重複前置檢查一拿掉，沒有 handler 就會漏成 500。
`test_max_steps_over_system_limit_rejected_as_error_envelope` 就是守這件事。

## 後果

- `POST /v1/agent/runs` 不再存在。沒有 Consumer 受影響（無人接上）。
- agent-runtime 的契約現在有 live 驗證，不再只是散文。
- 未實作的 `HandoffEnvelopeV1`、`ToolRequestV1`、`ToolResponseV1` **刻意不寫進 OpenAPI**，
  避免把不存在的東西描述成可呼叫。它們與 AGENTS.md §8.2 的牴觸仍然存在，
  記錄在 `contracts/README.md`。
- Tool schema 已依文件 10 §16 補齊 `consent_version`、`policy_version`、
  `idempotency_key`、`expected_resource_version`、`retryable`、`source_refs[]`、
  `redactions[]`、`resource_id`、`resource_version`。趁沒有實作時對齊是免費的；
  等 Tool 執行引擎寫完再補就是破壞性變更。
- `AgentRunResponseV1` 本身仍與文件 10 §15.2 的 Handoff Result 差距很大
  （缺 `source_ids[]`、`tool_calls[]`、`token_usage`、`model_id`、`prompt_version` 等），
  `ResultStatus` 也只有 4 個值。這些留在 `contracts/DIVERGENCE.md` 第九節，未收斂。
