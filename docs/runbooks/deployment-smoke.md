# 外部部署 Smoke Test Runbook

## 目的與邊界

本 runbook 驗證外部部署的 Core API／Agent Runtime 是否回應 repository 目前已有的介面，不假設
AWS、Azure、GCP 或其他 hosting provider，也不代表 production architecture 已完成。

目前 repository 沒有 production IaC。部署目標、網址與短效測試憑證都必須由 deployment owner
明確提供；無法確認時停止，不得掃描或猜測環境。

## 安全規則

- 只使用 Synthetic／De-identified 測試內容。
- Token 只經 process environment 傳入，不放在命令列、Git、`.env`、截圖或一般 log。
- 遠端 URL 必須使用 HTTPS；`--allow-local-http` 只允許 loopback 本機測試。
- Script 不輸出 token 或完整 response body，也不跟隨 redirect。

## 執行

至少提供 Core 或 Agent 其中一個 URL：

```powershell
$CoreBaseUrl = "https://<owner-provided-core-host>"
$AgentBaseUrl = "https://<owner-provided-agent-host>"

uv run python scripts/smoke_test_deployment.py `
  --core-base-url $CoreBaseUrl `
  --agent-base-url $AgentBaseUrl
```

只驗單一服務時省略另一個參數。本機 loopback 測試可加 `--allow-local-http`。

需要驗證受保護 Core route 時，先由核准流程取得短效 synthetic account session，再只於目前 process
設定：

```powershell
$env:KINSUN_SMOKE_CORE_TOKEN = "<short-lived-token>"
try {
  uv run python scripts/smoke_test_deployment.py --core-base-url $CoreBaseUrl
}
finally {
  Remove-Item Env:KINSUN_SMOKE_CORE_TOKEN -ErrorAction SilentlyContinue
}
```

Agent gateway 若需要 bearer，使用 `KINSUN_SMOKE_AGENT_TOKEN` 並採相同處理方式。

## 通過與失敗

通過只代表指定 URL 的 health、contract shape、未認證拒絕與 deterministic safety checks 在該次
測試成立。它不證明資料庫 migration、provider、queue、notification、speech、RAG、備援或 production
容量已完成。

遇到 TLS、redirect、非 JSON、readiness、authentication shape 或 safety check 失敗時，停止 release
提升並保留不含 Restricted Data 的 check name、timestamp、release reference 與 exit code。

