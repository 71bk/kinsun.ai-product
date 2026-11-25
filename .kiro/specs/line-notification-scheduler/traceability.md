# 需求追蹤

| 需求 | 實作與驗證 |
| --- | --- |
| R1 單次入口 | `services/notification-worker/run_daily.py` 讀取既有 config，request 通過 Core schema；沒有收件人／DB／LINE 直接呼叫 |
| R2 原預定時間 | 輸入含 offset 且精確台灣 08:00；未到時刻拒絕執行；UTC 正規化、各次 retry 同一 payload；來源日與回應比對 |
| R3 預設 dry-run | 替身驗證不讀 environment、不呼叫 transport；從其他工作目錄的真實 CLI 子程序驗證 default／explicit dry-run |
| R4 身分與範圍 | request-bound ksvc1、新 nonce／TTL、禁止 redirect；Core `notification_service_auth.py`＋repository 綁定 configured actor，再沿用 live context resolver。實際 ASGI 端點拒絕錯誤 subject／audience／簽章／綁定／過期／重播／App Session／失效 actor；factory 強制 durable replay store；production profile 拒絕啟用 |
| R5 重試邊界 | 408／429／5xx／transport exception 有限重試；1／2 秒退避、Retry-After 秒數／日期、長延遲 defer；loopback HTTP 重驗，重試簽章通過 Core verifier 且 nonce 不同 |
| R6 不能誤報成功 | Core status、日期、counts、delivery 格式／狀態不符拒絕；PARTIAL_FAILURE 在真實 CLI 回 code 2，不在 worker 內立即重送 |
| R7 摘要與停止 | JSON 摘要排除 secret／report ID／provider error；CLI 錯誤不回顯參數；中斷不發後續 retry；Core correlation ID 沿用 |
| R8 合成驗證與 CI | 新 tests 位於 Core unit；worker lint／format 與 config／worker impact 接入既有 Core CI。沒有 runtime flag 啟用、實際服務身分 provisioning、DB 寫入、LINE 發送或雲端部署 |

驗收結果與剩餘條件見 [交付報告](../../../docs/project/line-notification-scheduler-20261015.md)。正式憑證、key 輪替、每天觸發的部署與真人收訊仍未完成。
