# 家屬 LINE 每日通知設定 — 第一切片

授權方向：2026-10-13 使用者要求開始。每位已授權家屬可分別管理自己的通知；簽約身分不是通知權限。

- R1：僅 ACTIVE FAMILY_MEMBER 可讀寫本人、指定長者的設定；需現行 tenant membership、family_report:read、FAMILY_SHARING 同意及 REPORT_DAILY／REPORT_ALL 家屬關係。其他身分、跨範圍與失效一律不揭露。
- R2：只有 LINE 開關與 expected_version 可提交，收件人由 session 決定。預設關閉，不在 GET 建立資料。寫入須有版本與 Idempotency-Key，同交易保存稽核 outbox。
- R3：第一切片沿用 DAILY／Asia/Taipei／08:00。保留其他通路及偏好，不把未支援的既有週／月／靜默設定默默改成每日。
- R4：LINE 登入身份不等於推播收件目的地；區分未連結、已連結、需要重連。服務未開放或目的地不完整時，不得啟用通知；關閉不依賴 LINE provider 可用。
- R5：頁面雙語、可用鍵盤、手機／平板可讀。載入、未登入、無權限、空設定、可用、未連結、服務未開放、保存成功、衝突與錯誤均有明確狀態；撤權後清除舊資料。
- R6：日報收件範圍維持既有 recipient_scope，不因訂閱而擴大。通知只放更新提醒與登入連結，不放照護內容或 provider ID。
- R7：Messaging API credentials、實際排程部署與真實收訊需另有有效設定／操作證據，不能用合成結果標記完成。
