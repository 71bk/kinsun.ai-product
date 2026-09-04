# ADR 0021：採用 PostgreSQL lease 與固定 HTTPS ingress 完成 Outbox 傳遞

- 狀態：Accepted
- 日期：2026-09-04
- 關聯：[ADR 0019](0019-retire-aws-cdk-deployment-profile.md)、
  [Outbox Delivery Runbook](../runbooks/outbox-delivery.md)

## 背景

Core 已在業務交易內寫入 `outbox_event`，也已有嚴格 event envelope 與 consumer
idempotency，但舊 relay 會在持有資料庫交易與 row lock 時呼叫 publisher。程序若在
`PUBLISHING` 後中止，資料列沒有 owner、lease expiry 或安全 recovery 路徑；重試也沒有
持久化排程與可操作的 dead-letter metadata。

目前 hosting provider 尚未定案。依 ADR 0019，repository 不應重新假設 EventBridge、SQS
或其他供應商資源已存在，但 Wave 2 需要一個能實際部署、又不綁定特定雲端的可靠傳遞邊界。

## 決策

1. PostgreSQL `outbox_event` 是 publisher delivery control plane，也是 publisher DLQ 的
   authoritative record。它保存 next attempt、lease identity/expiry、最後 dead-letter 原因與
   redrive history。
2. Worker 以 `FOR UPDATE SKIP LOCKED` 在短交易內 claim 單一事件，commit 後才呼叫外部
   publisher，再以 lease token 條件式結算。外部 I/O 不持有資料庫 row lock。
3. 過期 `PUBLISHING` lease 自動回到 `FAILED`，達上限則進 `DEAD_LETTER`。重試採有上限的
   exponential backoff。
4. 傳遞語意明確為 at-least-once。HTTP ingress 必須在事件已 durable enqueue 後才回傳 2xx，
   並以 `Idempotency-Key`／`event_id` 去重。
5. 第一個 production-capable adapter 是固定 HTTPS URL 加 bearer credential；不跟隨 redirect，
   也不把 response body 或 raw exception 存入 outbox。
6. Consumer 使用 `EventConsumerWorker`：先 commit domain/idempotency transaction，之後才
   acknowledge；retry 不 acknowledge；dead-letter durable handoff 完成後才 acknowledge。
7. 實際 queue receiver、DLQ storage 與監控資源由選定的 hosting deployment adapter 實作
   `QueueSettlement`。選擇特定供應商時仍須另立 ADR 與部署證據。

## 結果

- Worker crash、DB finalize failure 或 acknowledgement loss 可能造成 duplicate delivery；
  consumer idempotency 會阻止 handler 重複生效。
- 停機超過 lease 時間不會永久卡住 `PUBLISHING`。
- 單筆 redrive 保留原 dead-letter 原因與時間，且 relay／consumer 仍重新檢查 consent 與
  deletion tombstone，避免 replay 復活已撤回資料。
- Repository 具備完整 provider-neutral runtime 與測試介面，但不代表任何外部 ingress、queue、
  alarm 或 worker process 已在 production 部署。

## 未採用方案

- 在資料庫交易內同步 publish：外部延遲會延長 lock，且 crash recovery 不完整。
- 宣稱 exactly-once：跨 PostgreSQL 與外部 transport 無共同交易，這個承諾不成立。
- 直接加入 AWS queue/IaC：與 ADR 0019 的 provider owner 決策不符。
