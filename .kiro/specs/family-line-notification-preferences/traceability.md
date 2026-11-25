# 需求追蹤

第一切片驗收日期：2026-10-15。完整證據與未完成條件見 [交付報告](../../../docs/project/family-line-notification-preferences-20261015.md)。

| 需求 | 實作 | 驗證與狀態 |
| --- | --- | --- |
| R1 本人與當前授權 | Core `family_notification_preference_service.py`、`family_notification_preference_repo.py` 與既有 `authorize_elder` | Unit、SQL／HTTP rollback：兩位家屬各自設定、跨 tenant／角色及 membership／關係／scope／同意／actor 失效拒絕，含 replay 重驗；已完成 |
| R2 嚴格輸入與交易 | Core schema／API、version migration、actor-scoped idempotency、最小 outbox；前端 `family-notifications.ts` | 非本人收件欄位拒絕、GET 無寫入、version 0／衝突、同 key 不跨 actor、重播；已完成 |
| R3 固定每日與保留舊設定 | Service 檢查 DAILY／Asia/Taipei／08:00；只有原本未開 LINE 的預設時間可在首次 opt-in 正規化 | 舊頻率／靜默／LINE-on NULL 時間不可啟用；停用保留 EMAIL 與其他偏好，SQL rollback 通過；已完成 |
| R4 收件綁定與可用狀態 | 僅讀取本人有效 LINE identity，驗證加密目的地與 feature readiness；GET 不呼叫 provider | OIDC-only、無綁定、錯誤密文、服務停用、可用目的地與離線 opt-out；已完成 |
| R5 家屬介面 | `/family/notifications`、雙語訊息、家屬導覽、focus／visibility／定時重讀與過期 request 防護 | 前端完整 844 項與後續定向 63 項回歸，正式 build／雙語 RWD／鍵盤／200% 放大，詳見報告；已完成 |
| R6 最小內容與報表範圍 | 沿用既有 `line_daily_notification` sender 與 recipient_scope；新 DTO／outbox 不含目的地或照護內容 | 既有 sender 定向測試、SQL recipient candidate 與 strict DTO／command 驗證；設定切片已完成，未發送真實 LINE |
| R7 真實設定、排程與收訊 | 本次不啟用旗標；`services/notification-worker` 仍為邊界 README | 未完成：需 Messaging API 設定／綁定、可執行 scheduler 部署及使用者指定收件人的真實收訊證據 |

Core 檔案位於 `services/core-api/app/{schemas,repositories,services,api}/`，測試為 `tests/unit/test_family_notification_preference.py`、`tests/unit/test_line_daily_notification.py` 與 `tests/integration/test_family_notification_preferences.py`。前端位於 `packages/frontend/src/`；契約與 examples 位於 `contracts/`。
