# Transactional Outbox Delivery Runbook

## 適用範圍與不變條件

本 runbook 操作 Core 的 publisher control plane。正式事實仍在 PostgreSQL；Graph、通知或其他
downstream 失敗不得回滾 Core transaction。傳遞為 at-least-once，下游必須以 `event_id` 去重。

禁止 bulk redrive、直接把狀態改成 `PUBLISHED`，或修改 event business fields。每次 redrive 前都要
確認事件類型、失敗原因、downstream 修復狀態、consent 與 deletion/tombstone 狀態。

## 啟用前檢查

1. 執行 migration 到 `b8d0f2a4c6e7` 或更新的 head。
   在 Core API working directory 以
   `uv run python -m scripts.verify_outbox_delivery_schema` 做只讀核對。
   若環境使用 `kinsun_app` runtime principal，須讓 migration job 重新 reconcile column grants。
2. 部署方提供固定 HTTPS ingress。只有事件已 durable enqueue 後才可回 2xx；需接受
   `Idempotency-Key: <event_id>` 並去重，不得 redirect。
3. 設定 runtime-only secret，且不要寫入 repository 或 log：

```text
OUTBOX_WORKER_ENABLED=true
OUTBOX_PUBLISHER_MODE=https
OUTBOX_PUBLISH_URL=https://<owner-provided-ingress>/<fixed-path>
OUTBOX_PUBLISH_BEARER_TOKEN=<at-least-32-byte-secret>
OUTBOX_PUBLISH_TIMEOUT_SECONDS=10
OUTBOX_LEASE_SECONDS=30
OUTBOX_MAX_ATTEMPTS=10
OUTBOX_RETRY_BASE_SECONDS=2
OUTBOX_RETRY_MAX_SECONDS=300
```

`OUTBOX_LEASE_SECONDS` 必須大於 publish timeout。啟用前須由部署方完成 ingress auth、durability、
duplicate delivery、worker restart 與 downstream DLQ smoke test。

## 啟動與單次驗證

在 `services/core-api` 的 runtime image／working directory 執行：

```powershell
uv run python -m app.events.worker --once
uv run python -m app.events.worker
```

第一個命令做一個 bounded pass；第二個持續執行。正常 rolling restart 不需先清 lease；未完成的
lease 到期後會自動恢復。

## 監控查詢

以下查詢只讀且不輸出 payload：

```sql
SELECT delivery_status, count(*)
FROM eldercare_ai.outbox_event
GROUP BY delivery_status;

SELECT count(*) AS unpublished_count,
       extract(epoch FROM now() - min(created_at)) AS oldest_age_seconds
FROM eldercare_ai.outbox_event
WHERE delivery_status IN ('PENDING', 'FAILED', 'PUBLISHING');

SELECT event_id, event_type, attempt_count, last_error,
       last_dead_lettered_at, redrive_count
FROM eldercare_ai.outbox_event
WHERE delivery_status = 'DEAD_LETTER'
ORDER BY last_dead_lettered_at
LIMIT 100;
```

最低告警條件由部署 owner 綁定到監控系統：dead-letter count 大於 0、oldest unpublished age 超過
5 分鐘、expired `PUBLISHING` 持續成長、publish retry rate 或 consumer retry rate 異常上升。

## 故障處理

- `PUBLISHER_DEPENDENCY_TIMEOUT`：確認 ingress 可用且確實 durable；修復後等待 bounded retry。
- `PUBLISHER_SCHEMA_REJECTED`：停止盲目 retry，檢查 receiver 支援的 event major version。
- `PUBLISHER_LEASE_EXPIRED`：確認 worker restart／timeout；若持續發生，檢查 lease 是否大於 transport
  timeout，以及是否有多個版本使用不相容設定。
- `DEAD_LETTER`：先修復根因，再逐筆 redrive。不要刪除 outbox row。
- backlog 上升：保留 outbox，必要時暫停新增非必要 async producer；不得用直接狀態更新跳過傳遞。

## 單筆 Redrive

先用上方只讀查詢完成審核，再執行：

```powershell
uv run python -m app.events.worker --redrive-event-id <event-uuid>
```

命令只接受目前為 `DEAD_LETTER` 的單一 `event_id`，會重設 attempt counter 並增加
`redrive_count`；原本的 `last_dead_letter_*` 仍保留。Relay 與 consumer 在重放時再次做 consent、
tombstone 與 aggregate status suppression。

## Rollback

應用回滾時先停用 worker，再部署舊程式。不要在仍有 worker 執行時 downgrade migration。若確實要
downgrade，migration 會把當下 `PUBLISHING` 轉成 `FAILED`，但會失去 lease、retry schedule 與
redrive metadata；先保存只含 event ID／狀態／原因的稽核證據並取得 owner 核准。
