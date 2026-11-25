# 設計

使用 Python 3.12+ 標準函式庫的單次執行入口 `services/notification-worker/run_daily.py`，由外部 scheduler 在每日 08:00 呼叫；本切片不選雲端平台或常駐 worker framework。時區使用 IANA zoneinfo，缺少時區資料時 fail closed。

預設 preview；`--execute` 搭配 `NOTIFICATION_CORE_URL` 與 `NOTIFICATION_WORKER_HMAC_SECRET` 才可送出，issuer 預設 kinsun-local。只允許 HTTPS origin，HTTP 僅限 literal loopback／localhost；禁止 userinfo、query、fragment、非根路徑與 redirect。憑證不由 CLI 參數或 `.env` 自動讀取。每次 invocation 產生 correlation ID，各次 HTTP 重試沿用；30 秒 ksvc1 憑證每次重簽，避免把已使用的 nonce 拿去重播。

Core App Session issuance 明確拒絕 SYSTEM_SERVICE，因此不能用「先提供服務 session」當接通方式。通知端點改為專用 service dependency，驗證 notification-worker→core-api、method／path／body／correlation／TTL／持久化 nonce；server 設定綁定 SYSTEM_SERVICE actor，再沿用 live actor context resolver。沒有一般 App Session 或 fake-role fallback。沿用既有短效憑證格式，只開放非 production；正式機制待 Owner 選型，本次不延長 ADR 0009 的期限、不宣稱 production 核准。

最多 3 次請求，每次 socket timeout 10 秒；退避為 1／2 秒，Retry-After 最多等待 30 秒，超過則回報可稍後重試。HTTP 成功只處理回傳結果；PARTIAL_FAILURE 不在 worker 內立刻重送，保留 Core delivery 的 attempt／lease／retry-key 邊界，由監控與外部重跑處理。

輸入時間正規化為 UTC，前一個台灣日曆日作為來源日期。Core 仍是 tenant／身份、Published Report、Consent、Relationship、Preference、delivery claim 與 LINE retry key 的唯一執行者。Worker 不保存收件人或提供人工指定收件功能。

退出碼：0 dry-run／完成／無合格日報；1 HTTP／連線／回應錯誤；2 Core 部分失敗；64 配置或輸入錯誤；130 中斷。JSON 摘要以固定 reason code、總數與 correlation ID 提供追蹤；raw body 不落盤。
