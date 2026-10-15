# AGENTS.md — contracts

本檔補充根目錄 [`AGENTS.md`](../AGENTS.md) §8，涵蓋 `contracts/` 與 contract 驗證腳本；根目錄規則一律適用，
衝突時以根目錄為準。目錄內容概覽見 [`README.md`](README.md)。

## 目前狀態

- `contracts/` **以目前實作為準，不是以文件 10 為準**；差異追蹤在 [`DIVERGENCE.md`](DIVERGENCE.md)。
  它是說明而非 executable truth，局部摘要可能落後；改動前後都跑 validator。消除或新增差異時同步更新它。
- path／operation 數量以 `scripts/validate_contracts.py` 與 live verifier 的當次輸出為準，不手動維護清單
  （2026-10-15 實測 Core OpenAPI 110 paths／121 operations、`info.version` 1.13.0）。FastAPI 自動掛的
  `/docs`、`/docs/oauth2-redirect`、`/openapi.json`、`/redoc` 不登記。
- `openapi/core-api.v1.yaml` 副檔名是 `.yaml`，**內容是 JSON**（由 `scripts/export_core_openapi.py` 產生）；
  用 YAML 縮排 grep 會得到 0。
- OpenAPI 有人工補充的 description／response；全量 exporter 可能覆蓋並重排無關 paths。新增 endpoint 時檢查
  semantic diff，只納入本次 operation。

## 目錄與命名

```
contracts/
├── openapi/<service>.v<major>.yaml   REST，一個服務一份
├── asyncapi/<service>.v<major>.yaml  Domain Event
├── schemas/{common,domain,events,rag,tools,agent}/
└── examples/{valid,invalid}/
```

- Schema 檔名與 `title` 為 PascalCase＋版本（`ElderSummaryV1.json`）。
- JSON Schema `$id` 用絕對 URI `https://kinsun.ai/contracts/schemas/<dir>/<Name>.json`，跨檔 `$ref` 指 `$id`。
  OpenAPI 外部 response schema 則沿用 exporter／validator 的 `../schemas/...` 文件相對路徑；兩套不混用。
- JSON 欄位 snake_case；REST 路徑複數名詞、kebab-case；時間 ISO 8601 UTC；ID 一律 UUID，不暴露流水號。

## 硬性規則

- **`additionalProperties: false`**，否則多餘欄位洩漏也測不出來。
- **enum 必須與 `eldercare_ai` schema 一致**（PG ENUM label 或 CHECK）；比 DB 寬鬆會延到 INSERT 才爆。
- **分頁只能用 opaque cursor**，不得有 `offset`、`page_number` 或 `total`（`total` 洩漏授權範圍外數量）。
- **不得包含 Restricted Data**：逐字稿、ASR 信心值、內部筆記、未覆核事件、診斷式分數、Secret、完整 Prompt。
  家屬版對照根目錄 §4 零容忍清單。錯誤訊息不得回填敏感的被拒原值。
- `security` 區塊描述目前 executable authentication；verifier 尚未實作時在 description 明說。
- HTTP 拒絕狀態依 `services/core-api/app/api/error_handlers.py` 實際映射（`AuthorizationDeniedError` → 404）。

## 何時新增或更新

- **必須新增**：新 endpoint／Domain Event／Agent Tool 實作完成後、合併前；既有 endpoint 新增欄位、狀態碼或
  改變分頁／篩選；新增 enum 值（同時確認 baseline／migration 對齊）。
- **不得新增**：尚未實作的 API（`contracts/` 的語意是「這個可以現在打」；設計放 `docs/` 或 Kiro spec）。
  不為讓驗證通過而放寬 schema；不符時先判斷哪一邊錯。例外須在 README 明列。
- **相容變更**（新增選填欄位、enum 值、放寬長度）直接改同一 major；**破壞性變更**（刪／改欄位名或型別、
  收緊 enum、改 envelope）走 Deprecation、新 major，Consumer 先支援新舊版本，Producer 才切換。

流程：確認實作可實際呼叫 → 改 `schemas/` → `openapi/` 以 `$ref` 指向 schema（不內嵌重複）→ 補
`examples/valid/` 與 `examples/invalid/` → 三支驗證全過 → 必要時更新 `DIVERGENCE.md`。

## 範例

- `examples/valid/` 至少一個；`examples/invalid/` 至少一個且**頂層帶 `_why_invalid`**。invalid 範例通過驗證＝
  schema 太寬鬆，視同測試失敗。
- 一般 domain example mapping 取 envelope 的 `data` 驗證；invalid example 也要沿用 `data`／`meta` 包裝，
  裸 payload 造成的 `KeyError: data` 不是 schema rejection。

## 驗證（在 repository 根目錄執行）

```powershell
uv run --with pyyaml --with jsonschema --with referencing python scripts/validate_contracts.py contracts
uv run --project services/core-api --with pyyaml --with jsonschema --with referencing python scripts/verify_contract_live.py contracts
uv run --project services/agent-runtime --with pyyaml --with jsonschema --with referencing python scripts/verify_agent_contract_live.py contracts
```

- `validate_contracts.py`：schema 與範例自我一致性（掃 `contracts/openapi/` 全部）。
- `verify_contract_live.py`：以 `httpx.ASGITransport` 就地 `create_app()` 驗 Core；`/ready` 依賴 DB，使用
  repository `.env` 的 `DATABASE_URL` 或 CI disposable DB，**不要為此啟動本機 PostgreSQL**。DB 不可用時，
  不要把 `/ready` 失敗寫成 contract regression。
- `verify_agent_contract_live.py`：驗 Agent Runtime，不需資料庫、憑證或網路。
- 沒跑過 live verifier 的 contract 不算數；新增 endpoint 時同步在對應 verifier 加檢查。
