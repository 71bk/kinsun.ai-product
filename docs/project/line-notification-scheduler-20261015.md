# LINE 通知排程入口

日期：2026-10-15。使用者核准下一階段第 1 項，先以合成資料完成。這是單次可執行入口，沒有自行安裝每天觸發的 scheduler，也未部署雲端或發送真實 LINE。

## 已完成

- `services/notification-worker/run_daily.py`，Python 3.12+ 標準函式庫入口，讀取既有 LINE schedule config，明確要求含 offset、台灣時間精確 08:00 的 `scheduled_for`；UTC 正規化，retry／跨日補跑不換工作時間。
- 預設 dry-run：不讀憑證、不連網、不連 DB。只有 `--execute` 才呼叫既有 Core job；不接受 role／tenant／elder／report／收件人參數，不直接呼叫 LINE。
- 只允許受信任 HTTPS origin，HTTP 限 literal loopback／localhost；禁止 userinfo／query／fragment／非根路徑及 redirect，避免把憑證轉送到其他位置。
- 408／429／5xx、timeout／連線錯誤最多 3 次請求，沿用同一 payload／correlation ID；退避與 Retry-After 有上限，過長延遲交給外部稍後執行。不宣稱 socket timeout 是整個工作的 wall-clock deadline。
- 成功 HTTP 還需比對 schedule、前一日來源、schema／counts／deliveries。PARTIAL_FAILURE 回 code 2，不把 2xx 當作全數成功，不在入口內立即重送。
- stdout 單行 JSON，含固定 outcome／reason code、attempts、counts 與 correlation ID，不含憑證、個案／報表／收件人 ID、provider body 或例外原文。無法確定的錯誤欄位回 null，不宣稱中斷時尚未送出。SIGINT／SIGTERM 會停止後續 retry，已被 Core 接收的工作可能仍完成。

## 修正服務身分缺口

原通知端點要求 SYSTEM_SERVICE，然而正常 App Session issuance 明確拒絕 SYSTEM_SERVICE；不能把「提供一個服務 App Session」當作可行的正式接線方式，也不能靠 fake auth 達成。

本次改為專用 `require_notification_service_actor`，沿用既有 ksvc1 短效服務憑證格式。Worker 每次 HTTP request 簽發新 30 秒 nonce；Core 驗證 notification-worker→core-api、method／path／body hash／correlation／TTL，再使用既有 PostgreSQL nonce store 持久化防重播。相同工作重試使用不同 credential，Core 的 delivery claim／LINE retry key 仍處理通知防重。

Core 從 server 設定的 `NOTIFICATION_WORKER_ACTOR_ID` 讀取 ACTIVE SYSTEM_SERVICE，再沿用 live actor context resolver 檢查唯一有效 tenant-level membership／ACTIVE tenant。Caller 不能提供 actor 或 tenant，也沒有 browser App Session／cookie／query／fake-role fallback。新設定預設關閉，HMAC key 必須獨立且至少 32 bytes；production 設定明確拒絕啟用此 profile。

這只延續本機／合成測試用格式，不延長 [ADR 0009](../adr/0009-gate-1-synthetic-profile-and-service-boundaries.md) 的期限，不代表 production credential mechanism 已獲核准。正式服務 actor provisioning、憑證選型與輪替仍待完成。本次未新增 migration 或改寫家屬偏好。

## 契約與 CI

通知 request／response body 與 DAILY 日報範圍不變，OpenAPI 的通知端點改用專用 service credential scheme。Selected exporter 只同步指定操作與它需要的新 security scheme，保留其他既有操作描述。CI policy v5 對 worker／LINE config 觸發 Core unit 與 contracts；worker 有獨立 lint／format steps。

## 驗證

| 項目 | 結果 |
| --- | --- |
| 排程、服務驗證與既有 sender 定向 | 115 passed；含 loopback HTTP、CLI 子程序、worker→Core 簽章互通與實際 ASGI route |
| Core 完整 unit | 1960 passed，106.65 秒，單工、BelowNormal |
| CI policy 與 workflow | 29 passed，含新 worker／config impact 與兩個 lint／format step 的嚴格命令清單 |
| 靜態契約／Core live verifier | 通過；OpenAPI 1.13.0、110 paths，既有家屬設定 PUT 保留；通知端點未登入拒絕 |
| 最終 lint／format | Core／worker／CI 通過；Core 489 files、worker 1 file、CI 9 files 格式一致 |
| 獨立 CLI dry-run | exit 0、outcome DRY_RUN、attempts 0，台灣 08:00 正規化為同日 UTC 00:00 |

第一輪 QA 腳本誤用 Core 不支援的 `APP_ENV=test`，collection 未執行；改為合法 development 合成設定。隨後因 oversized body fixture 自動產生過長 pytest ID，Windows 測試 setup 失敗；加上固定短 ID 後定向 115 項全過。兩者均為 QA 設定修正，沒有放寬產品 gate。證據保留在忽略的 `.qa/local/line-scheduler-20261015/`；所有 HTTP／簽章／LINE 回應均為合成資料。

Core live verifier 另沿用既有 development 設定進行健康與未授權路徑檢查，不代表真實 LINE 發送或已驗證 production 服務身分。CI 回歸採 workflow 相同的 PyYAML 依賴，保留嚴格命令覆蓋清單並新增兩個檢查，沒有移除既有 gate。

## 操作與剩餘條件

操作命令、環境變數、exit code、重試與停止語意見 [worker README](../../services/notification-worker/README.md)。先做 dry-run，不代表網路或 LINE readiness 已驗證。

未完成：正式服務身分／憑證與 key 輪替、Messaging API／收件綁定、每日 scheduler 的部署與持久化告警，以及使用者指定家屬的真實收訊／關閉／撤權驗收。平台、region、預算仍待選定；未修改 `.env`、未啟用 flags、未 commit／push／部署。

目前一組 Core 設定只綁定一個服務 actor 及它唯一有效的 tenant membership，不枚舉所有 tenant。多 tenant 的正式 principal 對應仍需後續設計；不能由 client 新增 tenant 選擇。
