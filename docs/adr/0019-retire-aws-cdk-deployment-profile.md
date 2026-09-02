# ADR 0019：退役 AWS CDK deployment profile

- 狀態：Accepted
- 日期：2026-09-02
- 決策者：Project Owner
- 取代：[ADR 0007](0007-canonical-backend-and-aws-deployment-authority.md) 中 AWS CDK／staging deployment profile 的決策
- 保留：ADR 0007 的單一 Domain Core、legacy backend 退役與禁止 dual write 決策
- 相關：[ADR 0010](0010-provider-neutral-oidc-and-application-sessions.md)、
  [ADR 0018](0018-postgresql-pgvector-public-knowledge-retrieval.md)

## 背景

本專案源自 AWS Hackathon，但黑客松 AWS 帳號已結束且目前沒有使用中的 AWS 服務。現行資料庫是
Supabase PostgreSQL；登入、Session 與 RAG serving path 也已改為不依賴 Cognito、Aurora 或
OpenSearch 的實作。

Repository 仍保留一套可 synth 的 `infra/` CDK workspace、AWS preflight／ECR／SageMaker deployment
腳本與操作 runbook。它們不在現行 CI quality gate，也沒有可操作帳號或 deployment evidence，卻仍被
root npm workspace、依賴鎖檔與協作文件視為現行工具。這會增加維護成本，並讓讀者把歷史 target
architecture 誤判為目前部署環境。

Production hosting provider 仍未定案。保留一套沒有使用者、無法驗證且綁定單一 provider 的 IaC，
不能替代正式的部署決策。

## 決策

1. 刪除 `infra/` AWS CDK workspace，並從 root npm workspace 與 lockfile 移除 CDK 套件及 scripts。
2. 刪除只服務舊 AWS 帳號或 AWS resource 的可執行工具：AWS identity preflight、ECR release
   validation、SageMaker endpoint deployment 與 Hackathon service allowlist check。
3. 移除已被現行 Gate 1 workflow 取代的 disabled PR workflow，以及已無可操作環境的 AWS access
   runbook。
4. 保留兩項 provider-neutral 驗證能力，但改用不含 AWS／staging 語意的名稱：
   - `scripts/build_runtime_images.ps1`／`.sh`：只在本機建立並檢查 OCI images，不 push registry。
   - `scripts/smoke_test_deployment.py`：只透過 HTTPS 驗證外部 Core／Agent endpoint contract，
     不推定 hosting provider。
5. 歷史 AWS Spec、ADR、handover 與 Hackathon service evidence 繼續保留，並明確標示為歷史紀錄，
   不得當成現行 runbook、resource inventory 或部署能力。
6. Application 內既有的 Bedrock、OpenSearch、AWS managed speech 與 SageMaker adapter 不在本 ADR
   的刪除範圍。它們是可替換的 provider adapter，沒有 live deployment evidence；Bedrock／OpenSearch
   不再是 RAG 預設路徑。Speech 的 provider routes 仍屬後續選型工作，不能因移除 IaC 就假定已完成
   provider migration。後續是否退役這些 adapters，應依實際 model、search、speech 選型另立決策。
7. 未來若選定 production hosting provider，必須先建立新的 ADR，記錄 provider、region、成本上限、
   secret injection、network、migration、rollback、observability 與 E2E gates，再新增對應 IaC。

## 後果

### 正面

- Repository 不再把未使用的 AWS topology 呈現成現行部署路徑。
- root Node workspace 只包含實際使用的 `packages/*`，移除 CDK dependency 與維護成本。
- 現行 Supabase PostgreSQL 與 provider-neutral service boundaries 更容易被正確理解。
- 本機 image 與外部 endpoint 驗證仍可沿用，不因 IaC 退役失去 portability checks。

### 代價與限制

- Repository 暫時沒有 production IaC；這是刻意且如實反映尚未選定 hosting provider，而不是
  production deployment 已完成。
- 若未來重新選用 AWS，必須依當時帳號、region、服務與成本重新設計，不得直接把歷史 CDK template
  當成可部署基準。
- optional AWS application adapters 仍會帶有部分 SDK dependency；它們的去留由各 provider 選型
  決定，不由本次 deployment profile 退役順帶刪除。

## 驗證

- root `package.json` 與 `package-lock.json` 不再包含 `infra` workspace 或 CDK packages。
- repository 不再包含 `infra/`、AWS deployment/preflight scripts 或其 active runbook。
- root workspace typecheck、Frontend tests／lint／build 與文件連結檢查維持可執行。
- 歷史文件若提到 AWS，必須能從文件狀態判斷它不是現行部署說明。

## Revisit conditions

- Project Owner 正式選定 production hosting provider。
- 部署環境需要可重建的 network、compute、secret、database 或 observability resources。
- 現行手動／平台代管設定已無法滿足 security、rollback、audit 或 disaster recovery gates。
