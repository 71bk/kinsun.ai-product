# LINE Daily Notification Scheduler Boundary

目前可執行的通知核心位於 `services/core-api`；本目錄仍不選定 Worker framework，也不宣稱 AWS
Scheduler、SQS 或 DLQ 已部署。排程介面的單一來源是
[`config/line/daily-family-report-notification-v1.json`](../../config/line/daily-family-report-notification-v1.json)。

外部 Scheduler 必須：

- 每日 `08:00 Asia/Taipei` 以該 tenant 的 `SYSTEM_SERVICE` 身分呼叫
  `POST /api/v1/internal/notification-jobs/line-daily`。
- 將實際預定時間填入 `scheduled_for`；retry／misfire 必須沿用同一值，不可改成 retry 當下時間。
- 不得在排程 payload 放 `elder_id`、`report_id`、LINE user ID、報表內容或其他個資。
- 只有收到 2xx 才可視為 job 已被 Core 處理；`PARTIAL_FAILURE` 仍需由 Delivery 狀態與告警追蹤。

範例輸入：

```json
{
  "schema_version": "1.0",
  "job_name": "line-daily-family-report",
  "scheduled_for": "2026-08-02T08:00:00+08:00",
  "timezone": "Asia/Taipei"
}
```

Core 會自行將來源期間推算為 `2026-08-01`，重新驗證 Published Report、Consent、Relationship、
Share Scope、Preference 與加密 LINE destination，再以穩定 retry key 發送最小通知。
