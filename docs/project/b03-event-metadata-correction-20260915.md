# B03 事件類型／時間修正 — 2026-09-15

## 範圍與交付

US-B03 原先 CORRECT 僅版本化 payload，event_type／event_time 無法修正。
本切片在 `feat/wave2-backend`／`D:/Hackthon/kinsun-backend` 補上 Core 寫入與稽核；
原前端 worktree 的檔案、分支、服務與 Supabase 均未變動。

POST `/api/v1/elders/{elder_id}/care-events/{event_id}/review`：

```json
{
  "decision": "CORRECT",
  "reason_code": "EVENT_MISCLASSIFIED",
  "expected_version": 1,
  "corrected_payload": {"text": "Synthetic corrected record"},
  "corrected_event_type": "SLEEP",
  "corrected_event_time": "2026-09-15T08:00:00+08:00"
}
```

| 欄位／操作 | 行為 |
| --- | --- |
| corrected_payload | CORRECT 仍必填 object；沿用 restricted-key gate |
| corrected_event_type | 選填 canonical CareEventType；省略保留，null／未知類型拒絕 |
| corrected_event_time | 省略保留；null 清除；時間必須含 Z 或 UTC offset |
| 其他 decision | VERIFY／REJECT／EXCLUDE 不接受新欄位，含 explicit null 也拒絕 |
| 回應與 outbox | 現有形狀不變；回應既有欄位提供修正後 type/time |
| 重送 | 舊請求 fingerprint 不變；省略時間與清除時間為不同 payload |

只有 CANDIDATE／NEEDS_REVIEW 可覆核。先鎖定同 tenant／elder 的事件並刷新資料，
等待鎖後重驗 elder scope；版本衝突或已正式事件回 409。每次成功 snapshot replay 也先驗目前授權。
CORRECT 保留舊 payload version、新 version 的 supersedes 關係，另在同一 ReviewDecision
保存 before/after event type/time、version、reviewer 與時間。私有 Memory／action proposal
不沿用到修正版；相關摘要標記 STALE。上述狀態與 outbox／idempotency 在同交易提交／回滾。

## Migration 與發布順序

- 新 head `f4b6d8e0a213`，前一版 `e3a5c7d9f102`。
- 只在 review_decision 加四個 nullable metadata 欄位與配對 check；既有與非 CORRECT row
  保留 NULL，不回填猜測歷史。既有 SELECT／INSERT runtime grant 足以使用新增欄位。
- **先由 migration principal 套用 additive upgrade，再啟動新版 Core。** 新 ORM 讀寫會用到新欄位。
- 回復 application 可保留 additive 欄位；downgrade 僅在 disposable DB 驗證，會丟失新 audit
  metadata，不得用於共享 Supabase rollback。
- 本次未讀取／套用 Supabase migration；未建立本機 PostgreSQL 或 Docker。

## 驗證與 traceability

| 驗證 | 本機結果／證據 |
| --- | --- |
| Core unit | 1,430 passed；其中新增 14 個 metadata／contract／idempotency regression |
| Core lint／format | 全部通過 |
| static contracts | all contract checks passed；新增 2 valid／3 invalid examples |
| CI impact／gate／telemetry tests | 26 passed |
| Alembic graph | 單一 head f4b6d8e0a213 |
| PostgreSQL／migration lifecycle | 本機未執行；使用 PR CI disposable PostgreSQL 驗證，結果待補 |

第一輪 [CI 34941061567](https://github.com/71bk/kinsun.ai-product/actions/runs/34941061567)
的新增 metadata migration roundtrip 通過；另兩個既有 lifecycle assertion 因 `_HEAD_REVISION`
未同步而失敗（19 passed／2 failed），已修正預期 head。HTTP integration 當輪未執行。

新增 DB regression 包含修正／清除／省略時間的 audit 保存、同 key replay／payload conflict、
已正式事件拒絕、assignment expiry、跨 elder／tenant、非授權角色、不同 key 並行只有一位成功、
outbox 插入後故障全部回滾與 retry。Migration regression 覆蓋前一版→新 head→前一版→head、
nullable 欄位與 check 存在。測試身分注入，資料為 synthetic，並非真實登入或 Browser E2E。

US-B03 的前端輸入與修正歷史瀏覽、陪伴需求訊號重算、離線評估用途授權不在本切片；
已正式事件仍不可再次覆核。B03／Wave 2 整體仍未結案；下一個後端缺口是 B04 來源篩選。
