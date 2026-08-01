# ADR 0004：agent-runtime 併入 monorepo，並對齊既有工程慣例

- 狀態：Accepted
- 日期：2026-07-31
- 決策者：成員 C（Isaac）；repository 整合待 A（Harper）確認
- 相關文件：12｜實作計畫、環境、團隊分工與交付路線 v0.1 §7、§4.3
- 相關：[ADR 0001](0001-package-manager-uv.md)、[ADR 0003](0003-core-api-framework-and-schema-authority.md)
- 來源：`71bk/eldercare-ai-agent-platform` @ `d1334b9`

## 背景

成員 C 的 Agent／RAG／Graph 工作在獨立 repository（`71bk/eldercare-ai-agent-platform`）
完成了 M0 Foundation：FastAPI 服務、contract-first 的 Pydantic model 與 JSON Schema、
單輪 Orchestrator、Companion Agent、deterministic Safety Evaluator、Mock Model Provider，
以及 43 個測試。

文件 12 §7 要求採 Monorepo，理由是「讓 Contract、Frontend、Backend、Agent、IaC 與 Eval
在同一版本標籤下交付」。§25 進一步要求 Release Candidate 必須記錄 Git Tag、Contract、
Prompt、Model、Dataset 版本——跨兩個 repository 無法用單一 tag 表達。

`kinsun.ai` 本來就依文件 12 預留了 `services/agent-runtime/`（先前只有 `.gitkeep`）。

## 決策

### 1. 併入 monorepo，不保留獨立 repository 的開發

程式碼搬進 `services/agent-runtime/`，契約搬進 `contracts/schemas/{agent,tools}/` 與
`contracts/examples/`。原 repository 轉為 archive，不再開發。

採檔案搬移而非 `git merge`：來源只有兩個 commit，且檔案必須拆到 monorepo 的兩個不同
目錄（服務與契約），保留歷史的收益低於製造混亂的成本。

### 2. 套件管理改用 uv，per-service pyproject

來源使用 pip ＋ setuptools ＋ repository 根目錄單一 `pyproject.toml`。改為與 core-api
一致：`services/agent-runtime/pyproject.toml`、`[tool.uv] package = false`、
`uv.lock` 進版控（ADR 0001）。兩個服務不共用虛擬環境。

`referencing` 從傳遞依賴改為明列——測試直接 import 它。

### 3. Contract 命名對齊團隊規範

| 項目 | 來源 | 併入後 |
| --- | --- | --- |
| 檔名 | `agent-run-request.schema.json` | `AgentRunRequestV1.json` |
| `$id` | 相對檔名 | `https://kinsun.ai/contracts/schemas/agent/AgentRunRequestV1.json` |
| 跨檔 `$ref` | 相對路徑 | 指向 `$id` |
| invalid 範例 | 無 `_why_invalid` | 有 |
| 範例結構 | 裸 payload | `{"_why_invalid": ..., "data": {...}}` |

`data` 外層不只是格式統一：`scripts/validate_contracts.py` 直接讀 `["data"]`，
沒有這層會讓驗證器 KeyError 崩潰，連 core-api 既有的檢查都跑不完。

schema 的實質內容（properties、required、`additionalProperties`）一律未動。

### 4. `scripts/validate_contracts.py` 只做加法

新增 4 筆 `DATA_SCHEMA_FOR` 對應。`check_openapi()` 維持只驗 `core-api.v1.yaml`，
因為 agent-runtime 這次沒有產出 OpenAPI（見下節）。

## 這次刻意不做的事

> **後續補充**：本節的三項延後事項都已由 [ADR 0005](0005-agent-runtime-api-conventions.md)
> 處理完畢——路徑改為 `/api/v1/agent/runs`、採用 `SuccessEnvelope`／`ErrorEnvelope`、
> 產出 OpenAPI，兩項已知缺陷也一併修掉。以下保留原始記錄，說明搬遷當下為何不做。

### 不寫 agent-runtime 的 OpenAPI

兩件事未定案：

1. 路徑是 `/v1/agent/runs`，缺團隊慣例的 `/api` 前綴（AGENTS.md §8，core-api 已全部
   使用 `/api/v1/...`）。
2. 回應是裸 `AgentRunResponse`，不走 `SuccessEnvelope`／`ErrorEnvelope`（AGENTS.md §8.3）。

兩項都是破壞性變更，現在寫 OpenAPI 等於立刻要走 Deprecation 流程。

### 不修已知缺陷

搬遷 commit 不混入行為變更。以下兩項當時原樣保留：

- `orchestration/orchestrator.py` 的 `while True` 迴圈結尾有有條件 `break` 緊接無條件
  `break`，導致迴圈恆只執行一輪，`StepLimitError` 永遠不會觸發。step 上限實際上由 API
  層的前置檢查達成，不是由迴圈邏輯。
- `InvalidRequestError`／`StepLimitError` 未註冊 exception handler，若前置檢查被移除
  會變成 500 而非 422。

### 不動文件 10 的對齊

Agent Handoff（§15）與 Tool（§16）的 schema 與文件 10 差異很大，全部登記在
[`contracts/DIVERGENCE.md`](../../contracts/DIVERGENCE.md) 第九節，未靜默對齊任何一邊。

## 後果

### 正面

- 契約、服務與測試回到單一版本標籤下。
- agent-runtime 的 contract 一致性測試掃的是根目錄 `contracts/schemas/`，因此同時
  驗證 core-api 的 schema 是否合法 JSON Schema。刻意保留這個交叉守護。
- agent-runtime 測試不需資料庫、AWS 憑證或網路，是目前 repository 內最快的測試套件。

### 負面／待處理

- **三支 schema 描述的東西還不存在**：`HandoffEnvelopeV1`（有 model 但 orchestrator
  從未產生 handoff）、`ToolRequestV1`／`ToolResponseV1`（無 model、無使用）。這與
  AGENTS.md §8.2「尚未實作的 API 不寫進 contract」牴觸，待 A 裁定是移出或記錄為例外。
- agent-runtime 的契約**尚未對執行中的服務驗證過**。core-api 有
  `scripts/verify_contract_live.py`，但它寫死 `from app.main import create_app` 且需要
  `DATABASE_URL`，無法直接沿用。需要另一支。（已由 ADR 0005 補上
  `scripts/verify_agent_contract_live.py`。）
- CI 之後要跑兩份 `uv sync`。
- `MAX_TOOL_ROUNDS`／`MAX_TOTAL_TOOLS`／`MAX_REWRITE` 已宣告但無程式使用。

## 待決策

- Repository 整合本身需 A（Integration Owner）知悉。
- `/api` 前綴與 envelope：已由 [ADR 0005](0005-agent-runtime-api-conventions.md) 決定。
- `HandoffEnvelopeV1`、`ToolRequestV1`、`ToolResponseV1` 與 AGENTS.md §8.2 的牴觸：
  決定保留於 `contracts/`，並在 `contracts/README.md` 記為明示例外；Tool 兩支已依
  文件 10 §16 補齊安全欄位（ADR 0005）。
