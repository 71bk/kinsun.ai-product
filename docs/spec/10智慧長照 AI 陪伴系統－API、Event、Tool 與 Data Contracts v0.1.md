智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1

## 文件資訊

版本：v0.1

狀態：Draft｜可開發 Contract 基準，待 OpenAPI、AsyncAPI、JSON Schema 與 Contract Test 實作驗證

建立日期：2026-07-26

文件 Owner：待團隊指定

審查者：五人團隊

適用範圍：REST API、WebSocket、Domain Event、Agent Handoff、Tool Contract、核心資料 Payload、錯誤碼、版本相容與測試

## 2026-08-14 Target Contract Overlay

依 [ADR 0013](../adr/0013-separate-account-elder-enrollment-entitlement.md)／[Spec 17](17智慧長照%20AI%20陪伴系統－Account、Elder、Enrollment%20與%20Service%20Entitlement%20v0.1.md)：

- 既有 `/elders/{elder_id}/...` resource ownership 可保留，但 Server 必須從可信 Auth Context 重新驗證 Membership、Enrollment、Relationship／Assignment、Consent 與 source Tenant。
- `POST /elders/{elder_id}/voice-sessions` Target contract 必須新增真實 initiator mode、authorization reference、service context 與 Entitlement check；Client 不得宣告可信 initiator／role／tenant。
- Target 新增 Organization／Household、Elder Enrollment、Service Entitlement、single-Elder offboarding 與 optional account-link resources；未進入 OpenAPI 與實作前不得視為已存在 endpoint。
- Authorization failure、Enrollment ended 與 Entitlement unavailable 必須是不同的內部 reason semantics，但對未授權 caller 不得洩漏 Elder 是否存在。
- 新增 event 候選：`ElderEnrollmentStarted`、`ElderEnrollmentEnded`、`ServiceEntitlementChanged`、`ElderAccountLinked`、`ElderAccountUnlinked`；event contract 必須先完成版本化與資料最小化審查。

## 相關文件

05｜核心工作流、狀態機與錯誤恢復 v0.1

https://docs.google.com/document/d/1fPZFY6Y7BEr6LnVOBVd7sRbmmAvUEutIS-HBesEOvoY/edit

06｜Domain Model、商業規則與資料生命週期 v0.1

https://docs.google.com/document/d/1B4dyCdiuAR7eR15cOgoQRZGsitcJN27Brgil58D4-J8/edit

07｜Security、Privacy、NFR 與 Threat Model v0.1

https://docs.google.com/document/d/1UUnrs6FUCqlaNxaDm12zPVFAPfQG0ruWqdiL0HXvTrI/edit

08｜AWS 系統架構、服務選型與 ADR v0.1

https://docs.google.com/document/d/136qR8PhU8v-vckak286q_2Ln3otQ0KRExTDvAO3_sAE/edit

09｜Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit

# 一、文件目的與使用方式

本文件把 05～09 的流程、Domain、安全、AWS 架構與 Agent 設計轉成可直接開發與測試的 Contract。它回答：前後端如何交換資料、事件如何跨服務傳遞、Agent 如何 Handoff、Tool 如何呼叫、錯誤如何表達、版本如何演進，以及哪些欄位不得遺漏。

本文件是邏輯 Contract Source of Truth；後續實作需產出：

• openapi.yaml：REST API。

• asyncapi.yaml：Domain Event、Queue 與 WebSocket Event。

• schemas/*.json：Entity、Command、Event、Tool、Agent Output。

• contracts/examples/*.json：正反例 Payload。

• Contract Test：Producer／Consumer、Schema、Authorization 與相容性測試。

Contract 不等於內部資料表。API 不直接暴露 Aurora Table、Neptune Node 或 OpenSearch Document 的完整結構；外部欄位只公開任務所需最小資訊。

# 二、Contract 設計原則

1. Contract First：先確認 Schema、狀態、錯誤與版本，再實作 Controller、Consumer 或 Agent。

2. Secure by Default：elder_id、tenant_id、purpose、consent_version 與 actor context 必須由受信任身份與 Core Policy 綁定，不能只相信 Client Body。

3. Candidate Before Fact：Agent 只可建立 Candidate／Draft，不可透過一般 Tool 直接建立正式記憶、正式事件或 Published 報表。

4. Idempotent Writes：所有建立、Command、Event Consumer 與通知工作都必須有 idempotency_key。

5. Optimistic Concurrency：可修改資源使用 version／ETag／If-Match，避免靜默覆蓋。

6. Explicit States：狀態不可由空值或布林組合隱含。

7. Unknown Is Not Normal：unknown、not_mentioned、insufficient_data、unavailable、failed 分開表達。

8. No Blind Dual Write：API 成功以 System of Record 交易為準；Graph、Search 與通知狀態透過 Event 更新。

9. Backward Compatible：同一 Major Version 只新增可選欄位，不刪除、不改型別、不改既有語意。

10. Traceable：每個 Request、Event、Tool、Agent Run 都可用 trace_id 串接。

# 三、命名、格式與版本慣例

## 3.1 命名

• JSON 欄位：snake_case。

• REST Resource：複數名詞、kebab-case 路徑。

• Event Type：dot notation，例如 care.event.verified.v1。

• Schema ID：PascalCase＋Version，例如 CareEventCandidateV1。

• 時間：ISO 8601 UTC，例如 2026-07-26T12:00:00Z。

• 日期：YYYY-MM-DD；時區另有 timezone，例如 Asia/Taipei。

• ID：不暴露遞增流水號，使用 UUID／ULID 類型字串。

## 3.2 API Version

Base Path：/api/v1

Major Version 只在 Breaking Change 時增加。Minor／Patch 由 Schema metadata 與部署版本管理，不寫入 URL。

## 3.3 Schema Metadata

每個主要 Payload 至少包含：

schema_name

schema_version

created_at

source_system

trace_id（適用時）

# 四、共用 HTTP Contract

## 4.1 Request Headers

Authorization: Bearer <JWT>

X-Request-Id: <client-generated-or-server-generated>

Idempotency-Key: <required-for-write>

If-Match: <resource-version-or-etag>（更新／高風險 Command）

Accept-Language: zh-TW／nan-TW／hak-TW／en

X-Client-Version: <app-version>

Client 不得自行指定可信 tenant_id／actor_role；Server 從 Token、Session 與 Policy Context 取得。Body 中的 elder_id 只作 Resource Target，仍需重新授權。

## 4.2 Success Envelope

{

"data": {},

"meta": {

"request_id": "req_...",

"trace_id": "tr_...",

"schema_version": "1.0",

"server_time": "2026-07-26T12:00:00Z"

}

}

## 4.3 List Envelope

{

"data": [],

"page": {

"next_cursor": "...",

"has_more": false,

"limit": 20

},

"meta": {}

}

## 4.4 Error Envelope

{

"error": {

"code": "AUTHORIZATION_DENIED",

"message": "無法存取此資源。",

"reason_code": "ELDER_SCOPE_MISMATCH",

"retryable": false,

"field_errors": [],

"safe_details": {},

"support_reference": "tr_..."

}

}

## 4.5 HTTP Status Mapping

400：VALIDATION_ERROR、INVALID_STATE_TRANSITION。

401：AUTHENTICATION_REQUIRED、TOKEN_EXPIRED。

403：AUTHORIZATION_DENIED、CONSENT_MISSING、PURPOSE_NOT_ALLOWED。

404：RESOURCE_NOT_FOUND；未授權時同樣可回 404，避免暴露存在性。

409：VERSION_CONFLICT、IDEMPOTENCY_CONFLICT、DATA_CONFLICT。

410：RESOURCE_WITHDRAWN、SECURE_LINK_EXPIRED、ASSIGNMENT_EXPIRED。

422：SCHEMA_SEMANTIC_ERROR、INSUFFICIENT_DATA。

429：RATE_LIMITED。

500：INTERNAL_ERROR。

502／503：DEPENDENCY_UNAVAILABLE。

504：DEPENDENCY_TIMEOUT。

## 4.6 Pagination／Filtering

採 cursor pagination，不使用可猜測 offset 處理敏感長者資料。

共用參數：limit、cursor、from、to、status、sort。

任何 filter 都不能擴大 Server 端授權範圍。

# 五、身份與目前 Context API

GET /api/v1/me

回傳 actor_id、角色、可見 tenant、care_unit 摘要與功能旗標；不回傳完整授權規則。

GET /api/v1/me/authorized-elders?mode=daycare|home-care|family

回傳目前可存取長者卡片。Server 依 role、care unit、assignment、relationship、share scope 與有效期間過濾。

GET /api/v1/elders/{elder_id}/access-context

用途：畫面進入前取得目前用途可用範圍。

回傳：purpose、allowed_actions、consent_summary、relationship／assignment summary、expires_at。

禁止：將此回應當永久授權快取；高風險 Command 必須重新驗證。

# 六、長者、同意與分享 API

## 6.1 長者摘要

GET /api/v1/elders/{elder_id}

回傳最小 Profile、語言偏好、介面偏好與可見狀態；依 Audience Redaction。

## 6.2 同意

GET /api/v1/elders/{elder_id}/consents

POST /api/v1/elders/{elder_id}/consents

POST /api/v1/elders/{elder_id}/consents/{consent_id}/revoke

Create Consent Request：

consent_type

purposes[]

share_scopes[]

effective_at

expires_at

actor_confirmation

policy_version

Revoke Consent Request：

reason_code

requested_effective_at

revoke_scope

request_deletion

回應必含 consent_id、consent_version、status、effective_at、affected_capabilities。

## 6.3 家屬分享

GET /api/v1/elders/{elder_id}/family-relationships

POST /api/v1/elders/{elder_id}/family-relationships/{relationship_id}/share-scopes

DELETE /api/v1/elders/{elder_id}/family-relationships/{relationship_id}/share-scopes/{scope_id}

任何分享擴大都需授權與長者同意；家屬本人不可自行擴大 scope。

# 七、語音 Session 與 WebSocket Contract

## 7.1 建立 Session

POST /api/v1/elders/{elder_id}/voice-sessions

Request：

language_preference

input_mode

client_audio_format

client_timezone

purpose

Response：

session_id

websocket_url／connection_token

max_recording_seconds

supported_audio_format

consent_version

expires_at

## 7.2 Session Command

POST /api/v1/voice-sessions/{session_id}/cancel

POST /api/v1/voice-sessions/{session_id}/retry

GET /api/v1/voice-sessions/{session_id}

## 7.3 WebSocket Client Events

client.audio.start

client.audio.chunk

client.audio.end

client.transcript.confirm

client.transcript.reject

client.playback.completed

client.cancel

client.ping

## 7.4 WebSocket Server Events

server.session.ready

server.asr.partial

server.asr.final

server.asr.low_confidence

server.agent.thinking_state

server.reply.text

server.tts.audio_chunk

server.tts.completed

server.session.completed

server.error

server.pong

## 7.5 WebSocket Event Envelope

{

"type": "server.asr.final",

"version": "1",

"session_id": "vs_...",

"sequence": 12,

"occurred_at": "...",

"trace_id": "...",

"payload": {}

}

sequence 必須單調遞增；Client 重連後以 last_sequence 恢復。原始音訊 Chunk Contract 由 Voice Spike 決定是 binary frame 或 signed upload，不在文字 JSON 內放 base64 大物件。

## 7.6 ASR Final Payload

transcript_id

text

language_code

model_version

confidence_band

critical_fields[]：field_type、value、confidence_band、needs_confirmation

is_final

# 八、Care Event API

## 8.1 候選建立

POST /api/v1/elders/{elder_id}/care-event-candidates

只供受控 Extractor Tool／背景 Consumer 呼叫。

Candidate Request：

source_type

source_id

source_version

event_type

event_time

structured_payload

evidence_refs[]

confidence_band

review_requirement

extractor_version

## 8.2 查詢與覆核

GET /api/v1/elders/{elder_id}/care-events?status=needs_review

GET /api/v1/elders/{elder_id}/care-events/{event_id}

POST /api/v1/elders/{elder_id}/care-events/{event_id}/review

Review Command：

decision：verify|correct|reject

reason_code

corrected_payload（decision=correct 時）

expected_version

Response：event_id、status、version、review_record_id、rebuild_required[]。

## 8.3 Care Event Contract

事件正式欄位：

event_id

elder_id

tenant_id

event_type

event_time

status

structured_payload

evidence_refs[]

source_ids[]

confidence_band

reviewed_by

reviewed_at

version

consent_version

created_at

updated_at

# 九、風險分級長期記憶 API

> 本節列出的 route 是既有目標 contract 基線；新 risk-tier、Speaker、version-bound confirmation 與
> retrieval Gate 以 [Spec 18](18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)
> 為準。實作前須做 OpenAPI impact review，不因本文件直接建立平行 endpoint。

GET /api/v1/elders/{elder_id}/memory-candidates

POST /api/v1/elders/{elder_id}/memory-candidates

POST /api/v1/elders/{elder_id}/memory-candidates/{candidate_id}/confirm

POST /api/v1/elders/{elder_id}/memory-candidates/{candidate_id}/reject

POST /api/v1/elders/{elder_id}/memory-candidates/{candidate_id}/defer

GET /api/v1/elders/{elder_id}/memories?status=active

PATCH /api/v1/elders/{elder_id}/memories/{memory_id}

DELETE /api/v1/elders/{elder_id}/memories/{memory_id}

Memory Candidate：

memory_type

memory_kind

normalized_content

source_ids[]

possible_conflict

conflict_with_memory_ids[]

confirmation_question

extractor_version

extraction_confidence

speaker_evidence_reference

content_digest

actual_risk_level（Core-owned；Agent risk hint 不具權威）

policy_decision

policy_version

Confirm Command：

elder_response_intent

confirmation_method

expected_candidate_version

expected_content_digest

consent_version

policy_version

speaker_evidence_reference

witness_evidence_reference（optional；witness 不取代 Elder consent）

正式 Memory：

memory_id

memory_type

content

status

source_ids[]

confirmed_by

confirmed_at

version

active_from

inactive_at

consent_version

verification_level

valid_from

valid_to

policy_version

注意：LOW all-of 通過後可由 Core 直接建立 ACTIVE；MEDIUM 才建立上述 Candidate 並逐筆確認；HIGH
不建立 Memory／Candidate content，只 MAY 留不含敏感原文的 minimal policy audit。每次 retrieval 仍須
重新驗證 current version、Consent、Speaker、verification、validity 與 scope。

graph_projection_status

未 Confirmed 不得出現在 ACTIVE Memory API 或 Context Builder。

# 十、摘要與照護待辦 API

## 10.1 Daily Summary

GET /api/v1/elders/{elder_id}/summaries?date=YYYY-MM-DD

POST /api/v1/elders/{elder_id}/summaries/rebuild

GET /api/v1/elders/{elder_id}/summaries/{summary_id}

Summary Contract：

summary_id

summary_date

summary_type：professional_daily

status

items[]：category、text、source_event_ids[]、data_status

missing_fields[]

conflict_flags[]

version

generated_by

reviewed_by

created_at

updated_at

## 10.2 Care Action

GET /api/v1/elders/{elder_id}/care-actions

POST /api/v1/elders/{elder_id}/care-actions

PATCH /api/v1/elders/{elder_id}/care-actions/{care_action_id}

Create Request：

title

description

source_event_ids[]

assignee_id

due_at

priority

expected_elder_scope

不得由 Care Insight Candidate 自動建立，必須由專業照護者確認。

# 十一、日照與居服派案 API

## 11.1 日照概覽

GET /api/v1/care-units/{care_unit_id}/elder-overview?date=YYYY-MM-DD

卡片欄位：elder_id、display_name、last_interaction_at、interaction_count、summary_status、pending_review_count、open_care_action_count。

禁止回傳診斷式排名或陪伴風險排行。

## 11.2 居服行程

GET /api/v1/home-care/assignments?date=YYYY-MM-DD

GET /api/v1/home-care/assignments/{assignment_id}

POST /api/v1/home-care/assignments/{assignment_id}/start

POST /api/v1/home-care/assignments/{assignment_id}/complete

Assignment Contract：

assignment_id

elder_id

provider_tenant_id

home_care_worker_id

service_type

scheduled_start

scheduled_end

status

allowed_data_scopes[]

version

expires_at

Complete Command：

service_record

observed_event_candidates[]

follow_up_items[]

expected_version

completed_at

派案失效或取消後，長者敏感詳情 API 應立即拒絕。

# 十二、家屬報表與通知 API

## 12.1 報表

GET /api/v1/family/elders

GET /api/v1/family/elders/{elder_id}/reports?type=daily|weekly|monthly

GET /api/v1/family/reports/{report_id}

內部流程：

POST /api/v1/internal/elders/{elder_id}/family-report-drafts

POST /api/v1/internal/family-reports/{report_id}/review

POST /api/v1/internal/family-reports/{report_id}/publish

POST /api/v1/internal/family-reports/{report_id}/withdraw

Family Report Contract：

report_id

elder_id

recipient_scope_ids[]

report_type

period_start

period_end

status

items[]：category、text、source_ids[]

data_gap_notice

sensitive_review_required

version

published_at

withdrawn_at

updated_at

只有 PUBLISHED 且 relationship、share_scope、consent 仍有效時可回傳。WITHDRAWN 回 410 或一般無法存取頁，不暴露內容。

## 12.2 通知設定

GET /api/v1/family/notification-preferences

PUT /api/v1/family/notification-preferences

Preference：

channels[]：line|email|in_app

frequency：daily|weekly|monthly|important_only

send_time_local

timezone

quiet_hours

important_event_enabled

status

## 12.3 Notification Delivery

POST /api/v1/internal/reports/{report_id}/notifications

GET /api/v1/internal/notifications/{notification_id}

通知只引用 report_id／version；LINE／Email 不保存另一份正式報表內容。

# 十三、同意撤回與刪除 API

POST /api/v1/elders/{elder_id}/deletion-requests

GET /api/v1/elders/{elder_id}/deletion-requests/{request_id}

POST /api/v1/internal/deletion-requests/{request_id}/retry-failed-items

Deletion Request：

scope[]：audio|transcript|events|summaries|memories|reports|graph|search|all_derived

reason_code

identity_reverified

consent_version

Deletion Status：

request_id

status

items[]：target_type、status、attempt_count、reason_code

started_at

completed_at

partial_failure

撤回同意成功後，停止新增處理不需等待 deletion job 完成。

# 十四、主動陪伴 API

GET /api/v1/elders/{elder_id}/proactive-companion/settings

PUT /api/v1/elders/{elder_id}/proactive-companion/settings

GET /api/v1/elders/{elder_id}/proactive-triggers

POST /api/v1/internal/elders/{elder_id}/proactive-triggers

POST /api/v1/internal/proactive-triggers/{trigger_id}/approve

POST /api/v1/internal/proactive-triggers/{trigger_id}/cancel

Trigger Contract：

trigger_id

source_type

source_id

topic_type

status

eligibility_result

blocked_reason

requires_approval

scheduled_at

expires_at

policy_version

version

Agent 只能 create_topic_candidate；schedule、approve、play 由確定性 Workflow 控制。

# 十五、Agent Handoff Contract

## 15.1 Handoff Envelope

request_id

trace_id

workflow_instance_id

session_id

actor_context

elder_scope

purpose

consent_version

policy_version

input_schema_name／version

output_schema_name／version

language

risk_level

context_manifest_id

allowed_tools[]

max_steps

latency_budget_ms

cost_budget_class

parent_agent

handoff_reason

created_at

expires_at

## 15.2 Handoff Result

agent_run_id

agent_id

agent_version

result_status

output

schema_validation

safety_flags[]

source_ids[]

tool_calls[]

stop_reason

latency_ms

token_usage

model_id

prompt_version

## 15.3 Result Status

SUCCESS

NEEDS_CLARIFICATION

BLOCKED

HUMAN_REVIEW

NO_DATA

SCHEMA_FAILED

DEPENDENCY_FAILED

TIME_BUDGET_EXCEEDED

COST_BUDGET_EXCEEDED

CANCELLED

# 十六、Tool Contract

## 16.1 共用 Tool Request

{

"tool_call_id": "tc_...",

"tool_name": "retrieve_confirmed_memory",

"tool_version": "1.0",

"actor_context": {},

"elder_scope": {},

"purpose": "conversation_reply",

"consent_version": 4,

"policy_version": "2026-07-26",

"request_id": "req_...",

"idempotency_key": "...",

"expected_resource_version": null,

"parameters": {}

}

## 16.2 共用 Tool Result

result_status

data

resource_id

resource_version

source_refs[]

reason_code

retryable

redactions[]

trace_id

## 16.3 Read Tools

read_session_context

retrieve_confirmed_memory

retrieve_verified_event

retrieve_daily_summary

knowledge_search

graph_subgraph

get_assignment_context

get_family_share_scope

read_policy

## 16.4 Candidate Write Tools

create_event_candidate

create_memory_candidate

create_summary_draft

create_family_report_draft

create_topic_candidate

create_care_insight_candidate

## 16.5 Command Tools

confirm_memory

review_event

publish_report

withdraw_report

send_notification

revoke_consent

create_deletion_request

create_care_action

Command Tool 一律由 Core API 二次授權、狀態與版本檢查。Agent Tool Allowlist 預設不得包含高風險 Command。

# 十七、Query Plan Contract

Query Planner Output：

query_plan_id

query_type：exact_transactional|keyword|vector|graph|hybrid|none

normalized_query

filters：tenant_id、elder_id、status、review_status、time_range、source_type、effective_period、risk_level

top_k

max_graph_hops

required_sources[]

fallback_order[]

grounding_required

reason

Query Plan 不含任意 SQL、Gremlin 或 OpenSearch DSL。Tool Translator 只能把允許欄位轉成預先定義 Template。

Retrieval Result：

query_plan_id

results[]：source_type、source_id、source_version、snippet_or_fact、score、status、effective_date

filters_applied

excluded_count

grounding_status

fallback_used

# 十八、Domain Event Envelope

## 18.1 共用 Envelope

{

"event_id": "evt_...",

"event_type": "care.event.verified.v1",

"event_version": "1.0",

"occurred_at": "2026-07-26T12:00:00Z",

"producer": "core-api",

"aggregate_type": "care_event",

"aggregate_id": "ce_...",

"aggregate_version": 3,

"tenant_id": "tn_...",

"elder_id": "el_...",

"actor_id": "ac_...",

"purpose": "care_record",

"consent_version": 4,

"trace_id": "tr_...",

"correlation_id": "wf_...",

"causation_id": "cmd_...",

"idempotency_key": "...",

"classification": "restricted",

"payload": {}

}

## 18.2 Event 規則

• event_id 全域唯一。

• Consumer 依 event_id 去重。

• Payload 不含完整音訊、完整逐字稿或 Secret。

• elder_id／tenant_id 適用時必填；知識庫事件可為 null，但需 source ownership。

• Event 不可被 Producer 修改；更正使用新 Event。

• event_version Major 變更才建立新 event_type suffix。

# 十九、Domain Event Catalog

conversation.session.completed.v1

Payload：session_id、transcript_version_id、language、completion_status、source_artifact_refs。

Consumers：Event Extractor、Memory Candidate、Metrics。

care.event.candidate.created.v1

Payload：candidate_id、event_type、source_ids、review_requirement。

Consumers：Care Review Queue、Audit。

care.event.verified.v1

Payload：event_id、event_type、event_time、version、source_ids。

Consumers：Summary、Graph Projection、Search Index、Care Insight。

care.event.corrected.v1

Payload：event_id、previous_version、new_version、changed_fields、source_ids。

Consumers：Summary Rebuild、Graph、Search、Report Staleness。

care.event.rejected.v1

Payload：event_id、reason_code、source_ids。

Consumers：Projection Removal、Summary Rebuild。

memory.candidate.created.v1

Payload：candidate_id、memory_type、source_ids、possible_conflict。

Consumers：Confirmation UI、Audit。

memory.confirmed.v1

Payload：memory_id、memory_type、version、source_ids。

Consumers：Graph Projection、Search／Context Cache Invalidation。

memory.deactivated.v1／memory.deleted.v1

Payload：memory_id、version、reason_code。

Consumers：Graph／Search Removal、Context Invalidation。

summary.ready.v1

Payload：summary_id、summary_date、version、status、source_event_ids。

Consumers：Professional UI、Family Report Eligibility。

family.report.published.v1

Payload：report_id、report_type、period、version、recipient_scope_ids。

Consumers：Notification Delivery、App Cache Invalidation、Audit。

family.report.withdrawn.v1

Payload：report_id、version、reason_code。

Consumers：Secure Link Revocation、App Cache Invalidation、Notification Cancellation。

notification.delivery.requested.v1

Payload：notification_id、report_id、report_version、recipient_id、channel、scheduled_at。

Consumers：LINE／Email Adapter。

notification.delivery.failed.v1

Payload：notification_id、channel、attempt_count、failure_class、retryable。

Consumers：Retry／DLQ Alarm；不得回滾 Report。

consent.revoked.v1

Payload：consent_id、consent_version、purposes[]、effective_at、request_deletion。

Consumers：所有相關 Workflow、Scheduler Cancellation、Secure Link Revocation、Deletion Coordinator。

assignment.changed.v1

Payload：assignment_id、elder_id、worker_id、status、effective_period、version。

Consumers：Home Care View、Authorization Cache Invalidation。

proactive.trigger.created.v1／blocked.v1／completed.v1

Payload：trigger_id、source_id、status、reason_code、policy_version。

Consumers：Scheduler、Caregiver Trace、Metrics。

deletion.requested.v1／deletion.completed.v1／deletion.partial_failed.v1

Payload：request_id、scope[]、item_summary、reason_code。

Consumers：Deletion Workers、Audit、User Status UI。

# 二十、Queue 與 Consumer Mapping

care-event-extraction：conversation.session.completed.v1

memory-candidate：conversation.session.completed.v1、care.event.verified.v1

summary-generation：care.event.verified／corrected／rejected.v1

memory-projection：memory.confirmed／deactivated／deleted.v1

search-indexing：care.event.*、memory.*、summary.*

family-report-generation：summary.ready.v1、scheduled report command

notification-delivery：notification.delivery.requested.v1

proactive-trigger：scheduler command、care event／memory eligible source

deletion-processing：consent.revoked.v1、deletion.requested.v1

每個 Queue 定義：visibility_timeout、max_receive_count、dlq_name、consumer_owner、schema_allowlist、alarm、redrive_runbook。

# 二十一、資料分類與欄位曝露

Public：公開法規與衛教來源 Metadata。

Internal：服務設定、非個資 Metrics。

Confidential：帳號、聯絡資訊、派案摘要。

Restricted：音訊、逐字稿、Care Event、Memory、家屬報表、同意與分享範圍。

Contract 規則：

• Restricted 欄位不得進 URL Query、Client Log、Metric Label 或通知預覽。

• Family API 不回傳 transcript_text、evidence_text、asr_confidence、agent_trace、internal_note。

• Agent Trace 只保存 source_id 與必要摘要，不保存其他 elder Context。

• Secure Link Token 只出現在 Header／Fragment 或一次性交換流程，不進一般日誌。

# 二十二、版本相容與 Deprecation

## 22.1 非 Breaking Change

• 新增可選欄位。

• 新增 Enum 值但 Consumer 必須有 UNKNOWN fallback。

• 新增 Event Type。

• 放寬文字長度但不改原語意。

## 22.2 Breaking Change

• 刪除或改名欄位。

• 型別改變。

• Required／Optional 改變造成舊 Client 失敗。

• 狀態或錯誤碼語意改變。

• Event Payload 拆分或合併。

## 22.3 Deprecation 流程

Draft → Announced → Dual Support → Deprecated → Removed。

每次需記錄 owner、replacement、announce_at、minimum_client_version、sunset_at、migration guide。

## 22.4 Consumer 規則

• 忽略未知可選欄位。

• 未知 Enum 映射 UNKNOWN，不直接 Crash。

• Producer 不得依賴 Consumer 未宣告支援的新欄位。

• Event Consumer 只接受 Allowlist Major Version。

# 二十三、Contract Repository 建議結構

/contracts

/openapi/openapi.yaml

/asyncapi/asyncapi.yaml

/schemas/common

/schemas/domain

/schemas/agent

/schemas/tools

/schemas/events

/examples/valid

/examples/invalid

/compatibility

/changelog

/backend

Contract Generated Types 或明確 DTO Mapping

/frontend

Generated Client＋手寫 View Model

/agent

Generated Pydantic／Typed Model

資料表 Entity、JPA Model、OpenSearch Document 與 API DTO 不直接共用同一 Class。

# 二十四、Contract Test 策略

## 24.1 Schema Test

• 所有 Example 通過對應 JSON Schema。

• Invalid Example 必須被拒絕。

• Required、Enum、Format、Max Length、Pattern 與 additionalProperties 策略測試。

## 24.2 API Test

• OpenAPI Request／Response Validation。

• Authorization／Consent／Purpose Negative Test。

• Idempotency Replay。

• If-Match Version Conflict。

• Family Redaction。

• Withdrawn／Expired／No Permission 不暴露存在性。

## 24.3 Event Test

• Producer Contract Test。

• Consumer Schema Allowlist。

• Duplicate Event Idempotency。

• Out-of-order Aggregate Version。

• DLQ 與 Redrive。

• Consent 撤回後等待中 Event 停止處理。

## 24.4 Tool／Agent Test

• 未列入 Allowlist Tool 被拒絕。

• Agent Output Schema 失敗最多修正一次。

• Agent 嘗試 confirm_memory／publish_report 被 Core 阻擋。

• Context Manifest 不含其他 elder_id。

• Query Planner 不可產生任意執行查詢。

## 24.5 Compatibility Test

以前一個 Released Contract 跑 Breaking Change Detection。CI 發現 Breaking Change 時，需升 Major 或提供 Migration。

# 二十五、Demo Contract Trace

Demo-01｜林阿嬤語音

voice-session create → WebSocket ASR final → Agent Handoff → reply → session completed event。

Demo-02｜事件與記憶

session completed event → event／memory candidate → review／confirm API → verified／confirmed event。

Demo-03｜Graph 引用

memory.confirmed event → projection consumer → graph_subgraph Tool → Companion Reply，Context Manifest 只有林阿嬤資料。

Demo-04｜照護端

care unit overview → elder detail → review event command → summary rebuild event。

Demo-05｜家屬

family report draft → review／publish → notification requested → LINE／Email → App 讀 Published Report。

Demo-06｜失敗恢復

通知失敗事件不回滾報表；Graph 失敗重放；Consent 撤回後安全連結失效。

# 二十六、Hackathon 必做 Contract

• /api/v1/voice-sessions 與主要 WebSocket Events。

• Care Event Candidate／Review。

• Memory Candidate／Confirm。

• ACTIVE Memory Read。

• 日照多長者 Overview。

• Family Report Read＋Published Gate。

• 一條 Notification Delivery Contract。

• Agent Handoff Envelope。

• Tool Request／Result Envelope 與 Allowlist。

• Domain Event Envelope＋至少六種 Event。

• 共用 Error Envelope。

• Idempotency、If-Match 與 Cross-Elder Negative Test。

可以分期但 Contract 先保留：居服完整服務紀錄、主動陪伴、Care Insight、完整刪除 Fan-out、客語模型路由。

# 二十七、ADR

## ADR-10-001｜REST API 採 /api/v1 Resource-oriented Contract

狀態：Accepted。

原因：角色共用、容易文件化與產生 Client。

## ADR-10-002｜WebSocket 只處理即時 Session 狀態與語音控制

狀態：Accepted。

原因：避免把一般 CRUD 與長流程混入長連線。

## ADR-10-003｜所有非同步訊息使用統一 Domain Event Envelope

狀態：Accepted。

原因：追蹤、去重、分類、版本與授權稽核一致。

## ADR-10-004｜Agent Handoff、Tool 與 Domain Payload 使用獨立 Schema

狀態：Accepted。

原因：模型輸出、工具呼叫與正式業務資料風險不同。

## ADR-10-005｜API DTO 不直接等於資料庫 Entity

狀態：Accepted。

原因：避免洩漏欄位與 Schema 綁死資料庫。

## ADR-10-006｜同一 Major Version 優先向後相容

狀態：Accepted。

原因：PWA、照護端、Agent Consumer 與背景 Worker 無法永遠同時部署。

# 二十八、v0.1 完成判定

□ REST、WebSocket、Event、Tool、Agent Handoff 與核心 Data Contract 都有共通 Envelope。

□ elder、consent、voice、event、memory、summary、assignment、report、notification、deletion、proactive trigger API 已定位。

□ Idempotency、If-Match、Cursor Pagination 與 Error Code 已定義。

□ Family、Professional、Elder Audience 的資料曝露邊界已定義。

□ Domain Event Catalog、Queue Mapping 與 Consumer Owner 欄位已定義。

□ 未確認記憶、未覆核事件與未發布報表不可透過 Contract 洩漏。

□ Agent Tool 不能直接繞過 Core Command Gate。

□ OpenAPI、AsyncAPI、JSON Schema 與 Contract Repository 結構已定義。

□ Producer／Consumer、Security、Compatibility 與 Negative Contract Test 已定義。

□ 第一條 Demo 從語音到 Graph、照護端與家屬通知可由 trace_id 串起。

# 二十九、待決策

1. WebSocket 原始音訊採 binary frame、直連 Speech Provider 或 S3 分段上傳？

2. Cursor Token 是否簽章及最長有效時間？

3. 內部 API 使用相同 Gateway Path、Private ALB 或獨立 Service-to-Service Endpoint？

4. Tool Gateway 使用 HTTP Tool、MCP 或混合模式？

5. Enum UNKNOWN 策略與各 Client SDK 產生器選擇？

6. Secure Link 是一次性 Token 交換、短效 JWT 或 Session Binding？

7. Event Schema Registry 使用 Repository＋CI，或另採 Managed Registry？

8. OpenAPI／AsyncAPI Generator 在 Java、TypeScript、Python 的選型？

9. Family Report Source References 是否只保留內部 ID，或顯示經整理來源標籤？

10. Voice Session 斷線後的 Resume Window 與 Audio Chunk 去重規則？

# 三十、下一份文件

11｜智慧長照 AI 陪伴系統－測試策略、Agent Evaluation 與品質門檻 v0.1

11 文件將定義：

• Unit、Integration、Contract、E2E、Security、Performance、Resilience 與 Accessibility Test。

• ASR／TTS、RAG、Graph、Agent、Summary、Family Report 與主動陪伴 Evaluation Dataset。

• CER、WER、NDCG、Grounding、Hallucination、Safety、Latency、Cost 與 Human Review 指標。

• Release Gate、Pass／Fail Threshold、Test Evidence 與 Demo Rehearsal。
