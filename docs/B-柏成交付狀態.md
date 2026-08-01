# B（柏成）Domain Backend／Security 交付狀態

- 更新日期：2026-08-01
- 角色：B — Domain Backend／Security Owner
- 範圍：Python Core API、Aurora schema、Domain State、RBAC + ABAC、Consent、Idempotency、Transactional Outbox，以及 Event producer／consumer foundation。

## 已完成

### Domain 與 API

- Elder：授權範圍查詢、單筆讀取、長者本人 actor 綁定與不可探測的 404。
- Consent：依 Purpose 分離的建立、查詢、撤回；撤回立即阻止未來處理，並建立 deletion workflow。
- Voice Session metadata：建立、查詢、受控狀態轉移、取消與完成；每次操作重新檢查 Consent。Audio／WebSocket transport 明確標示 `NOT_CONFIGURED`。
- Care Event：只能先建立 Candidate；覆核後才能成為 Verified，並支援 Correct／Reject／Exclude。
- Memory：Candidate、Confirm／Reject／Defer、Update、Delete；只有確認且未撤回的 Active Memory 能進正式讀取。
- Daily Summary：只接受 Verified Event 作為來源；支援 Draft、Review、Rebuild 與 stale 標記。
- Family Report：Draft、Publish、Withdraw；家屬端只可讀取符合 relationship scope 且仍為 `PUBLISHED` 的版本。
- Assignment：建立、查詢、確認、開始與完成；檢查 tenant、care unit、worker membership、時間範圍與用途 scope。
- Tool：Allowlist、schema、第二次 Core 授權、Consent／Policy version、Idempotency 與 restricted-data audit protection。
- Deletion：撤回同意時建立 deletion request／store job；具顯式 request/item state machine、tenant-scoped hash Tombstone 與 transactional outbox。Aurora `MEMORY` 已可在可信 policy／legal-hold gate 後清除內容；未配置的外部 store 會維持 `PARTIAL_FAILED`，不會偽造完成。

### 資料與事件安全

- 新 Alembic revisions 只做增量變更；凍結的 v0.1 baseline SQL 與 checksum 未修改。
- Outbox 支援 `SUPPRESSED` 與 terminal `DEAD_LETTER`；relay 在發布前重查 Consent、tenant scope、aggregate state 與通用 hash Tombstone，並將 typed publisher failure 依 `retryable` 與 attempt limit 決定 `FAILED` 重試或 `DEAD_LETTER`。
- Domain Event 使用嚴格 envelope；payload 遞迴拒絕 Transcript、Audio、Prompt、Secret、Token。
- Consumer 以 `consumer name + event_id` 做交易內 idempotency；Replay 不重做副作用，失效 Consent 或 tombstone 事件會被抑制。Handler／processing failure 只暴露穩定 `reason_code`，以 `RETRY`／`DEAD_LETTER` disposition 交由未來 queue adapter 處理，不保存原始 exception message。
- 正式 EventBridge／每個 Consumer 專屬 SQS／DLQ／Redrive 尚未綁定，避免在 AWS Region、Account、IaC 未定案前偷偷鎖定技術決策。

### Contract 與可重現 Demo

- OpenAPI 覆蓋目前 runtime 的 44 個 operations。
- JSON Schema 使用 `additionalProperties: false`；包含正常與必須被拒絕的範例。
- 已建立 AsyncAPI 與 Domain Event Envelope；validator 會檢查 JSON Schema、OpenAPI、AsyncAPI 及 examples。
- Live verifier 會比對 runtime operation parity，並驗證 protected GET 在未配置 authenticator 時 fail closed。
- `scripts/reset_demo.ps1 -ConfirmLocalReset` 可從空 DB 套用全部 migration 並載入固定 Synthetic Demo Seed。
- Seed 包含三位合成人物、Active／Revoked Consent、Confirmed Assignment、Verified Event、READY／NEEDS_REVIEW Summary、Confirmed Memory、Draft／Published／Withdrawn Report、成功／失敗通知、失敗 projection 與待發布 outbox。

## 本次整理已驗證

```text
Unit tests:          369 passed
Ruff check:          All checks passed
Ruff format:         149 files already formatted
Static contracts:    all contract checks passed (41 OpenAPI paths, 1 AsyncAPI channel)
Docker Compose config: passed
Git diff check:      passed
```

Integration tests、runtime live contract verifier 與 migration reset／Synthetic Seed
有先前執行紀錄，但本次整理未重跑，因此不列為本次驗證結果。原因是尚未安全確認
`TEST_DATABASE_URL` 只指向 `kinsun_test`，且未確認 live verifier 所需的本機服務正在執行。
在確認環境後，仍需依下方指令重跑並記錄結果。

## 需要 Owner／其他工作流決策，不可由 B 假裝完成

- Cognito User Pool／JWT verifier、AWS Region、Account／Environment 與 IaC 工具。
- EventBridge、SQS、DLQ、Redrive 的實際 AWS resource 與 deployment binding。
- Retention、Legal Hold、Backup Restore、外部 store 刪除驗證與 Offboarding 正式政策；現有 Core state machine 只接受可信 policy decision 且 fail closed，不能代替正式政策核准。
- D：WebSocket audio、ASR low-confidence confirm、TTS 與 voice performance。
- C：Agent Runtime／Handoff、RAG、Graph／OpenSearch projection 實作。
- E：LINE／Email delivery adapter、雲端部署、Observability 與 CI quality gate。

上述未決項目已保留 fail-closed 或 provider-neutral 邊界；目前不得描述成已部署或已可在 AWS 正式運行。

## 本機重跑

```powershell
docker compose up -d postgres
.\scripts\reset_demo.ps1 -ConfirmLocalReset

cd services/core-api
..\..\.venv\Scripts\python.exe -m pytest tests/unit
..\..\.venv\Scripts\python.exe -m pytest tests/integration
..\..\.venv\Scripts\python.exe -m ruff check .
..\..\.venv\Scripts\python.exe -m ruff format --check .

cd ..\..
.\.venv\Scripts\python.exe scripts/validate_contracts.py contracts
.\.venv\Scripts\python.exe scripts/verify_contract_live.py contracts
```

若本機 5432 已被其他 PostgreSQL 使用，可在不改 `.env.example` 的前提下，於未版控的 `.env` 將 `POSTGRES_PORT`、`DATABASE_URL` 與 `TEST_DATABASE_URL` 改為同一個可用本機埠；目前工作環境使用 15432。
