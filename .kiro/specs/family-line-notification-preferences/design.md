# 設計

GET／PUT `/api/v1/family/elders/{elder_id}/line-notification-preference`。PUT 僅接受 `line_enabled`、`expected_version`；本人身份由 Core session 取得。

使用既有 notification_preference，新增 integer version，維持 actor＋elder 唯一。無 row 的 GET 為關閉／version 0。寫入先驗權限、鎖 tenant 內 Elder、重驗同意與關係，再處理 scoped idempotency 與版本；避免兩個初次寫入同時建立資料。版本過期為 409，拒絕為 404。

設定權限沿用家屬現有報表讀取範圍，僅允許該本人決定是否接收相同範圍的通知；不增加報表權限、不改收件範圍、不替其他家屬設定。

回傳只有本人設定、固定每日規則及安全的 LINE readiness 狀態，不包含 actor ID、LINE user ID、ciphertext、digest、credential、照護內容或完整 delivery error。

`/family/notifications` 沿用 family surface。讀取 current elder 的設定，保存後重新 GET；前景／可見狀態重驗，403／404／401 時清除。綁定說明沿用官方帳號的一次性「連結帳號」流程，不拿 LINE Login 當 Messaging API 收件人。

本切片不啟用 feature flags 或發送真實 LINE；外部排程仍使用既有每日 scheduler boundary。
