# LINE Daily Notification Scheduler Boundary

本目錄提供 Python 3.12+ 單次執行入口 `run_daily.py`，通知核心仍位於 `services/core-api`。
沒有常駐排程 loop，不選定 Worker framework，也不宣稱 Scheduler、SQS 或 DLQ 已部署。排程介面的單一來源是
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

## 執行入口

從 repository root 執行；程式不載入 `.env`、不連資料庫，也不直接呼叫 LINE。
只使用 Python 標準函式庫；執行環境需有 `Asia/Taipei` IANA 時區資料，Windows 若缺少則需安裝
`tzdata`。可使用現有 Core Python 環境。設定檔相對於入口檔定位，切換工作目錄不影響讀取。

預設 dry-run，`--scheduled-for` 必填，不能以省略時間的方式取得「現在」：

```powershell
& services/core-api/.venv/Scripts/python.exe services/notification-worker/run_daily.py --scheduled-for '2026-10-15T08:00:00+08:00' --dry-run
```

Dry-run 只檢查 schedule config 與時間，輸出 `DRY_RUN`／attempts 0；不讀取憑證、不測試連線、
不代表身份、LINE 或排程已可用。UTC 同一時刻亦可使用 `2026-10-15T00:00:00Z`。

實際呼叫需明確加 `--execute`，並由外部安全注入：

| 環境變數 | 用途 |
| --- | --- |
| `NOTIFICATION_CORE_URL` | 受信任 Core origin，例如 `https://core.example.test`；HTTP 僅允許 literal loopback 或 localhost 作本機測試 |
| `NOTIFICATION_WORKER_HMAC_SECRET` | 獨立、至少 32 bytes 的環境 key，用來簽發每次 request-bound ksvc1 憑證 |
| `NOTIFICATION_WORKER_ISSUER` | 與 Core 相同 issuer，預設 `kinsun-local` |

```powershell
# 只有在上述設定與 Core 端非 production 設定已完成後才執行。
& services/core-api/.venv/Scripts/python.exe services/notification-worker/run_daily.py --scheduled-for '2026-10-15T08:00:00+08:00' --execute
```

不接受 secret／tenant／role／elder／report／收件人 CLI 參數。Core 不會核發 App Session 給
SYSTEM_SERVICE，因此此端點不接受 `ks1_`、cookie、query credential 或 fake-role fallback。
Speech credential 即使格式相同，也因 subject 不同而拒絕。

Core 非 production 設定需有：`NOTIFICATION_WORKER_IDENTITY_ENABLED=true`、相同 HMAC key／issuer，
以及 `NOTIFICATION_WORKER_ACTOR_ID`。Actor ID 僅由 Core 環境設定讀取，不放在 worker request；
必須是 ACTIVE SYSTEM_SERVICE，且在 live DB 有唯一有效、tenant-level SYSTEM_SERVICE membership
及 ACTIVE tenant。每次請求重新檢查，不能用 cache 放過撤權。通知本身仍需既有 LINE flags／credentials。

本次沒有建立真實服務 actor／membership、設定 key 或啟用 flags。HMAC profile 延續既有本機／測試
服務憑證格式，production 設定明確拒絕啟用；未延長 ADR 0009，也未替 production 憑證機制選型。

## 重試、結果與停止

- 每次呼叫只處理一個明確排程時刻；`--execute` 不允許早於該時刻。外部 scheduler 每天台灣時間
  08:00 觸發，失敗重試或跨日補跑須傳回原 `scheduled_for`，不能改成重試當日。UTC 正規化後的
  payload 與同一 invocation 的 correlation ID 在 HTTP retry 之間不變。每次 HTTP request 重新簽發
  30 秒憑證與新 nonce；Core 驗證 signature、issuer／subject／audience、method／path／body hash、
  correlation／TTL 後，以既有 PostgreSQL nonce store 持久化防重播。
- 連線／socket timeout、408／429／5xx 最多共 3 次請求，每次 socket timeout 10 秒，退避 1／2 秒。
  `Retry-After` 秒數與 HTTP-date 可延長等待，超過 30 秒則退出 `RETRY_DEFERRED`，由外部稍後再跑。
  這不是整個工作耗時上限；外部部署仍需配置 process timeout 與執行重疊策略。
- 3xx 不跟隨；401／403／其他非暫時錯誤不重試。拒絕回應 body 不讀取；成功 body 最多 1 MiB。
- 2xx 還會驗證 schedule、前一日來源、schema、counts 與 deliveries；錯誤或不一致不能標記成功。
  `PARTIAL_FAILURE` 不在 worker 內立即重試，先查 Core delivery 狀態與告警；Core 的 lease、最多
  delivery attempts 與 provider retry key 不由 worker 改寫。摘要的 `retryable` 只表示 HTTP 層可稍後重試，
  不能拿它宣稱某一收件人的 terminal failure 已恢復。
- stdout 一行 JSON，含工作時間、outcome、attempts、固定 reason code、counts 與 correlation ID，
  可與 Core `x-correlation-id` log 對照；不輸出 token、個案／報表／收件人 ID、provider body 或例外原文。
  不把收到 2xx 或 `SENT` 當作使用者手機已閱讀／實際收訊驗收。
- SIGINT／SIGTERM 停止後不再發送後續請求；可能已被 Core 接收的工作仍可能完成，不能視為撤回。
  需要重新執行時仍沿用原時刻，交由 Core delivery claim／LINE retry key 防止重複。

| Exit code | 意義 |
| --- | --- |
| 0 | DRY_RUN、COMPLETED 或 NO_ELIGIBLE_REPORTS；須同時檢查 outcome |
| 1 | 網路／HTTP／無效回應／非預期執行錯誤 |
| 2 | Core PARTIAL_FAILURE，需要檢查與追蹤 |
| 64 | CLI、設定、憑證或預定時間錯誤 |
| 130 | 使用者／系統中斷 |

## 測試與部署邊界

合成回歸位於 `services/core-api/tests/unit/test_notification_worker.py`，沿用 Core CI 環境，涵蓋
離線傳輸替身、真實 loopback HTTP 與 CLI 子程序。測試不呼叫外部 Core、資料庫或 LINE。

尚未完成：正式服務身分／憑證的選型、provisioning 與 key 輪替、Messaging API／收件綁定、每日 scheduler 的部署、
持久化告警與使用者指定收件人的真實收訊。平台／region／預算仍待選定；此 CLI 不會自行安裝排程。
