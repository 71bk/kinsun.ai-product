# LINE 通知排程入口

2026-10-15 使用者核准下一階段第 1 項：補上可執行的排程入口，先用合成資料完成。正式 LINE 設定、收訊與 production 排程部署另行驗收。

- R1：提供單次執行 CLI，沿用 `config/line/daily-family-report-notification-v1.json` 與 Core 通知工作，不在 worker 查個案資料或直接呼叫 LINE。
- R2：必須明確提供含 offset 的 `scheduled_for`，解析為台灣時間精確 08:00；所有重試與外部重跑沿用該時間，不從重試當下時間產生新工作。執行不得早於預定時間。
- R3：預設 dry-run，不讀取憑證、不發出網路請求；只有明確 `--execute` 才可呼叫 Core。
- R4：執行透過受信任 Core origin 與環境注入的獨立 HMAC key，沿用 ksvc1 短效服務憑證；Core 綁定 server-configured SYSTEM_SERVICE，重查 actor／membership／tenant。不得使用瀏覽器 App Session，不接受 caller 提供角色／tenant／收件人；不得跟隨 redirect 或輸出憑證。每次 HTTP 重試發新 nonce，工作時間及 payload 不變；runtime 用持久化 nonce store。
- R5：網路錯誤、408／429／5xx 限制重試次數與等待；沿用相同 payload。認證／輸入錯誤與 3xx 不重試。過長的 Retry-After 交由外部排程稍後重試，不提前重送。
- R6：只接受與本工作時間／來源日期一致、計數與 delivery 狀態一致的成功回應。PARTIAL_FAILURE 必須非零退出，不能把 HTTP 2xx 寫成全部發送成功。
- R7：stdout 只有固定結構摘要與 counts／correlation ID，不含個案／收件人 ID、provider 回應或例外原文。SIGINT／SIGTERM 可停止，不再發出後續請求。
- R8：以離線合成測試驗證時間、防重邊界、錯誤、真實 loopback HTTP 與 CLI；串入既有 Core CI。不得因本次實作啟用 flags、改真實偏好、發真實 LINE 或部署雲端。
