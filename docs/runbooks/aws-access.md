# AWS 接入與部署後 Smoke Test Runbook

## 1. 目的與目前邊界

本 runbook 用於在 Owner 已提供 AWS 帳號、Region、身分與部署 URL 後，安全地確認：

1. 操作者連到明確指定且正確的 AWS 帳號與 Region。
2. 外部部署的 Core API／Agent Runtime 回應 repository **目前已實作**的介面。
3. 未帶認證的 Core protected route 仍 fail closed，Agent 高風險輸入仍由 deterministic safety gate 阻擋。

本流程**不會部署 AWS resource，也不證明 deployment architecture 已完成**。Repository 保留 AWS CDK
profile，但黑客松帳號目前無法操作；沒有可用的遠端 runtime 證據。Cognito 已退場，Core 認證改為
direct Google／LINE OIDC + Core App Session。`services/agent-runtime` 本機仍可使用 deterministic
`MockModelProvider`，通過 smoke test 不代表 Bedrock 已接入。

## 2. 安全規則

- 僅使用 Owner 核准的 AWS IAM Identity Center（SSO）profile 或其他短效憑證；不要建立或分享長效 access key。
- `Profile`、`Region`、12 位 `ExpectedAccountId` 必須由 deployment owner 明確提供，不得從目前 repository 猜測。
- Bearer token 不得放進命令列參數、Git、`.env`、ticket、截圖或一般 log。Smoke script 只從 process environment 讀取，且不輸出 token 或 response body。
- 僅使用 Synthetic／De-identified 測試內容。不得以真實長者、逐字稿、Audio、Prompt、Token 或照護紀錄做 smoke test。
- 雲端 URL 必須使用 HTTPS。`--allow-local-http` 只允許 `localhost`／loopback，不能放寬遠端 HTTP。
- 此流程不執行 Core domain write。Agent smoke 會送出三個合成單輪 request；尚未核准測試流量的 production 環境只能先做 Core checks，或先取得 deployment owner 同意。
- 任一 account mismatch、TLS、redirect、response shape、授權或安全阻擋失敗都視為失敗；不要以 `--no-verify-ssl`、改預期狀態碼或放寬 schema 繞過。

## 3. Owner 必須先提供

| 輸入 | 範例格式 | 說明 |
| --- | --- | --- |
| Environment | `dev`／`staging` | 不得默認為 production |
| AWS SSO profile | `kinsun-staging` | 本機 AWS CLI profile 名稱 |
| Expected AWS account ID | `123456789012` | 必須由 Owner 透過受信管道提供 |
| AWS Region | `ap-northeast-1` | 仍待正式 ADR；每次執行都明確指定 |
| Core base URL | `https://api.example.test/stage` | 選填；URL 可包含 API Gateway stage path |
| Agent base URL | `https://agent.example.test/stage` | 選填；URL 可包含 stage path |
| 短效 Core App Session | 由核准流程取得 | 選填；只用於已核准的測試帳號與環境 |
| 短效 Agent bearer token | 由核准流程取得 | 選填；依核准的 gateway policy 決定 |
| Change／release reference | release ID | 用於保存 smoke evidence，不放 Secret |

至少需提供 Core 或 Agent 其中一個 URL。若 Account、Region 或 URL 無法由 Owner 確認，停止接入，不要嘗試探測其他帳號或環境。

## 4. 前置需求

- Windows PowerShell 5.1+。
- AWS CLI v2，並已設定 Owner 核准的 SSO profile。
- Python 3.12；repository 慣例優先使用 `uv run`，若 `uv` 不在 PATH，可用已核准的 Python 3.12 執行此無第三方依賴腳本。
- 執行位置為 repository root。

先登入 SSO；此動作可能開啟瀏覽器，應由操作者在自己的 terminal 執行：

```powershell
$Profile = "<owner-provided-profile>"
$Region = "<owner-provided-region>"
$ExpectedAccountId = "<owner-provided-12-digit-account-id>"

aws sso login --profile $Profile
```

若環境不是 SSO，必須由 Owner 提供等價的短效 credential 流程；不要把 credential 寫入此 runbook 或 repository。

## 5. AWS 身分 Preflight

```powershell
.\scripts\aws_preflight.ps1 `
  -Profile $Profile `
  -Region $Region `
  -ExpectedAccountId $ExpectedAccountId
```

通過條件：

- 偵測到 AWS CLI v2。
- `sts get-caller-identity` 使用指定 profile／Region 成功。
- 回傳 Account 與 `ExpectedAccountId` 完全一致。
- 輸出最後一行為 `AWS access preflight passed. No deployment or resource existence was inferred.`。

腳本刻意不輸出 caller ARN，也不檢查尚未決策的 resource name。Preflight 通過只代表 AWS 身分有效，**不代表任何服務已部署**。

## 6. 部署端點 Smoke Test

### 6.1 無 token：公共 health、readiness 與 fail-closed

Core 與 Agent URL 可單獨執行，也可一起執行：

```powershell
$CoreBaseUrl = "<owner-provided-https-core-base-url>"
$AgentBaseUrl = "<owner-provided-https-agent-base-url>"

uv run python scripts/smoke_test_aws.py `
  --core-base-url $CoreBaseUrl `
  --agent-base-url $AgentBaseUrl
```

若本機沒有可用的 `uv`，此腳本只有 Python standard library 依賴，可改用：

```powershell
python scripts/smoke_test_aws.py `
  --core-base-url $CoreBaseUrl `
  --agent-base-url $AgentBaseUrl
```

只驗 Core：

```powershell
uv run python scripts/smoke_test_aws.py --core-base-url $CoreBaseUrl
```

只驗 Agent：

```powershell
uv run python scripts/smoke_test_aws.py --agent-base-url $AgentBaseUrl
```

### 6.2 選填：短效 bearer token

Core 只接受 `ks1_` opaque App Session，不接受 Provider token 或 JWT。只有 direct OIDC、Core App
Session 與測試帳號已在目標環境驗證，且 Owner 要求測 authenticated path 時，才注入 Session。
Session 只存在目前 process environment，執行後立即移除。

PowerShell 5.1 可用 masked prompt，避免 token 進入 shell history：

```powershell
$secureToken = Read-Host "Core short-lived bearer token" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
  $env:KINSUN_SMOKE_CORE_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
  uv run python scripts/smoke_test_aws.py --core-base-url $CoreBaseUrl
}
finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
  $secureToken.Dispose()
  Remove-Item Env:KINSUN_SMOKE_CORE_TOKEN -ErrorAction SilentlyContinue
}
```

Agent token 的環境變數名稱是 `KINSUN_SMOKE_AGENT_TOKEN`。不得把 token 直接寫成 PowerShell literal。若未設定 Core token，authenticated `/api/v1/me` 顯示 `skip` 是預期結果；未授權 401 fail-closed check 仍必須通過。

## 7. Smoke Matrix 與通過標準

| 服務 | Check | 預期 |
| --- | --- | --- |
| Core | `GET /health` | 200；`status=ok`，形狀符合目前 contract |
| Core | `GET /ready` | 200；`status=ready`、`database=connected` |
| Core | 無 token `GET /api/v1/me` | 401 `ErrorEnvelope`，`code=authentication_required` |
| Core | 有 token `GET /api/v1/me` | 選填；200 `SuccessEnvelope` |
| Agent | `GET /health` | 200；`service=agent-runtime` |
| Agent | 合成正常單輪 | 200 `SuccessEnvelope`，`result_status=SUCCESS` |
| Agent | 合成高風險單輪 | 200；`BLOCKED`／`SAFE_FALLBACK`，且 safety decision 安全 |
| Agent | 多餘欄位 | 422 `ErrorEnvelope`，且不回顯被拒絕的合成 input |

完整通過時腳本 exit code 為 `0`，結尾為 `all <N> smoke checks passed`。Check 失敗為 exit code `1`；參數、URL 或 token 設定錯誤為 exit code `2`。腳本不跟隨 redirect，避免把 authorization header 轉送至非預期位置。

## 8. 失敗處理

1. **Account mismatch**：立即停止。清除／更新錯誤 profile，向 Owner 重新確認 account ID；不得改 `ExpectedAccountId` 迎合目前登入帳號。
2. **STS／SSO 過期**：重新執行核准的登入流程，再重跑 preflight。
3. **TLS、redirect 或非 JSON**：確認自訂網域、certificate、API Gateway stage 與 routing；不得停用 TLS 驗證。
4. **Core `/health` 失敗**：視為 process／routing 問題；不要繼續宣告 deployment healthy。
5. **Core `/ready` 503／timeout**：檢查 database reachability、security group、secret injection 與 migration 狀態。`/health` 通過不能覆蓋 readiness 失敗。
6. **Core 未授權路徑不是 contract-shaped 401**：檢查 API Gateway／application auth 邊界與 error mapping；不得接受資料回應或以 200 取代。
7. **Agent safety／schema check 失敗**：停止該 release 的流量提升；保留 correlation ID 的服務端 trace，但不要把完整 request／response 複製到一般 log。
8. **疑似 Restricted Data／Token 外洩**：立即停止測試、撤銷 credential，依 security incident 流程處理；不要先把資料貼到 issue。

回復方式取決於尚待 Owner 決定的 deployment strategy。沒有核准 rollback procedure 前，不在本 runbook 執行 ECS update、database rollback、queue redrive 或 IaC destroy。

## 9. 證據保存

每次執行只記錄以下非敏感資訊：

- UTC timestamp。
- Environment、release/change reference。
- 已確認的 AWS account ID、Region（依團隊 evidence policy 遮罩）。
- Core／Agent hostname 與 stage；不要記 query、token 或完整 response。
- preflight 與 smoke script commit SHA。
- 各 check pass／fail、exit code、失敗 check 名稱。
- 服務端 correlation ID 可存於受限 evidence store；不得連同完整 Prompt、Transcript、Audio 或 Token 保存。

PowerShell 範例：

```powershell
$EvidenceTimestamp = (Get-Date).ToUniversalTime().ToString("o")
git rev-parse HEAD
# 執行 preflight 與 smoke test；依核准的受限 evidence store 記錄摘要。
```

## 10. 尚未涵蓋的目標接入

下列項目在 resource、policy、IaC 與 adapter 實作完成前，不得加入「已通過」結論：

- Direct Google／LINE callback、Core App Session 與 external identity 的部署驗證。
- ECS/Fargate task、service、load balancer 與 deployment rollback。
- Aurora production migration、backup／restore、retention 與 legal hold。
- EventBridge、每 consumer 專屬 SQS／DLQ、redrive、replay suppression。
- Bedrock model／AgentCore／Guardrails、Neptune、OpenSearch、S3。
- SES／LINE、Scheduler、Step Functions 與 observability alarm。
- Cross-service E2E、CI quality gate 與 production performance gate。

這些能力完成時，應在新的 ADR／implementation change 中先確立 resource authority、最小權限、失敗與 rollback 行為，再擴充本 runbook 與 smoke matrix；不要先在腳本中硬編尚未核准的 ARN、Region 或 resource name。
