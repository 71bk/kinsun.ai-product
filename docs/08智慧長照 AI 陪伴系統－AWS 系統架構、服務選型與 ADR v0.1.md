智慧長照 AI 陪伴系統－AWS 系統架構、服務選型與 ADR v0.1

## 文件資訊

版本：v0.1

狀態：Draft｜Target Architecture 與黑客松實作基準，待 Region Matrix、成本估算與技術 Spike 驗證

建立日期：2026-07-26

文件 Owner：待團隊指定

審查者：五人團隊

適用範圍：長者語音端、專業照護端、家屬端、Agentic Workflow、RAG、Graph、報表通知、安全、可觀測性與部署營運

## 相關文件

01｜產品方向與範圍基準 v1.2

https://docs.google.com/document/d/1Z8Ser24Jx8wavKRrMkLdwlZ0PjQedWyYOp4g29FLEuc/edit

01A｜使用者研究與 Demo Persona v0.2

https://docs.google.com/document/d/1tZjDn5uY2FuVaTTLVshFjGSMaMP-37koqNZxfS2qjIQ/edit

02｜使用者故事與驗收條件 v1.3.2

https://docs.google.com/document/d/1qb89I23zD8GJFzead_R_G6fXq2CZWgEsKBK7Q4o_F8A/edit

03｜Story Map v1.2

https://docs.google.com/spreadsheets/d/1Qmg1jbaN67Tjmpcx6e2zyZOf_-td0_fg9iKqgb128CE/edit

04｜資訊架構、UX 與 User Flow v0.1

https://docs.google.com/document/d/1LO4FIONTEYVj4Oz_blIn25l4YN4ROm7lINrWG3Sd8r0/edit

05｜核心工作流、狀態機與錯誤恢復 v0.1

https://docs.google.com/document/d/1fPZFY6Y7BEr6LnVOBVd7sRbmmAvUEutIS-HBesEOvoY/edit

06｜Domain Model、商業規則與資料生命週期 v0.1

https://docs.google.com/document/d/1B4dyCdiuAR7eR15cOgoQRZGsitcJN27Brgil58D4-J8/edit

07｜Security、Privacy、NFR 與 Threat Model v0.1

https://docs.google.com/document/d/1UUnrs6FUCqlaNxaDm12zPVFAPfQG0ruWqdiL0HXvTrI/edit

# 一、文件目的與架構策略

本文件將 05～07 的工作流、Domain 與安全需求轉成 AWS Target Architecture，回答：

• 每個系統責任由哪一類 AWS 服務承擔？

• 哪些流程同步執行、哪些採事件與背景工作？

• RDS、Graph、Search／Vector、Object Storage 與 Agent Memory 如何分工？

• 國語、臺語、客語與混語的 ASR／TTS 如何路由與降級？

• 五人團隊如何在完整架構不縮水的前提下，分階段實作？

• 每項重要選擇的替代方案、理由、限制與退場策略為何？

本文件採「完整規劃、分期實作」：Target Architecture 定義最終責任邊界；Hackathon Profile 只縮減部署數量與非核心元件，不改變 Domain、Security、Contract 與資料責任。

# 二、架構決策摘要

1. 前端採單一多角色 PWA／Web Codebase，依角色與授權顯示長者、日照照服員、居服員及家屬介面。

2. 核心業務後端採 Python Modular Monolith，部署於 Amazon ECS on AWS Fargate；Web Framework 由 FastAPI／Django 技術 Spike 後定案。

3. API 入口採 Amazon API Gateway：HTTP API 處理一般 API，WebSocket API 處理語音 Session 控制與即時狀態。

4. 身份採 Amazon Cognito User Pools；真正的 elder／tenant／assignment／share_scope 授權由應用程式 ABAC Policy 執行。

5. Agent 執行採 Amazon Bedrock AgentCore Runtime；工具透過 AgentCore Gateway 或受控 Tool API 暴露。

6. Foundation Model 採 Amazon Bedrock，模型 ID 不寫死，以 Model Router 依任務、區域、品質、延遲與成本選擇。

7. 正式業務事實採 Amazon Aurora PostgreSQL；Graph、Search／Vector 與 Cache 均為可重建投影。

8. 已確認關係與記憶投影至 Amazon Neptune Serverless；不得以 Neptune 直接決定授權。

9. RAG 與混合搜尋採 Amazon OpenSearch Serverless；關鍵字、向量及 metadata filtering 共用檢索層。

10. 語音採 Speech Router：國語優先 Amazon Transcribe zh-TW；臺語／客語／專案微調模型採 SageMaker AI Real-Time Endpoint。

11. TTS 採 Voice Router：Amazon Polly 負責可接受的國語路徑；臺語／客語或特定聲線由自建模型 Endpoint 處理。

12. Domain Event 採 Transactional Outbox → Amazon EventBridge → 每個 Consumer 專屬 Amazon SQS Queue／DLQ。

13. 長流程與人工等待採 AWS Step Functions Standard；即時語音主路徑不經 Step Functions。

14. 每日、週、月報及主動陪伴 Trigger 採 Amazon EventBridge Scheduler。

15. App／Web 是家屬報表正式來源；LINE Messaging API 與 Amazon SES 只是通知 Adapter。

16. Infrastructure as Code 採 AWS CDK；容器映像放 Amazon ECR；CI/CD 以 GitHub Actions OIDC 或 AWS CodePipeline 執行。

# 三、Target Architecture 全貌

## 3.1 邏輯架構

使用者裝置

├─ 長者平板／PWA

├─ 日照照服員 Web

├─ 居服員 Mobile Web／PWA

└─ 家屬 App／Web

↓

Amazon Route 53

↓

Amazon CloudFront ＋ AWS WAF

├─ 靜態前端：Amazon S3

├─ HTTP API：Amazon API Gateway

└─ WebSocket：Amazon API Gateway WebSocket API

↓

Identity：Amazon Cognito User Pools

↓

Core API：Amazon ECS／Fargate｜Python Modular Monolith

├─ Identity／Authorization Policy

├─ Elder／Consent／Assignment

├─ Care Event／Summary／Memory

├─ Family Report／Notification

└─ Outbox／Audit／Deletion

↓

AI 與語音層

├─ Amazon Bedrock AgentCore Runtime

├─ AgentCore Gateway／Identity／Observability

├─ Amazon Bedrock Models ＋ Guardrails

├─ Speech Router → Amazon Transcribe 或 SageMaker ASR

└─ Voice Router → Amazon Polly 或 SageMaker TTS

↓

事件與工作流

├─ Amazon EventBridge

├─ Amazon SQS ＋ DLQ

├─ AWS Step Functions Standard

└─ Amazon EventBridge Scheduler

↓

資料層

├─ Amazon Aurora PostgreSQL｜System of Record

├─ Amazon S3｜音訊、文件、Chunk、報表附件

├─ Amazon Neptune Serverless｜Graph Projection

├─ Amazon OpenSearch Serverless｜Keyword／Vector／RAG

├─ Amazon ElastiCache｜短期 Session／Query Cache（Target）

└─ AWS Backup／Snapshot｜恢復

↓

營運安全

├─ AWS KMS／Secrets Manager／IAM

├─ CloudWatch／X-Ray／OpenTelemetry

├─ CloudTrail／AWS Config

├─ GuardDuty／Security Hub（正式環境）

└─ Budgets／Cost Anomaly Detection

## 3.2 架構原則

• System of Record First：先成功寫入 Aurora 與 Outbox，才由背景工作更新 Neptune、OpenSearch、通知與分析。

• No Blind Dual Write：禁止同一請求直接雙寫 Aurora＋Neptune 或 Aurora＋OpenSearch。

• Sync for User Value：身份、權限、同意、主要語音回覆與正式寫入走同步或短路徑。

• Async for Derivatives：事件擷取、Graph 投影、搜尋索引、週月報、通知與刪除清理走非同步。

• Agent Cannot Own Business State：Agent 只能提出候選；正式狀態由 Core API 的 Domain Service 改變。

• Region-Aware：模型、AgentCore、Neptune、OpenSearch、Transcribe 及 SageMaker 必須在 Region Matrix 中共同驗證。

# 四、體驗層與 Edge

## 4.1 前端

選擇：React 或 Vue 的響應式 PWA，單一 Repository、多角色 Route 與 Component Library。

部署：Production 以 S3 靜態 Hosting＋CloudFront；Preview Environment 可使用獨立 Bucket／Distribution。

理由：三種後台與長者端共用 Design Token、身份、報表及錯誤狀態，避免維護四套前端。

## 4.2 CloudFront／WAF

CloudFront 統一提供 TLS、靜態內容、API Domain 與快取控制。AWS WAF 套用 Rate Limit、已知攻擊規則與惡意 Bot 基礎控制。

Restricted API 回應設定 no-store；個人化 HTML／JSON 不進共享 Cache。

## 4.3 API Gateway

HTTP API：一般 CRUD、摘要、報表、派案、同意與管理 API。

WebSocket API：語音 Session 建立、狀態事件、partial／final transcript、播放狀態及取消指令。

注意：原始音訊是否經 WebSocket Proxy、直接送 Speech Service，或先傳 S3，須由 Voice Spike 依延遲與格式決定。

# 五、身份、授權與租戶隔離

## 5.1 Amazon Cognito

• 專業照護者、家屬、管理者使用 Cognito User Pool。

• 管理者與高權限角色啟用 MFA。

• LINE Login 若採用，作為 Federation／身份連結，不直接代表 elder 資料授權。

• 長者受控裝置使用 Device Enrollment＋短效 Session；分享、刪除與高風險設定需再次驗證。

## 5.2 Authorization Policy Service

Cognito Groups 只提供粗粒度 Role；Core API 每次請求執行：

actor_id＋role＋tenant_id＋elder_id＋care_unit_id＋relationship_id／assignment_id＋share_scope＋resource_status＋consent_version＋purpose＋time_window。

授權 Policy 實作先置於 Python Core Domain Module，介面保留未來接 Cedar／Verified Permissions 的可能性。v0.1 不另加 Policy Engine，避免五人團隊同時維護兩套授權語意。

# 六、核心應用運算

## 6.1 Amazon ECS on AWS Fargate

選擇：Core API、Authorization、Report API、Outbox Publisher 先採單一 Modular Monolith Container，可依模組與流量拆成服務。

理由：

• Python 可與 Agent、RAG、ASR／TTS、資料處理及 AWS SDK 共用語言與型別工具。

• 容器可保有長連線、Connection Pool、交易與既有 Library。

• Fargate 不需管理 EC2 主機或 Kubernetes Control Plane。

Target：至少兩個 Task 跨 Availability Zone，置於 Private Subnet，由 Internal ALB 接收 API Gateway VPC Link 流量。

Hackathon：可先單 Task；不得使用真實資料，並保留相同 IAM、Schema 與部署模板。

## 6.2 Lambda 使用邊界

Lambda 適合：

• LINE／Email Adapter

• S3 Object Event 處理

• EventBridge／SQS 輕量 Consumer

• 定時清理與 Glue Code

• 小型檔案轉換

不建議第一版用 Lambda 承擔全部 Python Domain Logic，以避免交易、冷啟動、部署與除錯分散。

# 七、Agent 與 Foundation Model 架構

## 7.1 Amazon Bedrock AgentCore Runtime

AgentCore Runtime 負責 Agent Container 的 Session Isolation、Scale、Auth Gate 與 Observability Plumbing；Orchestration Loop 仍由團隊程式控制。

Agent 分工建議：

• Conversation Orchestrator：對話主流程與工具選擇。

• Companion Agent：陪伴式短回覆。

• Event Extractor：輸出 Care Event Candidate Schema。

• Memory Extractor：輸出 Memory Candidate Schema。

• Summary Agent：產生專業版／家屬版 Draft。

• Proactive Topic Agent：產生候選主題與開場，不決定 Eligibility。

• Safety Evaluator：應用內容政策與理由碼。

## 7.2 AgentCore 元件邊界

• Runtime：執行 Agent Code。

• Gateway：將受控 API／Lambda 轉為 Agent Tool／MCP 入口。

• Identity：需要代表特定使用者呼叫外部工具時採用；不得取代 Core ABAC。

• Observability：輸出 Agent Session Metrics、Trace 與 Logs 至 CloudWatch。

• Evaluations：在後期建立 response quality、task completion、safety 與 tool usage 評估。

• Memory：只考慮短期 Session／Working Memory；正式確認式長期記憶仍在 Aurora，Neptune 為投影。

## 7.3 Model Router

所有 Agent 呼叫經 Model Router：

task_type＋language＋risk_level＋latency_budget＋quality_tier＋region_availability＋cost_policy → model_id／inference_profile／guardrail_id。

不得在 Business Code 寫死單一 Model ID。

## 7.4 Bedrock Guardrails

使用者輸入、RAG Context 與模型輸出套用 Guardrails／自訂 Safety Rule。IAM Policy 應要求高風險 Agent 使用指定 Guardrail；Output 仍需 Core API 做 Schema、PII、Share Scope 與醫療邊界檢查。

# 八、語音鏈路與多語路由

## 8.1 Speech Router

Input：elder preference、explicit language switch、session history、audio metadata。

Output：provider、language_code、model_version、confidence_policy、fallback_order。

路由基準：

• 國語／繁體中文：Amazon Transcribe zh-TW Streaming 作 Baseline。

• 國語專有名詞：使用 zh-TW Custom Vocabulary／注音 SoundsLike 能力進行 Spike。

• 臺語：Taiwan Tongues ASR 或其他已驗證模型部署 SageMaker AI Real-Time Endpoint。

• 客語：專用模型或資料不足時明確降級，不把國語結果當正確答案。

• 中臺／中客混語：先由 Persona 與 Session 偏好縮小候選；必要時使用自建 Router，不依賴無限制自動語言猜測。

現行 Amazon Transcribe 語言表列有 zh-TW 批次與串流，但未列臺語、客語為獨立語言；因此臺語／客語不得只靠 Transcribe 宣稱完整支援。

## 8.2 SageMaker AI Real-Time Endpoint

用途：自建 ASR、TTS、語言辨識或重排序模型。

部署要求：

• Model Artifact／Container 版本化。

• Endpoint 放 Private Network；Core／Speech Gateway 透過 IAM 呼叫。

• CloudWatch 記錄 latency、model error、GPU／CPU 指標。

• 建立 canary sample 與 fallback。

• GPU Endpoint 依 Demo 時段啟停，正式環境才評估 Auto Scaling。

## 8.3 TTS Router

• 國語：Amazon Polly 作可快速驗證的 Baseline；需以長者可懂度測試，不假設中國普通話聲線等同臺灣長者偏好。

• 臺語／客語：自建 TTS Endpoint 或經授權語音模型。

• TTS 失敗：顯示文字、允許重播，不回滾已完成文字回覆。

# 九、資料架構

## 9.1 Aurora PostgreSQL

保存：Actor、Tenant、Elder、Relationship、Assignment、Consent、Conversation Metadata、Care Event、Summary、Memory、Report、Notification State、Care Action、Trigger、Deletion Job、Audit Reference、Outbox。

選型：Aurora PostgreSQL Serverless v2 作 Target Baseline；實際 Min／Max ACU 需成本 Spike。

理由：交易、外鍵、版本、JSONB、Outbox，並可搭配 Python ORM 與資料驗證工具實作 Domain Model。

## 9.2 Amazon S3

Bucket／Prefix 分離：

• raw-audio（短期、Restricted）

• transcript-artifacts

• rag-source

• rag-processed

• report-export

• audit-evidence

所有 Bucket Block Public Access、KMS Encryption、Lifecycle、Versioning／Object Lock 是否啟用依資料類型決定。前端不得直接列舉 Bucket；只使用短效、限物件、限用途 URL。

## 9.3 Amazon Neptune Serverless

保存：ACTIVE／VERIFIED 的人物、家庭關係、照護關係、活動、偏好、作息、事件與來源投影。

用途：

•「女兒與林阿嬤的關係」

•「哪些事件涉及同一人物」

•「最近與某活動相關的已確認記憶」

限制：

• 不做身份授權來源。

• 不保存候選、拒絕或撤回資料作 Active Context。

• Region 可用性與最低成本必須先 Spike。

• Graph 失敗時回到 Aurora／Search 降級。

## 9.4 Amazon OpenSearch Serverless

Collection：

• care-search：事件／摘要關鍵字與語意搜尋。

• knowledge-vector：長照法規、衛教文件與審查 Chunk。

每筆文件必含 tenant_id、elder_id（知識庫可為 null）、status、review_status、consent_version、source_id、source_version、publish_agency、category、risk_level 與 effective period。

檢索策略：

Keyword BM25＋Vector Similarity＋Metadata Filter＋可選 Reranker。

Graph Search 不與 Keyword／Vector 二選一；只在關係查詢時由 Query Planner 叫用。

## 9.5 Bedrock Knowledge Bases 決策

v0.1 採「保留 Bedrock Knowledge Bases 作 Managed Retrieval 選項，但不立刻交出 Chunking Source of Truth」。

原因：團隊已建立自訂來源登錄、Chunk、Review 與 Metadata 規則，需要驗證 Managed Ingestion 是否完整保留。

Spike 通過條件：

• 可使用既定 Chunk／Metadata。

• 可強制 review_status 與 risk_level Filter。

• 可回傳 source_id／version。

• 可私有連線 OpenSearch Serverless。

若未通過，採自訂 Ingestion Pipeline＋OpenSearch Query API。

## 9.6 Cache

Target 可用 ElastiCache Redis 保存短期 Session、Rate Limit、Query Cache 與 WebSocket Connection Metadata。

不得把 Consent、Assignment 或 Published 狀態只存在 Cache；權限變更需立即失效。

Hackathon 可先用 Core Memory／Aurora，避免增加非必要服務。

# 十、事件驅動與工作流架構

## 10.1 Transactional Outbox

Core API 在同一 Aurora Transaction 寫入 Domain Aggregate 與 Outbox Record。

Outbox Publisher 發送至 EventBridge；成功後更新 published_at。Consumer 依 event_id／idempotency_key 去重。

## 10.2 EventBridge＋SQS

EventBridge 依 event_type、tenant、risk、resource_type 路由。

每個重要 Consumer 使用專屬 SQS Queue：

• care-event-extraction

• memory-projection

• search-indexing

• summary-generation

• family-report-generation

• notification-delivery

• deletion-processing

• proactive-trigger

每個 Queue 具 Visibility Timeout、Max Receive Count、DLQ、Alarm 與 Redrive Runbook。

## 10.3 Step Functions Standard

適用：

• Event Review／Summary Rebuild

• Family Report Draft→Review→Publish→Notify

• Consent Revocation／Deletion Fan-out

• RAG Ingestion／Review／Index

• 需要人工 Approval Callback 的主動陪伴

不適用：

• ASR→LLM→TTS 即時主路徑

• 單次低延遲查詢

## 10.4 EventBridge Scheduler

適用：

• 每日摘要

• 每週／每月家屬報表

• 主動陪伴一次性 Trigger

• Retention Cleanup

• Secure Link Expiry Cleanup

每次排程到期仍重新檢查 Consent、Authorization、Source Status 與 Policy，不因排程存在就直接執行。

# 十一、家屬報表與通知架構

## 11.1 App／Web

Family Report API 只查 PUBLISHED 且 Share Scope 有效的版本。Report Page 每次開啟重新驗證 Relationship、Consent、report status 與 Secure Link。

## 11.2 LINE

Lambda／Fargate Notification Adapter 呼叫 LINE Messaging API。

Secrets 放 Secrets Manager；Webhook 簽章驗證；通知只含最小預覽與安全連結。

## 11.3 Email

Amazon SES 寄送簡短預覽與連結；不把完整 Restricted 報表當永久附件。

## 11.4 Delivery State

Aurora 保存 Notification Delivery；SQS 負責重試。通知失敗不修改 Family Report 的 PUBLISHED 狀態。

# 十二、網路與安全部署

## 12.1 VPC

至少兩個 Availability Zone：

• Public Subnet：必要的 Internet-facing Load Balancer／NAT Gateway。

• Private App Subnet：ECS Tasks、Lambda VPC Integration、Agent Adapter。

• Isolated Data Subnet：Aurora、Neptune、ElastiCache。

API Gateway 透過 VPC Link 到 Internal ALB。Aurora／Neptune 不開 Public Access。S3、ECR、CloudWatch、Secrets Manager 等優先使用 VPC Endpoint，實際 Endpoint 依成本取捨。

## 12.2 Encryption

• KMS Key 分為 application-data、audio-object、search／graph、logs／backup 等用途。

• Secrets Manager 保存 DB、LINE、外部 API 與 signing secrets。

• Service Role 只能讀取自身需要 Secret。

## 12.3 Security Services

Target Production：AWS WAF、CloudTrail、AWS Config、GuardDuty、Security Hub、ECR Image Scan、Inspector／Dependency Scan、Backup Vault。

Hackathon：WAF、CloudTrail、Secret Scan、ECR Scan、IAM Least Privilege 與 Demo Data Gate 為最低必做。

# 十三、可觀測性

## 13.1 Trace

OpenTelemetry／X-Ray Trace Context：

CloudFront／API Gateway → Core API → AgentCore／Bedrock → Speech → Aurora／EventBridge → Consumer → Report／Notification。

## 13.2 CloudWatch Dashboard

最低顯示：

• ASR final、LLM、TTS p50／p95

• API latency／5xx／4xx

• Agent tool call success／blocked

• EventBridge failed invocation

• SQS age／depth／DLQ

• Aurora connections／CPU／ACU

• Neptune projection lag

• OpenSearch ingestion／query latency

• Report publish time

• LINE／Email success rate

• Authorization denied、Consent blocked、Safety blocked

## 13.3 Agent Observability

AgentCore Observability 的 Metrics／Spans／Logs 進 CloudWatch；自訂 Trace 需保留 source_ids、tool_name、policy result、model／prompt version，不保留不必要完整 Prompt。

# 十四、Region 與環境策略

## 14.1 Region Decision Matrix

部署前對候選 Region 評分：

• 臺灣使用者網路延遲

• Bedrock 目標模型與 Guardrails

• AgentCore Runtime／Gateway／Memory／Evaluations

• Transcribe zh-TW

• SageMaker GPU Instance

• Neptune Serverless

• OpenSearch Serverless Vector

• Aurora Serverless v2

• SES Sending 與資料落地要求

• 價格、Quota 與黑客松帳號可用性

v0.1 不直接鎖定 Region。候選可先比較東京與新加坡；以服務共同可用性及實測延遲決定，不能只依地理距離。

## 14.2 Environment

• dev：合成資料、低容量、開發模型與短 Retention。

• test：固定 Persona、整合測試與攻擊測試。

• demo：獨立 Stack、虛擬 Persona、可重置 Seed。

• prod：獨立 AWS Account／VPC／KMS／Secrets／Data。

黑客松可暫時同一 Account 不同 Stack／Prefix，但不得共用正式資料與 Secrets。

# 十五、CI/CD 與 Infrastructure as Code

• AWS CDK 定義 Network、IAM、Cognito、API、ECS、Aurora、Queues、State Machines、Buckets、Search、Graph 與 Monitoring。

• GitHub Actions 以 OIDC Assume Role，不保存長期 AWS Access Key。

• Container Build → Test → Secret／Dependency Scan → ECR → Deploy Dev → Integration Test → Manual Approval → Demo／Prod。

• DB Migration 使用 Alembic（若採 SQLAlchemy）或框架原生 Migration；同一版本只由一個 migration job 執行，Web／Worker 不競爭 Migration。

• Prompt、Policy、Schema、Model Route 與 RAG Manifest 與程式一樣版本化。

# 十六、Hackathon Implementation Profile

## 16.1 Demo 必做

• S3＋CloudFront 前端

• Cognito 登入

• API Gateway HTTP／WebSocket

• ECS Fargate Python Core API

• Aurora PostgreSQL

• Bedrock Model＋Guardrail

• AgentCore Runtime 或可替換的 Container Runtime

• Transcribe zh-TW＋一條自建臺語 ASR Endpoint

• S3 語音／RAG Artifact

• EventBridge＋SQS＋DLQ

• Step Functions：至少 Report 或 Memory Projection 一條

• OpenSearch：Keyword＋Vector Demo

• Neptune：林阿嬤→女兒→每週日通話關係

• SES 或 LINE 至少一條真實通知

• CloudWatch Trace／Dashboard

## 16.2 可延後但架構保留

• Multi-AZ Production Scaling

• ElastiCache

• 多 Account AWS Organizations

• AgentCore Evaluations 全套

• 客語 Custom TTS 完整模型

• 離線居服草稿

• 跨機構共同照護

• 自動 Backup Restore Drill

## 16.3 禁止以 Mock 取代

• elder／tenant／assignment 授權

• Consent Gate

• 未確認記憶不得 ACTIVE

• Report PUBLISHED 才能給家屬

• Notification Failure 不回滾 Report

• 張阿姨資料不得進林阿嬤 Context

# 十七、主要同步流程

## 17.1 長者語音

PWA → WebSocket Session → Core Authorization／Consent → Speech Router → Transcribe／SageMaker ASR → Low Confidence Confirmation → AgentCore Orchestrator → Bedrock Guardrail＋Model → TTS Router → Polly／SageMaker TTS → PWA Playback。

Event／Memory Extraction 由完成事件轉非同步，不阻塞主要回覆。

## 17.2 日照照服員

Web → HTTP API → Cognito JWT → Core ABAC → Aurora Query → Multi-Elder Overview → Elder Detail → Review Command → Aurora Transaction＋Outbox。

## 17.3 居服員

PWA → HTTP API → Cognito → Assignment Validation → Minimal Elder View → Service Record → Aurora＋Outbox。

## 17.4 家屬

LINE／Email → Secure Link → Cognito／Recipient Verification → Family Relationship＋Consent＋PUBLISHED Check → Report API → App／Web。

# 十八、主要非同步流程

## 18.1 Event／Memory

ConversationSessionCompleted → EventBridge → SQS → Extractor Agent → Schema／Consent → Candidate Write → Review／Confirm → Outbox → Neptune／OpenSearch Projection。

## 18.2 Family Report

Scheduler → Step Functions → Source Query → Summary Agent → Share／Safety Check → Human Review（必要時）→ PUBLISHED → EventBridge → Notification Queue → LINE／SES。

## 18.3 Deletion

ConsentRevoked → Step Functions → Deletion Job Items → Aurora／S3／Neptune／OpenSearch／Cache／Secure Link Consumers → Completion／Partial Failure → Audit。

# 十九、Service Selection Matrix

Frontend：S3＋CloudFront｜Alternative：Amplify Hosting｜選擇理由：部署可控、角色共用、易接 WAF。

Core Compute：ECS Fargate｜Alternative：Lambda／EKS｜理由：Python API、長連線、交易、Agent 整合與五人維運能力。

Identity：Cognito User Pools｜Alternative：自建 Auth｜理由：減少密碼、MFA、Federation 維運。

Agent Runtime：Bedrock AgentCore Runtime｜Alternative：ECS 自管｜理由：Session Isolation、Scale、Agent Observability；保留框架自由。

LLM：Amazon Bedrock｜Alternative：SageMaker 自架 LLM｜理由：多模型、Guardrails、少管理推論基礎設施。

Transactional DB：Aurora PostgreSQL｜Alternative：RDS PostgreSQL／DynamoDB｜理由：關聯、交易、版本、JSONB、Outbox。

Graph：Neptune Serverless｜Alternative：Aurora Relation Table｜理由：關係查詢；但可降級及可退出。

Search／Vector：OpenSearch Serverless｜Alternative：Aurora pgvector｜理由：Keyword＋Vector＋Filter＋獨立擴充。

Workflow：Step Functions Standard｜Alternative：全部寫在 App Code｜理由：長流程、等待、重試、可視化與 Audit。

Event Bus：EventBridge｜Alternative：直接 Queue｜理由：Domain Event 多 Consumer 路由。

Queue：SQS｜Alternative：Kafka／MSK｜理由：團隊規模與需求不需維運 Stream Platform。

Custom ML：SageMaker Real-Time Endpoint｜Alternative：ECS GPU｜理由：Model Hosting、版本與 Endpoint 管理。

Email：SES｜Alternative：第三方 Email｜理由：AWS 整合與最小 Adapter。

# 二十、Architecture Decision Records

ADR-001｜採 Python Modular Monolith on ECS Fargate

狀態：Accepted for v0.1。

原因：五人團隊、Python 可整合 API、Agent 與資料處理，且 Domain 尚在快速變動。

代價：需自行管理 Container、ALB、Scaling 與 Deployment。

退場：模組有獨立流量／Owner／SLO 後拆服務。

ADR-002｜Aurora 是 System of Record

狀態：Accepted。

原因：強一致、版本、關聯與 Outbox。

禁止：以 Neptune／OpenSearch／Agent Memory 反向覆蓋正式事實。

ADR-003｜Neptune 為 Graph Projection

狀態：Accepted with Spike。

原因：關係密集查詢與 Demo 可解釋性。

退出條件：成本、Region 或延遲不合格時，以 Aurora Relation＋OpenSearch 暫代。

ADR-004｜OpenSearch Serverless 作 Hybrid Retrieval

狀態：Accepted with Cost Spike。

原因：Keyword、Vector 與 Metadata Filter 同層。

替代：Aurora pgvector 適合早期低量，但完整 Keyword／Search Ops 較弱。

ADR-005｜AgentCore Runtime 執行 Agent，Domain State 留在 Core

狀態：Accepted。

原因：AgentCore 管 Runtime／Isolation／Observability；Core 控制狀態與規則。

禁止：Agent 直接更新 DB 或自行發布報表。

ADR-006｜Transcribe＋Custom ASR 雙路由

狀態：Accepted。

原因：zh-TW 有 Managed Baseline；臺語／客語需自建能力。

禁止：把國語模型結果冒充臺語／客語完整支援。

ADR-007｜EventBridge＋SQS＋Outbox

狀態：Accepted。

原因：避免雙寫、Consumer 解耦、可重試。

代價：最終一致與重複事件，需要冪等。

ADR-008｜Step Functions 只處理長流程

狀態：Accepted。

原因：人工等待、刪除與報表需要可視化；語音主路徑要求低延遲。

ADR-009｜Cognito Role＋Core ABAC

狀態：Accepted。

原因：身份與業務授權分離。

禁止：只靠 Cognito Group 判斷可查看哪位長者。

ADR-010｜完整規劃、三階段部署

狀態：Accepted。

階段 A：核心 Vertical Slice。

階段 B：居服與家屬報表。

階段 C：完整主動陪伴、治理與 Production Hardening。

# 二十一、成本控制

• Bedrock：限制最大 Token、Context、工具次數與重試；不同任務使用不同 Quality Tier。

• SageMaker：Demo 前啟動、Demo 後關閉非必要 Endpoint；記錄每語言每分鐘成本。

• OpenSearch／Neptune：先做最低容量與使用量 Spike，再決定常駐或展示時開啟。

• NAT Gateway：評估 VPC Endpoint 與流量成本，不因「Serverless」假設免費。

• CloudWatch：設定 Log Retention，禁止 Debug Prompt 永久保存。

• S3：Lifecycle 移除短期 Audio 與中間檔。

• Budgets：依 dev／demo／prod 設日、週、月告警。

# 二十二、恢復與降級

• Bedrock／AgentCore 失敗：固定安全回覆＋稍後再試；正式資料不受影響。

• Transcribe 失敗：切換自建 ASR 或要求重說；不產生正式事件。

• Custom ASR 失敗：可在國語 Session 降級 Transcribe；臺語／客語需明確告知目前無法辨識。

• TTS 失敗：顯示文字。

• Neptune 失敗：Aurora Memory／Relationship Query 降級，Outbox 後續重放。

• OpenSearch 失敗：精確 ID／日期查詢回 Aurora，RAG 回覆暫停或顯示來源不可用。

• LINE／SES 失敗：App 報表仍可讀，SQS 重試。

• Step Functions 失敗：保留 Execution、進 DLQ／Manual Action，不把部分成功標成完成。

• Region 故障：v0.1 先以 Aurora Backup、S3 Versioning、IaC 重建達成 RTO／RPO；跨 Region Active-Active 不在第一版。

# 二十三、技術 Spike 清單

SP-01｜候選 Region 服務共同可用性與 RTT。

SP-02｜Transcribe zh-TW 長者語音、專有詞與混語 CER／Latency。

SP-03｜Taiwan Tongues ASR 部署 SageMaker GPU、冷啟動、串流方式與成本。

SP-04｜Polly 國語長者可懂度；臺語／客語 TTS 替代。

SP-05｜AgentCore Runtime＋Gateway＋Python Core Tool Authorization。

SP-06｜Bedrock Guardrails 對臺語／繁中輸入輸出效果。

SP-07｜Aurora Outbox → EventBridge 的可靠發布與重送。

SP-08｜Neptune Serverless 最低成本、Graph Query 與 Projection Recovery。

SP-09｜OpenSearch Serverless Hybrid Search＋Metadata Filter＋Rerank。

SP-10｜Bedrock Knowledge Bases 是否保留自訂 Chunk／Review Metadata。

SP-11｜LINE Secure Link、Recipient Binding、Withdraw 失效。

SP-12｜完整 Voice Trace p95 是否達 05／07 基準。

# 二十四、v0.1 完成判定

□ Target Architecture 已涵蓋三類前端、語音、Agent、Workflow、Domain、Graph、RAG、報表與通知。

□ Aurora／Neptune／OpenSearch／S3／Cache 的責任清楚且無雙重事實來源。

□ 國語與臺語／客語的 Managed／Custom 路由及限制已明確。

□ 同步與非同步流程、Outbox、EventBridge、SQS、DLQ、Step Functions 與 Scheduler 已定位。

□ Cognito 身份與 Core ABAC 授權已分離。

□ AgentCore／Bedrock／Guardrails 與 Domain State 邊界已定義。

□ Target、Hackathon、Production Hardening 的實作層級已區分。

□ 10 個 ADR 已記錄原因、代價與退場方案。

□ Region、成本與 12 項技術 Spike 尚未驗證處均有標記。

□ 第一條 Demo 可從語音一路展示到記憶、Graph、照護端及家屬通知。

# 二十五、官方技術參考（檢查日期：2026-07-26）

Amazon Bedrock AgentCore Release Notes

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html

AgentCore Harness vs Runtime

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/harness-vs-runtime.html

AgentCore Observability

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-service-provided.html

Amazon Transcribe Supported Languages

https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html

Amazon Transcribe Streaming

https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html

Amazon Transcribe zh-TW Character Sets

https://docs.aws.amazon.com/transcribe/latest/dg/charsets.html

Amazon Polly Available Voices

https://docs.aws.amazon.com/polly/latest/dg/available-voices.html

Amazon SageMaker AI Real-Time Inference

https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints.html

API Gateway WebSocket APIs

https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-websocket-api-overview.html

Amazon Cognito User Pools

https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools.html

Amazon ECS on AWS Fargate

https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html

Aurora Serverless v2

https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Concepts.Aurora_Fea_Regions_DBEng.Feature.ServerlessV2.html

Amazon Neptune Serverless

https://docs.aws.amazon.com/neptune/latest/userguide/neptune-serverless.html

Amazon OpenSearch Serverless

https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless.html

OpenSearch Serverless Vector Search

https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-vector-search.html

Amazon Bedrock Knowledge Bases

https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html

Amazon Bedrock Guardrails

https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html

EventBridge and Step Functions

https://docs.aws.amazon.com/step-functions/latest/dg/connect-eventbridge.html

EventBridge Scheduler

https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html

Amazon SQS Dead-Letter Queues

https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html

AWS Secrets Manager Encryption

https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html

# 二十六、下一份文件

09｜智慧長照 AI 陪伴系統－Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

09 文件將根據 05～08 定義：

• Agent 清單、Owner、目標、輸入輸出與禁止事項。

• Orchestrator、Specialist Agent、Evaluator 與確定性程式的責任。

• Tool Allowlist、Tool Schema、Approval Gate 與 AgentCore Gateway 設計。

• Session Memory、確認式長期記憶、RAG、Graph 與照護 Context 組裝順序。

• Multi-Agent Handoff、Loop、終止條件、成本與延遲 Budget。

• Prompt、Model、Policy、Evaluation Dataset 與 Agent Trace 版本治理。
