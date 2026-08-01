# 14智慧長照 AI 陪伴系統－Observability、營運與 Incident Response v0.1.docx

智慧長照 AI 陪伴系統－Observability、營運與 Incident Response v0.1

### 文件資訊

版本：v0.1

狀態：Draft｜Python Backend、AgentCore、語音、RAG、Graph、報表與事件驅動系統的營運基準，待實測流量、Owner、通報管道與正式 SLO 核准

建立日期：2026-07-26

文件 Owner：Platform／Operations Owner

審查者：五人團隊

適用範圍：Python Core API、長者語音、Agent Runtime、Aurora PostgreSQL、EventBridge、SQS／DLQ、Step Functions、OpenSearch、Neptune、S3、Cognito、家屬報表、LINE／Email、CI／CD 與安全事件

### 相關文件

07｜Security、Privacy、NFR 與 Threat Model v0.1

https://docs.google.com/document/d/1UUnrs6FUCqlaNxaDm12zPVFAPfQG0ruWqdiL0HXvTrI/edit

08｜AWS 系統架構、服務選型與 ADR v0.1

https://docs.google.com/document/d/136qR8PhU8v-vckak286q_2Ln3otQ0KRExTDvAO3_sAE/edit

09｜Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit

10｜API、Event、Tool 與 Data Contracts v0.1

https://docs.google.com/document/d/1s2iM5Yue8WdpVa04DmQm-F_jTkHrPVaSW5ZaFFXD1bA/edit

11｜測試策略、Agent Evaluation 與品質門檻 v0.1

https://docs.google.com/document/d/1saeohikZZ63P2ud1YNHMQDKBKX2wgVnMsQ3LPTAD2qY/edit

12｜實作計畫、環境、團隊分工與交付路線 v0.1

https://docs.google.com/document/d/1OGa9igfGHILGPJE3PmvynP23LxA9FPsT8jPO_R-SG9o/edit

13｜Database Migration、Release 與 Rollback v0.1

https://docs.google.com/document/d/1UC7AmwYJY8fWxgF-69yKqoplRD519KfvjMz2ck16jOU/edit

## 一、文件目的與營運原則

本文件將 07 的安全／NFR、08 的 AWS 架構、09 的 Agent Trace、11 的品質門檻與 13 的發布／復原流程，轉成每天可以執行的監控、告警、值班、事件處理、Runbook、容量、成本與改善機制。

營運目標不是收集最多 Log，而是能快速回答：

1. 哪位使用者、哪個 tenant、哪位長者、哪條工作流受到影響？

2. 問題發生在哪一段：裝置、API、ASR、Agent、Tool、RAG、Database、Queue、Graph、通知或外部服務？

3. 是否涉及安全、隱私、Consent、跨長者或錯誤發布？

4. 目前應降級、關閉 Feature、切換 Provider、重試、Replay、Rollback 還是進人工處理？

5. 從偵測到回復花了多久，如何防止再次發生？

核心原則：

• User Journey First：先監控長者對話、照護者覆核、家屬讀報等完整體驗，不只看單一資源 CPU。

• Trace Everything Important：以 trace_id／workflow_instance_id 串起同步與非同步流程。

• Privacy by Default：日誌只保存排障所需最小欄位，不保存完整語音、逐字稿、Token、Secure Link 或不必要 Prompt。

• Symptoms Before Causes：先以可用性、延遲、錯誤率、資料新鮮度與安全結果告警，再用資源指標找原因。

• Actionable Alert Only：每個告警需有 Owner、Severity、Runbook、Dashboard、抑制與解除條件。

• Fail Safe：可觀測性故障不能使安全 Gate 失效；高風險路徑在 Safety／Authorization 不可判斷時 Fail Closed。

• Projection Is Rebuildable：Graph、Search、Cache 出錯時優先降級與重建，不改寫 Aurora 正式事實。

• Incident Evidence Is Immutable：事件時間線、關鍵決策與證據需保存，普通 Debug Log 可依期限刪除。

## 二、Observability Architecture

### 2.1 遙測來源

Client／PWA

→ page_view、voice_start、voice_cancel、network_status、playback_result、frontend_error

API Gateway／CloudFront／WAF／Cognito

→ request_count、latency、4xx、5xx、throttle、auth_failure、WAF block

Python Core API on ECS Fargate

→ structured log、custom metric、OpenTelemetry trace、business event、audit event

AgentCore／Bedrock

→ session、agent run、model invocation、tool call、memory／gateway operation、token、latency、error、safety result

Speech Layer

→ ASR route、language、audio duration、final latency、confidence band、confirmation result、TTS first audio、provider error

Data／Workflow

→ Aurora、Outbox、EventBridge、SQS／DLQ、Step Functions、S3、OpenSearch、Neptune、Scheduler

External Adapter

→ LINE／Email request、accepted、delivered／failed、provider status、secure link open

### 2.2 遙測後端

• CloudWatch Logs：應用程式、Worker、Agent、Audit 與 AWS Service Logs。

• CloudWatch Metrics：AWS 原生與 EMF／PutMetricData 自訂指標。

• OpenTelemetry／ADOT：Python API、Worker 與 Agent 的 Trace／Metric 標準化。

• AWS X-Ray／CloudWatch Transaction Search：分散式 Trace 與服務相依性。

• CloudWatch Application Signals：服務健康、依賴、流量、錯誤、延遲與 SLO；是否支援目前 Python 部署方式需在 Spike 驗證。

• CloudWatch GenAI Observability：AgentCore Agents、Sessions、Traces、Metrics 與 Evaluations。

• CloudTrail：AWS API 與控制平面稽核。

• S3 Audit Archive：需較長保存或事件證據的去識別／加密匯出。

• Security Hub／GuardDuty：正式環境安全發現與事件來源。

### 2.3 帳號與環境

Hackathon：同一 AWS Account 可用 dev／demo Stack、Log Group、Metric Dimension 與 KMS Key 分離。

Target：dev、staging、prod 分 Account；使用 CloudWatch 跨帳戶可觀測性／Observability Access Manager 將 telemetry 分享至 Monitoring Account。資料與 Secret 不跨環境混用。

## 三、統一識別與 Correlation

### 3.1 必要識別碼

trace_id

span_id

request_id

session_id

workflow_instance_id

agent_run_id

actor_id

actor_role

tenant_id

elder_id（必要時 Tokenize／Hash）

care_unit_id

assignment_id

report_id

event_id

memory_id

notification_id

consent_version

policy_version

release_id

service_name

environment

region

### 3.2 傳遞規則

• HTTP 使用標準 Trace Context header，並保留 request_id。

• WebSocket 建立 Session 後，所有 Client／Server Event 帶 session_id＋trace_id。

• Domain Event Envelope 帶 trace_id、event_id、aggregate_id、tenant_id、elder_id 與 producer version。

• SQS Message Attribute 保留 trace_id、event_type、event_version、tenant_id 與 retry_count。

• Step Functions execution input／name 保存 workflow_instance_id，不把 Restricted 內容塞進 execution name。

• Agent Handoff 保留 parent_run_id、context_manifest_id、tool_call_id 與 source_ids。

• LINE／Email Provider Message ID 對應 notification_id，但不把 elder_name 放進外部 Correlation Key。

### 3.3 Trace 邊界

完整長者語音 Trace：

PWA → API Gateway／WebSocket → Core Authorization／Consent → Speech Router → ASR → Low Confidence Gate → Orchestrator → Retrieval／Tool → Bedrock／Guardrail → Safety → TTS → Playback → Session Complete → EventBridge → Event／Memory Candidate Worker。

家屬報表 Trace：

Scheduler → Step Functions → Source Query → Summary／Report Agent → Share／Safety Gate → Review → Publish → Outbox → EventBridge → Notification Queue → LINE／SES → Secure Link Open。

## 四、Structured Logging Standard

### 4.1 共通 JSON 欄位

{

"timestamp": "ISO-8601 UTC",

"level": "INFO|WARN|ERROR|CRITICAL",

"service": "core-api",

"environment": "demo",

"release_id": "...",

"trace_id": "...",

"span_id": "...",

"request_id": "...",

"tenant_id": "...",

"elder_ref": "tokenized-or-null",

"actor_ref": "tokenized-or-null",

"action": "family_report.publish",

"resource_type": "family_report",

"resource_id": "...",

"result": "success|denied|failed|partial",

"reason_code": "...",

"latency_ms": 0,

"retry_count": 0,

"policy_version": "...",

"consent_version": "...",

"error_type": "...",

"safe_message": "..."

}

### 4.2 Log 類型

Application Log：程式狀態、依賴錯誤、性能與重試。

Business Operation Log：狀態轉移、工作流結果與資料版本。

Security Audit：登入、權限、Consent、分享、發布、刪除與高權限操作。

Agent Trace Log：Agent／Prompt／Model／Tool／Source／Safety 結果。

Data Pipeline Log：Outbox、Queue、Projection、RAG Ingestion、Backfill。

Deployment Log：release_id、image_digest、migration_head、traffic shift、rollback。

### 4.3 禁止紀錄

• 密碼、Access／Refresh Token、API Key、Secret、Private Key。

• Secure Link Token 明文與可直接重用 URL。

• 完整原始語音、完整逐字稿、完整 Prompt／Context、完整家屬報表。

• 不必要姓名、地址、電話、身份證、健康與用藥文字。

• 其他長者的 Context、Tool Result 或 Graph 子圖。

• Exception 中的 Database DSN、Authorization header、Request Body 明文。

### 4.4 Sanitization

• Logger Adapter 集中遮罩 token、authorization、cookie、email、phone、address、transcript、prompt、audio_url。

• 使用 allowlist 欄位，不以「事後刪除敏感欄位」作主要策略。

• 使用者輸入移除換行控制字元，避免 Log Injection。

• Stack Trace 只在內部 Log；前端只收到 error_id 與安全訊息。

• Log Sampling 不得抽掉安全拒絕、發布、刪除、Consent 與 Incident 證據。

## 五、Metric Taxonomy

### 5.1 RED／USE

服務採 RED：Rate、Errors、Duration。

資源採 USE：Utilization、Saturation、Errors。

### 5.2 Business／Safety Metrics

voice_session_started_total

voice_session_completed_total

voice_session_cancelled_total

low_confidence_confirmation_rate

care_event_candidate_created_total

care_event_verified_total

memory_confirmation_accept_rate

family_report_publish_success_total

family_report_withdraw_total

notification_delivery_success_rate

secure_link_open_success_rate

authorization_denied_total

consent_blocked_total

cross_elder_blocked_total

safety_blocked_total

prompt_injection_blocked_total

medical_boundary_blocked_total

proactive_trigger_blocked_total

### 5.3 API／Python Metrics

http_requests_total

http_errors_total

http_request_duration_ms

active_requests

db_pool_in_use

db_pool_wait_ms

python_process_cpu

python_process_memory

worker_task_duration

worker_task_failure

idempotency_conflict_total

optimistic_lock_conflict_total

### 5.4 Voice Metrics

asr_final_latency_ms

asr_error_rate

asr_timeout_rate

asr_confidence_band

language_route_total

language_route_fallback_total

audio_duration_seconds

tts_first_audio_latency_ms

tts_error_rate

playback_failure_rate

禁止將完整音訊或逐字稿作 Metric Dimension。

### 5.5 Agent／LLM Metrics

agent_session_total

agent_run_duration_ms

agent_error_rate

agent_max_step_terminated_total

tool_call_total

tool_call_error_rate

tool_call_denied_total

schema_validation_failure_rate

safety_rewrite_total

human_review_required_rate

input_tokens

output_tokens

cost_estimate

model_fallback_total

context_item_count

context_token_estimate

retrieval_grounding_rate

AgentCore 服務提供的 session、latency、duration、token、error 與 ActiveSessionCount 等指標可直接納入 CloudWatch；自訂 Domain Metric 需額外產生。

### 5.6 Event／Queue Metrics

outbox_unpublished_count

outbox_oldest_age_seconds

eventbridge_failed_invocations

sqs_visible_messages

sqs_not_visible_messages

sqs_oldest_message_age_seconds

dlq_message_count

consumer_success_rate

consumer_retry_rate

consumer_idempotent_duplicate_total

projection_lag_seconds

scheduler_missed_trigger_total

stepfunctions_failed_execution_total

stepfunctions_timed_out_total

stepfunctions_execution_duration

### 5.7 Data Metrics

Aurora：CPU、ACU、connections、freeable memory、storage、deadlock、replica lag、transaction duration、slow query。

OpenSearch：query latency、ingestion latency、index error、document count、rejected request、capacity／OCU。

Neptune：query latency、error、connection、capacity、projection version、source coverage。

S3：4xx／5xx、ingestion object count、lifecycle failure、unexpected public access finding。

### 5.8 Notification Metrics

notification_pending_age_seconds

notification_send_attempt_total

notification_provider_error_rate

notification_dead_letter_count

notification_duplicate_prevented_total

report_published_without_notification_total

通知失敗不降低 family_report 的 Published 可讀性指標，但需獨立告警。

## 六、Dashboard 設計

D-01｜Executive／Demo Health

• 核心體驗成功率。

• Voice E2E p50／p95。

• 家屬報表可用性。

• Incident／P0／P1 狀態。

• 今日成本與 Budget。

• 三位 Demo Persona 最新 E2E 結果。

D-02｜Voice Journey

• Session Started／Completed／Cancelled。

• ASR、LLM、TTS 各段延遲。

• Low Confidence、Fallback、Playback Failure。

• 語言路由分布。

• 失敗 Trace 連結。

D-03｜Agent／RAG／Graph

• Agent Sessions、Errors、Steps、Tool Calls、Tokens。

• Schema Failure、Safety Block、Human Review。

• Retrieval Grounding、No Result、Source Validity。

• Graph Query、Projection Lag、Fallback Rate。

D-04｜Core API／Database

• API Rate／Error／Latency。

• ECS Task、CPU、Memory、Restart。

• DB Connections、Pool Wait、Slow Query、Deadlock。

• Authorization／Consent Decision。

D-05｜Async Workflow

• Outbox Lag、EventBridge Failure。

• Queue Depth／Age、DLQ。

• Step Functions Failure／Timeout。

• Summary、Report、Deletion、Projection Workflow 狀態。

D-06｜Family Report／Notification

• Draft／Needs Review／Published／Withdrawn。

• Publish Latency、Share Scope Block。

• LINE／Email Success、Retry、DLQ。

• Secure Link Open、Expired、Revoked。

D-07｜Security／Privacy

• Login Failure、MFA、WAF Block。

• Cross-Tenant／Cross-Elder Denied。

• Prompt Injection、Unsafe Output、Tool Denied。

• Consent Revocation、Deletion Partial Failure。

• GuardDuty／Security Hub Findings。

D-08｜Release／Cost

• Release Version、Migration Head、Feature Flags。

• Error／Latency Before vs After Release。

• Canary／Synthetic Result。

• Bedrock、AgentCore、SageMaker、OpenSearch、Neptune、NAT、CloudWatch 成本趨勢。

## 七、SLO、SLI 與 Error Budget

### 7.1 v0.1 候選 SLO

SLO-01｜核心登入與正式資料讀取月可用性 ≥ 99.5%。

SLI：成功回應／有效請求，排除使用者輸入錯誤與已知維護窗口。

SLO-02｜專業照護首頁與長者詳情 API p95 ≤ 2.5 秒。

SLO-03｜家屬 PUBLISHED 報表頁 p95 ≤ 3 秒，可用性 ≥ 99.5%。

SLO-04｜語音停止後 ASR final p95 ≤ 5 秒。

SLO-05｜LLM 文字回覆 p95 ≤ 10 秒；TTS 首段 p95 ≤ 5 秒。

SLO-06｜PUBLISHED 報表在 App／Web 正式來源的生成成功率 ≥ 99%，通知另列 SLO。

SLO-07｜Outbox／主要 Queue 事件 99% 在 5 分鐘內開始處理；實際值待負載測試校準。

SLO-08｜跨長者洩漏、越權成功、Consent 繞過、Draft Report Exposure、危險醫療建議通過率＝0。

### 7.2 Error Budget

• 可用性 99.5% 的月 Error Budget 約為當月時間的 0.5%；正式核准後再作唯一依據。

• 若 7 日 Burn Rate 過高：停止非必要 Feature Release。

• 若 1 小時 Burn Rate 急速消耗：啟動 Incident 並降低流量／功能。

• 安全零容忍指標不使用 Error Budget；一次即事件。

### 7.3 SLO Review

每週檢查趨勢，每月檢查門檻與排除條件。不可透過改 Label、排除失敗流量或刪除資料讓 SLO 看起來通過。

## 八、Alert Design

### 8.1 Severity

P0／SEV-1｜立即處理

• 跨 tenant／elder 實際資料暴露。

• Token、Secret、金鑰或 Restricted 資料外洩。

• 家屬收到其他長者報表。

• 大規模服務全面不可用。

• 刪除／Consent 撤回後資料重新出現。

• Agent 執行未授權高風險 Command。

P1／SEV-2｜15 分鐘內確認

• 單一 tenant 敏感風險。

• 核心 Voice／Report 路徑大幅失敗。

• Aurora 不可用或資料完整性風險。

• DLQ 持續成長、Deletion Partial Failure。

• Prompt／Policy 變更造成危險輸出或越權。

P2／SEV-3｜工作時段處理

• 局部功能降級、Graph／Search 無法使用但有 Fallback。

• 通知大量延遲。

• 延遲超標、容量接近上限。

P3／SEV-4｜排入改善

• 單次非敏感錯誤、低影響噪音、Dashboard 缺口。

### 8.2 告警內容

alarm_name

severity

service／workflow

environment／region

symptom

current_value／threshold

started_at

affected_scope

trace／dashboard link

runbook link

owner

feature_flag／kill_switch

recent_release_id

不得在 Chat／Email 告警正文放長者姓名、地址、逐字稿或完整報表。

### 8.3 告警抑制

• Deployment Window 只能抑制預期噪音，不可抑制 Security、Cross-Elder、Consent 與 Data Integrity 告警。

• Parent Incident Active 時，使用 Composite Alarm 降低相同根因的子告警轟炸。

• 同一 Queue／Service 使用 Dedup Key 與 Cooldown。

• 告警解除需確認服務恢復，不因 Metric 缺資料自動視為正常。

### 8.4 通知路徑

CloudWatch Alarm／Log Alarm／AWS Health／Security Finding

→ EventBridge／AWS User Notifications／SNS

→ Email／Slack／Microsoft Teams（可用 Amazon Q Developer in chat applications）

→ Incident Channel／Ticket。

AWS Systems Manager Incident Manager 自 2025-11-07 起不再向新客戶開放，因此本專案不將其作為必要新依賴；採 CloudWatch＋EventBridge／SNS＋Chat／Ticket＋版本化 Runbook 的可替換模式。

## 九、Synthetic、Canary 與 Smoke Monitoring

### 9.1 Synthetics

• 公開首頁與 Login Redirect。

• API health／readiness。

• 家屬 PUBLISHED Report Test Persona。

• Secure Link 過期／撤銷 Negative Test。

• Cognito Login 測試帳號。

• 非敏感 Knowledge Search。

### 9.2 Voice Synthetic

完整語音自動測試成本高，採分層：

• 每 5～15 分鐘：API／Provider health。

• 每小時或發布後：固定合成短音檔 → ASR → Agent Safe Response → TTS Artifact。

• Demo 前：林阿嬤完整 E2E 連續 5 次。

### 9.3 Canary 安全

• 只使用 Test／Synthetic Persona。

• Canary Secret 放 Secrets Manager。

• Artifact Bucket 加密與短 Retention。

• Screenshot／HAR 不得含真實 Restricted 資料。

• Canary Failure 建立 trace_id 與 release_id。

## 十、Runbook 標準

每份 Runbook 包含：

runbook_id

service／workflow

owner／backup

severity

trigger／alarm

user impact

safety／privacy impact

prerequisites

quick diagnosis

containment／kill switch

recovery steps

verification

rollback／roll forward

communication template

evidence to preserve

exit criteria

last_drill_at

Runbook 操作要求：

• 指令可複製，但需環境、Account、Region 與 Resource 限制。

• 高風險寫入先 Dry Run。

• 不在 Runbook 寫 Secret。

• 每次實際使用後更新錯誤步驟與新證據。

## 十一、核心 Runbook Catalog

RB-OPS-01｜Core API 5xx／Latency

診斷：最近 Release、Task Health、CPU／Memory、DB Pool、Dependency Latency。

止血：停止 Canary、切回前版 Image、降低非核心流量、關閉高成本 Feature。

驗證：登入、Elder Detail、Report Page、Authorization Negative Test。

RB-OPS-02｜Aurora 連線／效能

診斷：connections、pool wait、slow query、lock、deadlock、storage、ACU。

止血：限制背景 Worker、降低 Batch、暫停 Backfill、擴容量、切 Read Path。

禁止：直接 kill 不明 Transaction 或手動改正式資料而無 Audit。

RB-OPS-03｜Outbox 未發布

診斷：publisher health、DB rows、EventBridge permission、idempotency。

止血：保留 Outbox、修復 Publisher、分批 Replay。

驗證：event_id 唯一、Consumer 無重複副作用。

RB-OPS-04｜SQS Backlog／DLQ

診斷：oldest age、consumer errors、schema version、poison message。

止血：停止 Producer 或降低頻率、擴 Consumer、隔離 Poison Message。

Replay 前重新檢查 Consent、Deletion Marker、Assignment、Resource Status 與 Consumer Version。

RB-OPS-05｜AgentCore／Bedrock Failure

診斷：Agent session、model invocation、tool、quota、throttle、Guardrail、region status。

止血：Model Route Fallback、固定安全回覆、關閉非必要 Agent、縮小 Context／Tool。

高風險功能無 Evaluator 時 Fail Closed。

RB-OPS-06｜ASR／TTS Failure

診斷：Provider、語言路由、audio format、duration、endpoint health、quota。

止血：國語 Managed／Custom 切換；臺語／客語失敗需明確告知，不冒充成功；TTS 失敗顯示文字。

RB-OPS-07｜Graph Projection Lag／Failure

止血：關閉 graph_retrieval，改查 Aurora／OpenSearch；保留 Outbox。

復原：修正 Worker → 依 source version 重建 → 比對 Node／Edge／Sample Query → 切回。

RB-OPS-08｜OpenSearch Ingestion／Query Failure

止血：正式 ID／日期查詢回 Aurora；Knowledge 回覆顯示來源暫不可用。

復原：切舊 Alias、重建新 Index、跑 Retrieval Eval 與 Metadata Isolation。

RB-OPS-09｜Family Notification Failure

確認 Report 仍 PUBLISHED 且 App 可讀；停止重複發送；檢查 Provider、Recipient、Rate Limit。

重試使用 notification_id 冪等；不可因通知失敗回滾 Report。

RB-OPS-10｜Consent Revocation／Deletion Partial Failure

立即阻擋新讀取與新處理；列出各 Deletion Job Item；停止相關 Scheduler／Retry；逐 Store 修復；保存 Tombstone；完成後驗證 RDS、S3、Graph、Index、Cache、Secure Link。

RB-OPS-11｜Cross-Elder／Cross-Tenant Exposure

立即 SEV-1：停用受影響 Route／Tool／Report／Tenant、撤銷 Session／Link、保存 Trace、確認範圍、修復 Filter／Policy、重跑隔離測試。未確認安全前不恢復。

RB-OPS-12｜Secret／Token Leakage

撤銷與 Rotation、停止外洩來源、掃描使用範圍、調查 CloudTrail／Access Log、更新 CI／Container／Docs，確認無 Restricted 資料一併外洩。

RB-OPS-13｜Prompt Injection／Unsafe Agent Output

停用 Agent／Tool／Prompt Bundle、切回前版、保存最小 Trace、擴充 Dataset、修正 Policy、重新跑 Medical／Isolation／Tool Negative Test。

RB-OPS-14｜Deployment／Migration Failure

依 13 文件停止切流量、判斷 App Rollback 或 Roll Forward；Migration 失敗不得手動標記成功；驗證 Schema、Event、Projection 與 Release Manifest。

RB-OPS-15｜Demo Day Failure

使用離線 Demo Seed、預錄音檔、固定 Safe Response、Graph Snapshot 與 Screenshot 作最後備援，但 ElderScope、Consent、未確認記憶隔離與安全阻擋不可 Mock。

## 十二、Incident Response Lifecycle

### 12.1 Prepare

• Owner、Backup、Incident Commander、Technical Lead、Security／Privacy Lead、Communication Lead。

• Dashboard、Alarm、Runbook、Feature Flag、Kill Switch、Access、Backup、Contact List。

• 每月至少一次桌上演練；Demo 前做完整故障演練。

### 12.2 Detect／Declare

• 告警、使用者回報、安全發現、異常 Metric 或測試失敗。

• 建立 incident_id、Severity、開始時間、影響、Commander、Channel 與 Timeline。

• 不等待 Root Cause 才宣告事件。

### 12.3 Triage

先判斷：

• 是否正在洩漏或持續破壞資料？

• 是否影響長者安全、家屬錯收或 Consent？

• 是否與最近 Release／Migration／Prompt／Policy 有關？

• 影響單一 Session、Elder、Tenant、Region 或全部？

### 12.4 Contain

可用 Kill Switch：

• proactive_companion off

• family_notification off

• graph_retrieval off

• knowledge_rag off

• custom_asr off

• agent_tool_write off

• family_share tenant／report revoke

• session／secure_link revoke

• tenant maintenance mode

### 12.5 Eradicate／Recover

修復程式、Policy、Secret、資料或依賴；選擇 Rollback、Roll Forward、Replay、Rebuild 或 Restore。恢復順序優先正式資料讀取與安全 Gate，再恢復 Agent、Graph、Search、通知與主動功能。

### 12.6 Validate

• 正向 E2E。

• Authorization／Consent／Cross-Elder Negative Test。

• Data Consistency Query。

• Queue／DLQ／Projection Lag。

• Security／Privacy Log Review。

• 觀察窗口無復發。

### 12.7 Communicate

內部更新包含：事實、影響、已採動作、下一次更新時間、未知項目。

對外通報需由指定 Owner／法務／合作機構決定；不猜測、不公開長者身份、不提前宣稱完全恢復。

### 12.8 Close／Postmortem

退出條件：影響停止、資料一致、安全驗證通過、Backlog 受控、Owner 同意。

重大事件 2～5 個工作日完成無責備 Postmortem。

## 十三、Incident Record

incident_id

severity

status

started_at／detected_at／declared_at／contained_at／resolved_at

incident_commander

technical_lead

security_privacy_lead

affected_services

affected_regions／environments

affected_tenant_count

affected_elder_count（必要時僅數量）

data_classification

user_impact

safety_impact

recent_release_id

alarm_ids

trace_ids

timeline[]

containment_actions

recovery_actions

root_cause

contributing_factors

detection_gap

follow_up_actions

owners／due_dates

communication_records

evidence_locations

## 十四、Postmortem 標準

1. 摘要與影響。

2. 精確時間線。

3. Root Cause 與促成因素。

4. 為何測試、監控或流程未提早阻擋。

5. 哪些控制有效。

6. 哪些手動步驟拖慢恢復。

7. 修復項目：Prevent、Detect、Contain、Recover。

8. 每項 Action 有 Owner、期限、Priority 與驗證方式。

9. 追蹤至完成，不因文件寫完就關閉。

禁止把「操作人員失誤」當唯一 Root Cause；應追查為何系統允許單一操作造成重大影響。

## 十五、營運節奏

每日

• 查看 P0／P1、核心 Dashboard、DLQ、Outbox Lag、Failed Workflow、Budget。

• 確認 Demo／Production Synthetics。

• 檢查前一日 Release 與 Error Trend。

每週

• SLO／Error Budget Review。

• Top Error／Slow Trace／Agent Failure／Safety Block Review。

• DLQ、Projection Lag、Notification Failure、Consent／Deletion Work Review。

• 成本與 Log Volume Review。

• 更新一份最常用 Runbook。

每月

• Incident／Near Miss Review。

• Access Review、Secret Rotation 狀態、Backup／Restore Evidence。

• Capacity Forecast、Quota、模型／Provider 可用性。

• Alarm Noise、漏報、誤報與 Owner 檢查。

• Security Dataset、Prompt Injection 與 Cross-Elder Regression。

每季／Pilot

• Restore Drill、Region／Provider Failure Game Day。

• 長者、照護者與家屬真實場域回饋。

• SLO／Retention／RTO／RPO／成本基準重新核准。

## 十六、容量、Quota 與 Backpressure

### 16.1 容量指標

• Concurrent Voice Session。

• API Request Rate。

• AgentCore ActiveSessionCount／Model TPS／Token。

• SageMaker Endpoint Invocation／GPU／Queue。

• Aurora Connections／ACU／Storage。

• SQS Queue Age／Consumer Throughput。

• OpenSearch／Neptune Capacity。

• Notification Provider Rate Limit。

### 16.2 Backpressure

• 限制每 actor／device／tenant 的 Voice Session。

• 最大錄音長度、Context、Tool Call、Agent Step、Token、Retry。

• Queue 高水位時暫停非核心 Summary／Analytics／Projection Rebuild。

• Report／Deletion 高優先於非必要 Insight。

• 主動陪伴在系統壓力、近期拒絕或通知事故時自動暫停。

• 不因 Consumer 落後無限制擴大 retry storm。

## 十七、成本可觀測性

### 17.1 成本維度

service、environment、tenant_class、feature、model_route、language、workflow、release_id。

不得以 elder_id 作成本 Tag 或高基數 Metric。

### 17.2 每日追蹤

• Bedrock Input／Output Token。

• AgentCore Session／Tool／Memory／Observability 使用量。

• SageMaker Endpoint Hours／Invocation。

• OpenSearch／Neptune Capacity。

• Aurora ACU／Storage／I/O。

• NAT／Data Transfer。

• CloudWatch Log Ingestion／Storage／Query／Alarm。

• S3 Storage／Request。

• Notification Delivery。

### 17.3 成本告警

• 日成本超過基準 150%。

• Token／Session 突增。

• 無流量但 Endpoint／Task／Collection 持續運作。

• Debug Log 或 Trace Volume 突增。

• Retry／DLQ 造成重複消耗。

• Demo 後未關閉非必要 GPU Endpoint。

成本異常先查錯誤 Loop、重試、模型路由與 Log Volume，不只提高 Budget。

## 十八、資料保存與 Observability Access

### 18.1 建議初始 Retention

Application Debug Log：14～30 日。

API Access Log：30～90 日。

Agent Operational Trace：30 日；敏感 Payload 預設不保存。

Security Audit：依法務／機構要求，初始候選 1 年以上，待核准。

Incident Evidence：依 Severity 與法律需求保存。

Metric：依趨勢需要保存，避免無限制高解析自訂 Metric。

Synthetics Artifact：7～30 日。

以上均為 v0.1 候選值，不代表正式法律期限。

### 18.2 Access

• Developer 只能讀取 dev／demo 普通 Log。

• Production Restricted Trace 需 JIT／Approval／Audit。

• Security Audit 與應用程式 Log 分開權限。

• 外部支援人員只取得去識別、必要範圍與限時存取。

• 下載／匯出 Incident Evidence 需記錄操作者、理由與期限。

## 十九、Monitoring as Code

Repository：

/infra/observability

/dashboards

/alarms

/synthetics

/log-policies

/metric-definitions

/runbooks

/incident-templates

要求：

• Dashboard、Alarm、Log Group、Retention、Metric Filter、Synthetics、SNS／EventBridge Route 透過 CDK／Terraform 版本化。

• PR 檢查 Alarm 有 Owner、Runbook、Severity、缺資料行為。

• Metric／Log Schema 變更需相容策略。

• Release 同時更新對應 Dashboard／Alarm／Runbook。

• 禁止只在 Console 手動建立關鍵 Alarm 而未回寫 IaC。

## 二十、Hackathon Implementation Profile

### 20.1 必做

• Python Core API 結構化 JSON Log。

• trace_id 串起 Voice → Agent → Event／Memory Candidate。

• CloudWatch Dashboard：Voice、Agent、API、Queue、Graph／Search、Report／Notification。

• AgentCore GenAI Observability 或相容 OTEL Trace。

• 至少 8 個可執行告警。

• 一條 SQS／DLQ 故障與 Redrive Demo。

• 一條 Graph Failure → Aurora Fallback。

• 一條 LINE／Email Failure 但 App Report 可讀。

• Cross-Elder／Consent／Safety 告警證據。

• Demo Health Check 與三位 Persona Synthetic／E2E 結果。

• Release／Migration／Feature Flag 顯示在 Dashboard。

• Demo Day Runbook 與 Kill Switch。

### 20.2 建議 8 個核心告警

1. Core API 5xx／Latency。

2. Voice E2E Failure／ASR Timeout。

3. Agent／Model Error 或 Max-Step。

4. Outbox Oldest Age。

5. SQS Oldest Age／DLQ > 0。

6. Aurora Connection／Pool Saturation。

7. Graph／Search Projection Lag。

8. Authorization／Consent／Cross-Elder／Safety Critical Event。

### 20.3 可延後

• 多 Account OAM 集中監控。

• 24×7 On-call 工具整合。

• Production 級 Security Incident Response 訂閱。

• 全自動 Remediation。

• 長期 Error Budget Automation。

### 20.4 不可省略

• Restricted 資料不得進普通 Log／Alert。

• 跨長者、Consent、Published Gate 的偵測與事件處理。

• Owner、Runbook 與 Kill Switch。

• DLQ／Retry／Replay 的 Consent 重新檢查。

• Incident Timeline 與 Release／Trace Correlation。

## 二十一、ADR

ADR-14-001｜CloudWatch＋OpenTelemetry／ADOT 為主要 Observability Baseline

狀態：Accepted。

原因：AWS 服務原生 Metric／Log、Python 自訂 Trace 與 AgentCore OTEL 可統一關聯，並保留未來輸出其他後端的能力。

ADR-14-002｜不把完整 Prompt／Transcript 當普通 Log

狀態：Accepted。

原因：長照語音與 Agent Context 高敏感；排障以 Manifest、Source ID、Version、Reason Code 與最小片段為主。

ADR-14-003｜以 User Journey SLO 驅動告警

狀態：Accepted。

原因：單一 CPU／Memory 正常不代表長者語音或家屬報表可用。

ADR-14-004｜安全零容忍事件不使用 Error Budget

狀態：Accepted。

原因：跨長者洩漏、越權、Consent 繞過與危險醫療輸出不能以平均值抵銷。

ADR-14-005｜Incident Manager 不作新專案必要依賴

狀態：Accepted。

原因：AWS Systems Manager Incident Manager 已停止向新客戶開放；採可替換的 CloudWatch／EventBridge／SNS／Chat／Ticket／Runbook 模式。

ADR-14-006｜Graph／Search 事故採降級與重建，不回滾 Aurora

狀態：Accepted。

原因：兩者為可重建投影，Aurora 才是正式事實來源。

ADR-14-007｜Monitoring Configuration 納入 IaC 與 Release

狀態：Accepted。

原因：告警、Dashboard、Retention 與 Runbook 必須可審查、重建與版本回查。

## 二十二、技術 Spike

SP-O01｜Python OpenTelemetry／ADOT on ECS Fargate 與 Trace Correlation。

SP-O02｜CloudWatch Application Signals 對目前 Python Runtime 的支援與成本。

SP-O03｜AgentCore Transaction Search、GenAI Dashboard、Prompt Trace 與自訂 Domain Span。

SP-O04｜WebSocket／Voice Trace 跨 Client、API、ASR、Agent、TTS。

SP-O05｜EMF／Custom Metric 的 Dimension 與高基數成本。

SP-O06｜CloudWatch Log Alarm、Composite Alarm、Anomaly Detection 與 Noise。

SP-O07｜Synthetics Secure Link／Report／Voice Canary。

SP-O08｜Cross-Account Observability／OAM 的 Target Account 設計。

SP-O09｜Security Hub／GuardDuty／CloudTrail 事件進 Incident Route。

SP-O10｜AWS Health EventBridge 與 Demo／Production 通知。

## 二十三、待決策

1. 正式 Monitoring Account 與跨 Account 模式。

2. Slack、Teams、Email 或其他 On-call 通報管道。

3. 五人團隊的 Incident Commander、Security Lead、Communication Lead。

4. 正式 SLO、Error Budget、RTO、RPO 與維護窗口。

5. Application Signals 是否納入 Python Core API。

6. Trace Sampling 與高風險 Trace 全保留規則。

7. 各類 Log、Audit、Incident Evidence 的正式 Retention。

8. Security Hub、GuardDuty、AWS Security Incident Response 的啟用層級。

9. LINE／Email Provider 的送達回報與告警能力。

10. Production 24×7 On-call 是否委外或由合作機構承擔。

## 二十四、v0.1 完成判定

□ Log、Metric、Trace、Audit、Agent Trace 與 Business Metric 已分層。

□ Correlation ID 與同步／非同步傳遞規則已定義。

□ 敏感資料禁止紀錄、遮罩、取樣與存取規則已定義。

□ Voice、Agent、API、Database、Queue、Graph、Search、Report、Notification Dashboard 已定義。

□ 初始 SLO、Error Budget 與安全零容忍指標已定義。

□ Severity、告警內容、抑制、通知與 Owner 規則已定義。

□ Synthetics、Smoke、Voice Canary 與 Demo E2E 已定義。

□ 至少 15 份 Runbook 範圍已定義。

□ Incident Prepare、Detect、Contain、Recover、Validate、Communicate、Postmortem 已定義。

□ 容量、Backpressure、Quota、成本與 Log 成本控制已定義。

□ Monitoring as Code、Hackathon Profile、ADR 與 Spike 已建立。

## 二十五、官方技術參考（檢查日期：2026-07-26）

CloudWatch Application Signals

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Monitoring-Sections.html

Application Signals API／SLO

https://docs.aws.amazon.com/applicationsignals/latest/APIReference/Welcome.html

AWS Distro for OpenTelemetry and X-Ray

https://docs.aws.amazon.com/xray/latest/devguide/xray-services-adot.html

AgentCore Observability

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html

AgentCore Generated Observability Data

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-service-provided.html

CloudWatch GenAI Observability

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AgentCore-Agents.html

View AgentCore Observability Data

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/view-observability-data-cloudwatch.html

CloudWatch Alarms

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Alarms.html

CloudWatch Alarm Events and EventBridge

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/cloudwatch-and-eventbridge.html

CloudWatch Log Alarms

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Alarm-On-Logs.html

CloudWatch Composite Alarms

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-combining.html

CloudWatch Synthetics

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Synthetics_Canaries.html

CloudWatch Cross-Account Observability

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Unified-Cross-Account.html

Amazon Q Developer in Chat Applications

https://docs.aws.amazon.com/chatbot/latest/adminguide/what-is.html

AWS Health Events on EventBridge

https://docs.aws.amazon.com/eventbridge/latest/ref/events-ref-health.html

AWS Systems Manager Incident Manager Availability Change

https://docs.aws.amazon.com/incident-manager/latest/userguide/incident-manager-availability-change.html

AWS Security Incident Response

https://docs.aws.amazon.com/security-ir/latest/userguide/people.html

## 二十六、下一份文件

15｜智慧長照 AI 陪伴系統－成功指標、Feedback、實驗與迭代 v0.1

15 文件將定義：

• North Star、產品、照護、AI、營運、安全與商業指標。

• 長者、照服員、居服員與家屬的 Feedback Loop。

• 事件、記憶、報表、主動陪伴與搜尋品質的實驗設計。

• A／B、Shadow、Canary、Human Review 與停止條件。

• 指標治理、資料偏差、虛榮指標、Guardrail Metric 與決策節奏。
