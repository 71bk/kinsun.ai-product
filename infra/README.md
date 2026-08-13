# AWS infrastructure profile

`infra/` 是保留的 AWS CDK v2 deployment profile。黑客松 AWS 帳號目前已無法操作，因此本目錄的
CloudFormation template 只代表 repository 中可測試、可 synth 的部署設計；不能據此宣稱任何 AWS
resource 仍存在、可存取或正在計費。不要在沒有新的 AWS 帳號、Owner 授權與部署前檢查時執行 deploy。

## Repository 現況

- `canonical-staging-foundation-stack.ts` 定義 VPC、ECR、ECS cluster、Aurora、Secrets、Logs、IAM
  roles 與 OpenSearch external reference。
- `canonical-staging-application-stack.ts` 定義 Frontend、Core API、Core migration、Agent Runtime 與
  Speech Gateway 的 ECS/Fargate application topology，`ServiceDesiredCount` 預設為 `0`。
- Cognito construct、parameter、SSM reference、secret injection 與 output 已移除。登入由 application
  code 的 direct Google／LINE OIDC + Core-owned App Session 負責。
- 目前實際資料庫 provider 是 Supabase PostgreSQL；本 AWS profile 內的 Aurora 不是現行資料來源。
- OpenSearch、Bedrock、managed speech 與 SageMaker adapter 仍存在於程式或 IaC 邊界，但沒有目前帳號的
  live deployment 證據，不得描述為可用服務。

## 可安全執行的本機檢查

```powershell
npm run test --workspace @elderly-care/infrastructure
npm run typecheck --workspace @elderly-care/infrastructure
npm run synth --workspace @elderly-care/infrastructure
npm run synth:application --workspace @elderly-care/infrastructure
```

以上只驗證 TypeScript 與 CloudFormation 形狀，不會確認遠端資源。application profile 目前也沒有注入
direct OIDC 的 provider credentials；若未來重新採 AWS，必須先設計 provider-neutral 的 runtime secret
注入、重新做 database migration/preflight、image digest、內部 smoke 與公開流量 gate，不能直接把
`desiredCount` 調成 `1`。

## 邊界

- 不恢復 Cognito 或另一套 Identity Provider；Core Actor／ExternalIdentity／App Session 是身份權威。
- 不建立第二套 Domain backend、DynamoDB source of truth 或 legacy Lambda backend。
- AWS-specific construct 不得滲入 Domain service；Core 只透過 PostgreSQL、HTTP、model、speech、event
  等 adapter contract 使用外部能力。
- 是否保留、改寫或刪除其餘 AWS profile，應在盤點可替代服務與實際部署目標後另立 ADR。

歷史 AWS canonical 決策見
[`docs/adr/0007-canonical-backend-and-aws-deployment-authority.md`](../docs/adr/0007-canonical-backend-and-aws-deployment-authority.md)；
現行身份決策見
[`docs/adr/0010-provider-neutral-oidc-and-application-sessions.md`](../docs/adr/0010-provider-neutral-oidc-and-application-sessions.md)。
