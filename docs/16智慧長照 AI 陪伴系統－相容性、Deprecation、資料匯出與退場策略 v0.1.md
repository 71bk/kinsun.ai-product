# 16智慧長照 AI 陪伴系統－相容性、Deprecation、資料匯出與退場策略 v0.1.docx

智慧長照 AI 陪伴系統－相容性、Deprecation、資料匯出與退場策略 v0.1

### 文件資訊

版本：v0.1

狀態：Draft｜完整 Target Product 的版本治理、資料可攜、Tenant Offboarding 與產品退場基準，待法務、合作機構、安全與正式保存期限核准

建立日期：2026-07-26

文件 Owner：Architecture／Data Governance／Platform Owner

審查者：五人團隊

適用範圍：Python Core API、Web／PWA、REST／WebSocket、Domain Event、Agent、Prompt、Model、ASR／TTS、RAG、Graph、Aurora PostgreSQL、S3、OpenSearch、Neptune、通知、Tenant、長者、家屬與營運資料

### 相關文件

06｜Domain Model、商業規則與資料生命週期 v0.1

https://docs.google.com/document/d/1B4dyCdiuAR7eR15cOgoQRZGsitcJN27Brgil58D4-J8/edit

07｜Security、Privacy、NFR 與 Threat Model v0.1

https://docs.google.com/document/d/1UUnrs6FUCqlaNxaDm12zPVFAPfQG0ruWqdiL0HXvTrI/edit

08｜AWS 系統架構、服務選型與 ADR v0.1

https://docs.google.com/document/d/136qR8PhU8v-vckak286q_2Ln3otQ0KRExTDvAO3_sAE/edit

09｜Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit

10｜API、Event、Tool 與 Data Contracts v0.1

https://docs.google.com/document/d/1s2iM5Yue8WdpVa04DmQm-F_jTkHrPVaSW5ZaFFXD1bA/edit

13｜Database Migration、Release 與 Rollback v0.1

https://docs.google.com/document/d/1UC7AmwYJY8fWxgF-69yKqoplRD519KfvjMz2ck16jOU/edit

14｜Observability、營運與 Incident Response v0.1

https://docs.google.com/document/d/1SUefwxwKMOQx4tH3avyrFq-DFlkzWpIpgBV3mKw5JiY/edit

15｜成功指標、Feedback、實驗與迭代 v0.1

https://docs.google.com/document/d/1cclA_-0cA4AHm8kjfKH5WQGduVOTHpQCAWbVm0ml3i0/edit

### 法律與治理聲明

本文件是產品與技術治理基準，不構成台灣醫療、長照、個資、勞動、契約或稅務法律意見。正式保存、匯出、刪除、法律保留與機構退場，需由法務、資安、照護專業與合作機構依實際資料類型及契約核准。

## 一、文件目的

本文件處理系統最容易在後期被忽略的四類問題：

1. 新版本如何不破壞舊 App、舊 Event、舊 Agent、舊資料與外部整合？

2. API、模型、Prompt、ASR、TTS、RAG、Graph 或 AWS 服務需要替換時，如何有時間窗與遷移路徑？

3. 長者、家屬或照護機構要求匯出、撤回同意、終止服務或刪除資料時，如何安全完成？

4. 團隊、供應商、Region、模型或整個產品停止服務時，如何保留必要證據並避免資料遺留？

核心目標不是永遠保留所有舊版本，而是讓每次改變都具備：

• 明確 Owner。

• 支援期限。

• 相容性分類。

• Migration Path。

• 可驗證的停止條件。

• 可追蹤的資料處置結果。

## 二、治理原則

• Compatibility Is a Product Feature：相容性不是只由 Backend 負責，會影響長者裝置、照護工作流、家屬連結與外部通知。

• Source of Truth First：Aurora 正式資料與版本紀錄優先；Graph、Search、Cache、Agent Memory 為可重建投影或工作記憶。

• Add Before Remove：先新增欄位、版本、Consumer 或 Provider，再遷移流量，最後移除舊路徑。

• Consumer Before Producer：事件新增或破壞性變更前，先讓 Consumer 能理解新舊格式。

• Explicit Deprecation：不使用「某天突然失效」的隱性退場。

• No Silent Meaning Change：同一欄位、狀態、Event Type、Tool 或 Prompt Version 不可在不改版本下改變語意。

• Export Is Not Database Dump：匯出需依角色、目的、資料分類與可理解格式設計。

• Deletion Is a Workflow：刪除涵蓋交易資料、S3、Graph、Index、Cache、Secure Link、通知、Eval Dataset 與衍生投影。

• Revocation Overrides Retry：同意撤回、分享失效與刪除 Tombstone 優先於 Queue Retry、DLQ Replay、Scheduler 與 Backfill。

• Evidence Before Destruction：正式刪除前保存合法且最小的稽核證據，不保留已要求刪除的實質內容。

• Portability Without Leakage：資料可攜不能導致其他長者、內部 Prompt、照護者私密筆記或系統 Secret 外洩。

• Complete Planning, Phased Execution：完整定義退場能力；黑客松只實作關鍵合約與一條可演示流程。

## 三、相容性分類

3.1 相容變更

通常可在同一 Major Version 中發布：

• 新增 Optional Request Field。

• 新增 Response Field，Client 可忽略未知欄位。

• 新增 Event Type。

• 新增 Event Payload Optional Field。

• 新增 Enum 值且 Consumer 有 UNKNOWN／default 處理。

• 新增 Tool，不改既有 Tool 語意。

• 新增 Prompt／Model Route Version 並保留舊版。

• 新增 Graph Edge／Node Type，舊 Query 不受影響。

3.2 條件相容

需先驗證 Client／Consumer 能力：

• 欄位由 Optional 變成實際業務必要，但仍接受舊 Client 缺省。

• Enum 新值可能改變 UI 或流程。

• 回應排序或分頁規則改變。

• ASR 信心分數尺度改變。

• Prompt 產出風格改變但 Schema 不變。

• RAG Ranking 或 Graph Query Planner 改變。

• 模型替換造成語言、Latency 或 Tool Calling 差異。

3.3 不相容變更

必須新 Major Version 或雙寫／雙讀遷移：

• 移除或重新命名必填欄位。

• 欄位型別、單位或語意改變。

• Event Type 重用不同意義。

• State Machine 合法轉移改變且舊資料無法解讀。

• Tool Input／Output Schema 破壞性變更。

• Actor、tenant_id、elder_id、assignment_id、consent_version 等安全欄位被移除。

• 家屬可見範圍改變。

• 記憶確認、事件覆核或報表發布 Gate 被改寫。

• Export 格式不再可讀或欄位消失。

## 四、版本識別標準

所有可部署或可交換元件需可識別版本：

app_version

api_version

event_version

schema_version

database_migration_head

agent_version

prompt_version

model_route_version

model_id／inference_profile

policy_version

guardrail_version

tool_schema_version

context_manifest_version

asr_route_version

asr_model_version

tts_route_version

tts_voice_version

rag_corpus_version

chunk_schema_version

embedding_model_version

search_index_version

graph_schema_version

graph_projection_version

export_schema_version

release_id

禁止只記錄「latest」。正式資料、Event、Agent Trace、Report、Export Manifest 與 Incident 都需能回查實際版本。

## 五、REST API 相容策略

5.1 路徑版本

公開與前端 API 採 Major Version 路徑：

/api/v1/...

/api/v2/...

Minor／Patch 變更透過相容欄位、Header 或行為修正完成。重大語意、權限、State 或 Schema 變更建立新 Major Version。

5.2 Client Capability

Client Request 可傳：

X-Client-Version

X-Platform

X-Capabilities

Accept-Language

X-Contract-Version

Server 不信任 Client 傳入 actor、tenant、elder 或 assignment scope；仍由 Token、Relationship、Assignment、Consent 與 Core ABAC 推導。

5.3 Response 規則

• Client 必須忽略未知欄位。

• Server 不隨意移除已發布欄位。

• Null、缺省與空集合語意明確區分。

• 日期時間使用 ISO-8601 與時區規則。

• Money／Duration／Confidence 等單位不可靜默變更。

• Error Code 保持穩定；safe_message 可改善但不可用於程式邏輯。

• Pagination Cursor 不承諾可被 Client 解碼。

5.4 API Support Window

v0.1 候選：

• Production Major API 至少支援目前版與前一個 Major Version。

• 重大安全缺陷可縮短支援窗，但需提供緊急通知與升級路徑。

• Hackathon／Demo API 不承諾長期支援，但需標記 demo_only 與移除日期。

正式天數待 Pilot 裝置更新能力與合作機構契約確認。

## 六、WebSocket／Voice Protocol 相容策略

• connect／session.start 先交換 protocol_version 與 capability。

• Server Event 有 event_type＋event_version。

• 新增 Event 不應使舊 Client 中斷；舊 Client可忽略非必要事件。

• audio format、sample rate、codec 與 chunk sequencing 明確版本化。

• asr.partial、asr.final、low_confidence.required、response.text.delta、tts.ready、session.completed 的必要欄位不可靜默改語意。

• Server 不向舊 Client 發送其無法理解且會影響安全的流程；必要時要求升級。

• Resume Token 有版本、TTL、session_id 與 scope，不跨 Major Protocol 使用。

• 不在 WebSocket Message 暴露內部 Agent Trace、Prompt、其他長者 Context 或 Provider Secret。

## 七、Domain Event 相容策略

7.1 Event Envelope 穩定欄位

至少保留：

event_id

event_type

event_version

occurred_at

producer

aggregate_type

aggregate_id

aggregate_version

tenant_id

elder_id

trace_id

workflow_instance_id

correlation_id

causation_id

consent_version

policy_version

data_classification

payload

7.2 演進規則

• Event 已發布即視為不可變歷史契約。

• 同一 event_type 的破壞性 Payload 變更提高 event_version。

• Consumer 先支援新舊版本，Producer 才切換。

• 無法處理的版本進 Quarantine／DLQ，不可默默忽略正式狀態事件。

• Replay 時以原始 event_version 解讀，不用最新 Schema 強行覆蓋。

• Event Upcaster／Translator 需純函式、可測試、有版本與失敗處理。

• 大型或 Restricted Payload 使用安全 Pointer，不將完整語音、逐字稿或報表塞入 Event Bus。

7.3 Event Retirement

停用 Event 前需確認：

□ 無 Producer。

□ 無 Active Consumer。

□ 無 Scheduled Replay／Backfill。

□ Audit 與歷史重播仍可解讀。

□ Replacement Event 已文件化。

□ Dashboard／Alarm／Runbook 已更新。

## 八、JSON Schema、OpenAPI 與 AsyncAPI

• OpenAPI 3.1 描述 REST API。

• AsyncAPI 描述 Event 與 WebSocket Channel。

• JSON Schema 為 Agent Handoff、Tool、Candidate、Export Manifest 與 Domain Event 的機器可驗證契約。

• Schema 存於 Repository，具 Owner、status、version、compatibility test。

• CI 檢查欄位移除、型別改變、required 變化、Enum 破壞與範例有效性。

• Runtime 仍執行 Schema Validation，不能只依文件。

Schema 狀態：

DRAFT

→ REVIEW

→ PUBLISHED

→ DEPRECATED

→ RETIRED

## 九、Database Schema 相容策略

依 13 文件採 Expand → Migrate → Contract：

1. Expand：新增欄位／表／Index，不立即刪舊欄位。

2. Dual Read／Write：必要時同時維護舊新表示。

3. Backfill：可重跑、具 Checkpoint、Idempotency 與 Data Validation。

4. Switch Read：Feature Flag／Release 切到新欄位。

5. Observe：確認 Error、Lag、資料一致與 Rollback Window。

6. Contract：確認無舊 Client／Job／Query 後才移除。

Database Rollback 不等同把 Migration 反向執行。已寫入正式資料的破壞性變更優先 Roll Forward、Data Repair 或 Snapshot Restore。

## 十、Agent、Prompt 與 Tool 相容策略

10.1 Agent Contract

Agent 版本至少綁定：

• input_schema_version。

• output_schema_version。

• allowed_tools。

• max_steps。

• risk policy。

• context_manifest_version。

• prompt_version。

• model_route_version。

10.2 Prompt

• Prompt 以不可變 Version 發布，不覆蓋已發布版本。

• 修改 System Policy、Output Schema、Tool 說明或安全邊界需新 Version。

• 舊 Prompt 保留至 Active Session、Replay、Incident 與回歸驗證不再需要。

• Prompt Deprecation 需替代版本、Dataset 結果、已知差異與 Rollback。

10.3 Tool

• Tool 名稱＋Major Version 為穩定識別，例如 get_verified_events.v1。

• 破壞性 Input／Output 改變建立 v2，不重用 v1。

• 高風險 Tool 仍由 Python Core API 重做 Authorization、Consent、State 與 Idempotency。

• Tool Retirement 前確認無 Prompt、Agent、Workflow、Eval Dataset 或 Runbook 引用。

10.4 Agent Session

已開始 Session 預設固定 Agent／Prompt／Model Route Bundle。除安全緊急切換外，不在同一 Session 中途切換造成語意不一致。

## 十一、Model Lifecycle 與替換

Amazon Bedrock 模型可能處於 Active、Legacy 或 End-of-Life 狀態；系統需定期讀取模型生命週期與官方通知，不把模型 ID 永久硬編碼。

11.1 Model Registry

model_alias

provider

model_id／inference_profile

lifecycle_status

region

capabilities

context_window

tool_use_support

languages

risk_approval

prompt_compatibility

embedding_dimension（如適用）

activated_at

deprecation_notice_at

last_supported_at

fallback_model

owner

11.2 替換流程

Discover Notice

→ Assess Capability／Region／Cost／Risk

→ Offline Regression

→ Shadow

→ Synthetic Canary

→ Limited Tenant Rollout

→ Compare Quality／Safety／Latency／Cost

→ Switch Alias

→ Monitor

→ Retire Old Model

11.3 不可直接替換的情況

• Embedding 維度或語意空間改變。

• Tool Calling Schema／格式不同。

• 語言或臺語／混語品質下降。

• Safety／Guardrail 行為不一致。

• 長期 Report、Memory 或 Event 需要版本重現。

Embedding Model 替換需建立新 Index／Collection、重新向量化、Alias 切換與 Retrieval Eval，不在原 Index 混合不同向量空間。

## 十二、ASR／TTS 相容與退場

12.1 Speech Router

外部介面使用穩定 Speech Contract，Provider 細節藏在 Router 後：

language

locale

audio_format

sample_rate

channel_count

confidence_band

transcript_segments

provider_route

model_version

fallback_reason

12.2 ASR 替換

• Managed zh-TW、Custom ASR、臺語／客語模型分開評估。

• 比較 CER／WER、Key Entity、False High Confidence、Latency 與長者任務完成。

• Confidence 分數不可跨模型直接比較，需校準成統一 Band 或 Model-specific Threshold。

• 轉換期間保存 route_version 與 model_version。

• Provider 失效可降級為替代 ASR、重新錄音或文字輸入，不冒充辨識成功。

12.3 TTS 替換

• Voice ID、語速、語言、發音字典與輸出格式版本化。

• 替換需做長者可理解度與專有名詞測試。

• TTS 失敗可顯示文字；不可因切換 Provider 產生未授權的聲音複製或人格誤導。

## 十三、RAG、Search 與 Knowledge Corpus 演進

13.1 Corpus Version

每次 Ingestion 保存：

corpus_version

source_id

source_version

publish_agency

effective_date

review_status

chunk_schema_version

embedding_model_version

index_version

ingested_at

13.2 Chunk／Metadata 變更

• 新 Chunk 規則建立新 corpus_version。

• 不覆寫舊 Chunk 而無來源對照。

• Metadata 欄位改變需 Backfill 與 Filter Regression。

• review_status、effective_date、persona_restriction、risk_level 等安全篩選不可在遷移期間缺失。

13.3 Search Index Retirement

Build New Index

→ Backfill

→ Compare Counts／Sample／Metadata

→ Retrieval Eval

→ Shadow Query

→ Alias Switch

→ Observe

→ Retain Rollback Window

→ Delete Old Index

正式 ID、Consent、Assignment 與報表狀態仍以 Aurora 為準，不因 Search Index 退場而遺失正式資料。

## 十四、Graph Schema 與 Projection 演進

• Neptune 為已確認關係／記憶／事件的 Projection，不是授權或正式事實來源。

• Node Label、Edge Type、Property 與 source_version 版本化。

• 新 Edge 可先雙寫；Query Planner 支援新舊 Graph Schema。

• ACTIVE、CONFIRMED、VERIFIED 狀態條件不可在遷移期間放寬。

• 刪除、撤回或停用先在 Core Permission Gate 阻擋，再非同步清理 Graph。

• Graph 重建使用 Aurora＋Outbox／Projection Record，不從舊 Graph 猜正式事實。

• Graph Schema Retirement 前確認 Query、Agent、Eval Dataset 與 Dashboard 已切換。

## 十五、Feature Flag Lifecycle

Feature Flag 狀態：

PROPOSED

→ DEVELOPMENT

→ INTERNAL

→ PILOT

→ GENERAL

→ DEPRECATION_PLANNED

→ DISABLED

→ REMOVED

每個 Flag 需：

flag_key

owner

purpose

scope

default_value

created_at

expiry_date

risk_level

kill_switch

linked_experiment

linked_release

removal_issue

規則：

• 安全 Gate、Consent、Authorization 不得永久依賴臨時 Flag。

• General Release 後移除不再需要的分支。

• 到期 Flag 在 CI／Dashboard 告警。

• Flag Disabled 不代表程式碼已移除。

• 沒有 Owner、Expiry、Migration Path 的 Flag 不得進 Production。

## 十六、Deprecation Lifecycle

16.1 狀態

ACTIVE

→ DEPRECATION_PLANNED

→ NOTICE_PUBLISHED

→ MIGRATION_AVAILABLE

→ USAGE_BLOCKED_FOR_NEW_CLIENTS

→ END_OF_SUPPORT

→ RETIRED

16.2 Deprecation Notice 必要內容

deprecation_id

component_type

component_name

current_version

replacement

reason

notice_date

new_client_block_date

end_of_support_date

retirement_date

affected_personas／tenants

breaking_changes

migration_steps

test_plan

rollback_window

support_contact

owner

status

16.3 通知對象

• 開發團隊：Repository、ADR、Release Notes、CI Warning。

• 照護機構管理者：管理介面、Email、正式公告。

• 專業照護者：只通知會影響工作流程或裝置的改動。

• 家屬：只通知 App、登入、Secure Link、報表或通知偏好的改動。

• 長者：以可理解方式說明裝置、語音、記憶或主動陪伴的重要改變，不用技術術語。

16.4 緊急退場

安全漏洞、資料洩漏、Provider 禁用或法規要求可縮短通知期，但仍需：

• Incident／Decision Record。

• 受影響範圍。

• 替代路徑或明確不可用訊息。

• Data Handling。

• 後續通知與支援。

## 十七、Migration Plan 標準

每個 Migration Plan 包含：

source_version

target_version

inventory

preconditions

data_mapping

schema mapping

backfill strategy

dual read／write period

validation queries

sample comparison

performance impact

security／privacy impact

rollback／roll forward

communication

owner／backup

start／end

completion evidence

完成條件不能只看程式部署成功，還需：

□ Active Client／Consumer 已切換。

□ 資料數量、關聯、版本與狀態一致。

□ Authorization／Consent／Cross-Elder Negative Test 通過。

□ Queue、DLQ、Projection Lag 受控。

□ Export 與 Audit 仍可讀。

□ 舊路徑無流量或有明確例外。

## 十八、資料匯出原則

資料匯出需回答：

• 誰提出？

• 代表哪位長者或哪個 Tenant？

• 有何法律／契約／產品目的？

• 能匯出哪些資料類型？

• 是否包含第三人或專業照護者資訊？

• 誰核准與如何安全交付？

• 匯出後檔案保存多久？

匯出不是將整個資料庫、Graph、Prompt、Log 或 Agent Trace 打包給申請者。

## 十九、角色別資料匯出範圍

19.1 長者／合法代理人

候選可匯出：

• 基本個人資料與偏好。

• Consent 歷史與目前狀態。

• 本人確認的長期記憶。

• 可向本人提供的互動紀錄或摘要。

• Verified 且依政策可提供的事件。

• 已發布給本人的報表。

• 資料來源、版本與更正紀錄。

預設排除或需額外審查：

• 其他長者資料。

• 專業照護者私人／內部工作筆記。

• 系統 Prompt、Model Chain-of-Thought、Secret、內部安全規則。

• 未確認 Memory Candidate。

• 未覆核 Event Candidate。

• Draft Family Report。

• 其他人的身份與聯絡資料。

19.2 家屬

只匯出該家屬在有效 Family Share Scope 下可見的 PUBLISHED Report、Important Event History、通知偏好與存取紀錄摘要。不得因家屬提出匯出而取得完整逐字稿、內部照護筆記、未覆核事件、未確認記憶、照護任務或其他家屬資料。

19.3 日照中心／居服機構

依 Tenant、契約、角色與資料控制責任匯出：

• Elder Profile／Consent 狀態。

• Care Assignment／Service Record。

• Verified Event／Summary。

• Family Report 與 Publication Record。

• Care Action。

• 必要 Audit／Access／Change History。

跨 Tenant、跨機構或超出 Assignment Scope 的資料不得混入。

19.4 照服員／居服員

個人帳號可取得自身帳號、派案、工作紀錄與操作歷史的適當範圍；不能以個人身份下載全部機構長者資料。

## 二十、匯出格式

20.1 Human-Readable Package

README.pdf／html

profile.json

consents.csv／json

verified_events.csv／json

confirmed_memories.csv／json

summaries.pdf／json

published_reports.pdf／json

assignments_and_service_records.csv／json（依角色）

audit_summary.csv

manifest.json

checksums.txt

20.2 Machine-Readable

• UTF-8 JSON／JSONL。

• CSV 有欄位說明與時區。

• ISO-8601 日期時間。

• ID 使用穩定 Export ID 或受控 Pseudonym。

• Enum、狀態與版本附 Data Dictionary。

• 大型 Binary 以加密檔案與 Manifest Pointer 提供。

20.3 Manifest

export_id

request_id

requested_by

subject_scope

tenant_id

elder_scope

legal／product purpose

export_schema_version

created_at

expires_at

included_datasets

excluded_datasets_and_reasons

record_counts

time_range

source_versions

file_list

checksums

encryption_method

approvals

delivery_method

## 二十一、Export Request State Machine

REQUESTED

→ IDENTITY_VERIFICATION

→ SCOPE_REVIEW

→ THIRD_PARTY_REDACTION

→ APPROVED／REJECTED

→ GENERATING

→ VALIDATING

→ READY_FOR_SECURE_DELIVERY

→ DELIVERED

→ EXPIRED

→ PURGED

替代狀態：

NEEDS_MORE_INFORMATION

LEGAL_HOLD_REVIEW

PARTIAL_EXPORT_WITH_REASON

FAILED_RETRYABLE

FAILED_MANUAL_REVIEW

CANCELLED

規則：

• Requester 身份與代理關係由 Server 驗證。

• 匯出建立時再次檢查 Consent、Family Share、Assignment 與 Tenant Scope。

• Generator 使用 Snapshot／一致性時間點，避免檔案間互相矛盾。

• 生成後自動做 Cross-Elder、Record Count、Schema、Checksum 與 Restricted Field Scan。

• 檔案到期後清理 Delivery Copy，不因此刪除正式 Source Record。

## 二十二、安全交付

• 使用加密 S3 Object／Package。

• Secure Download Link 短期有效、單一 Export、可撤銷、需再驗證身份。

• Token 不放 Log、Email 主旨或可重用 URL 參數中。

• 大型或高敏感 Export 不直接寄 Email Attachment。

• 可採另一通道提供解密資訊。

• 每次下載記錄 requester、時間、IP／device risk、result 與 export_id。

• 超過下載次數、期限、關係失效或 Tenant Offboarding 後 Link 失效。

• 匯出檔案與 Staging Artifact 使用短 Retention。

## 二十三、Consent Revocation、Deletion、Export 與 Offboarding 的差異

Consent Revocation：停止特定 Purpose 的未來使用與處理；不一定等同立即刪除所有依法需保存資料。

Deletion Request：要求刪除符合範圍的資料與衍生投影，需追蹤各 Store 完成狀態。

Export Request：提供可攜副本，不改變正式資料狀態。

Family Share Revocation：停止家屬未來報表與通知，撤銷 Secure Link；不自動刪除機構正式紀錄。

Tenant Offboarding：機構停止使用整個服務，需處理帳號、整合、資料交付、保存、刪除、Billing 與證據。

Legal Hold：在核准範圍內暫停原定刪除，但必須最小化且有 Owner、理由與解除流程。

## 二十四、Tenant Offboarding Lifecycle

INITIATED

→ CONTRACT／LEGAL REVIEW

→ INVENTORY_FROZEN

→ NEW_DATA_DISABLED

→ EXPORT_SCOPE_APPROVED

→ EXPORT_DELIVERED

→ ACCESS_REVOKED

→ INTEGRATIONS_DISABLED

→ RETENTION／DELETION_JOBS

→ VALIDATION

→ CERTIFICATE_ISSUED

→ CLOSED

24.1 Offboarding Checklist

□ 確認 Tenant、Care Unit、Elder、Family Share、User、Device 與 Integration Inventory。

□ 停止新增長者、派案、報表、通知與主動陪伴。

□ 取消 Scheduler、Webhook、API Client、Secrets 與 Service Account。

□ 完成約定資料匯出。

□ 撤銷 Cognito／Session／Secure Link／Refresh Token。

□ 停止 LINE／Email／第三方通知。

□ 處理 Aurora、S3、Graph、Index、Cache、Agent Memory、Eval Dataset、Analytics。

□ 保存必要 Audit、Invoice、Contract 與 Deletion Certificate。

□ 驗證無跨 Tenant 殘留或共享資源引用。

□ 完成成本標籤與資源釋放。

## 二十五、Data Store 處置矩陣

Aurora PostgreSQL

• 正式交易資料、版本、狀態、Audit、Tombstone。

• 依 Policy Archive／Delete／Anonymize。

• Foreign Key、Outbox、Job、Export、Notification 關聯需一致處理。

S3

• Raw Audio、Transcript Artifact、RAG Source、Report Export、Audit Evidence。

• 依 Prefix／Object Tag／Manifest 找出範圍。

• Versioning、Replication、Lifecycle、Object Lock／Legal Hold 需檢查。

Neptune

• 刪除或停用受影響 Node／Edge Projection。

• 驗證無孤兒 Edge、跨 Elder 關聯與舊 ACTIVE Memory。

OpenSearch

• 依 document_id／elder_id／tenant_id 刪除或重建 Index。

• 驗證 Alias、Replica、Snapshot／Export Artifact 與 Cache。

Cache

• 立即失效 Session、Authorization、Report、Secure Link、Retrieval 與 User Context。

AgentCore／Agent Memory

• 清除 Session／Working Memory 與允許的長期記錄。

• 正式 Memory 仍以 Aurora Deletion State 為準。

Analytics／Eval Dataset

• 依 Purpose、Dataset Manifest 與去識別程度處理。

• 不因已複製到 Dataset 就跳過刪除要求。

External Provider

• LINE／Email／ASR／TTS／Model／Support Tool 依其資料處理能力確認刪除或到期。

## 二十六、Deletion Workflow 與 Tombstone

26.1 Deletion Request

request_id

subject_scope

requested_by

verified_authority

purpose

requested_at

policy_version

legal_hold_status

stores[]

status

completion_evidence

certificate_id

26.2 Store Job

store_name

item_scope

status

attempts

last_error

started_at

completed_at

verification

26.3 Tombstone

Tombstone 不保存已刪內容，而保存最小防重建資訊：

subject_ref_hash

resource_type

resource_id_hash

deleted_at

deletion_request_id

policy_version

reason

expires_at／retention_basis

用途：

• 阻止 DLQ Replay／Backfill／Graph Rebuild 將資料復活。

• 讓 Consumer 知道事件不可重新建立。

• 證明刪除已處理。

26.4 Completion

只有所有必要 Store 完成或合法例外被核准，Deletion Request 才能 COMPLETED。部分失敗保持 PARTIAL_FAILURE 並進人工處理，不可回覆「已全部刪除」。

## 二十七、Archive、Retention 與 Legal Hold

27.1 Archive

Archive 代表不再供日常產品讀取，但仍依核准目的保存。Archived Data：

• 與 Active Data 分權限。

• 不進 Agent Context、RAG、Graph 或報表。

• 有 Retention End Date。

• 有 Restore／Access Audit。

27.2 S3 Object Lock

S3 Object Lock 可用 WORM 模型，以 Retention Period 或 Legal Hold 防止特定 Object Version 被覆寫或刪除。啟用前必須確認正式保存需求、成本、版本與刪除例外，不能把所有產品資料無差別鎖死。

27.3 AWS Backup Vault Lock

Governance Mode 允許具權限者管理；Compliance Mode 在 Grace Period 後形成不可變設定。正式啟用前需經法務與資料治理核准，特別避免無限期 Recovery Point 造成無法刪除與成本風險。

27.4 Legal Hold Record

hold_id

subject／dataset scope

reason

authority

approved_by

start_at

review_at

end_at

stores

access restrictions

release_action

audit evidence

## 二十八、Backup、Snapshot 與刪除關係

• Backup 不是正式查詢來源。

• 刪除完成後，既有 Backup 可能依核准 Retention 存在，但不得恢復後重新供產品使用。

• Restore Drill 必須套用 Deletion Tombstone、Consent Revocation、Share Revocation 與 Offboarding Delta。

• Aurora Snapshot 可匯出至加密 S3 作受控資料分析或退場備份，但需依 Region／Engine 支援、IAM、KMS、Manifest 與 Retention 執行。

• Backup Expiry 後依 Policy 自動到期，不手動延長而無核准。

• Restore 需產生 restore_id、source_snapshot、policy_version、tombstone_replay_result 與 validation evidence。

## 二十九、Provider／Region／Account 替換

29.1 Provider Exit

適用 Bedrock Model、Agent Runtime、ASR、TTS、LINE、Email 或其他外部依賴。

流程：

Inventory

→ Contract／Data Review

→ Alternative Capability Test

→ Export Configuration／Artifacts

→ Dual Run／Shadow

→ Migrate Traffic

→ Revoke Credentials

→ Confirm Provider Data Handling

→ Remove Integration

→ Cost／Security Validation

29.2 Region Migration

• 先確認服務、模型、Quota、資料駐留、Latency 與 KMS 支援。

• 建立新 Region 基礎設施與 Key，不直接複製 Secret。

• Aurora、S3、OpenSearch、Neptune、Cognito、Agent、Queue、Scheduler 各有獨立遷移計畫。

• 先同步資料與 Consumer，再切 DNS／API Traffic。

• Secure Link、Webhook、Callback URL 與外部 Allowlist 需更新。

• 切換後驗證 ElderScope、Consent、Assignment、Family Share、Report 與 Notification。

29.3 Account／Ownership Transfer

不假設可直接轉移所有 AWS Resource。需要明確 Data Export／Import、KMS、DNS、Certificate、Container、IaC State、Secrets、Domain、Audit 與 Billing 交接。

## 三十、系統／產品退場策略

30.1 退場觸發

• 商業停止服務。

• 合作機構合約終止。

• 法規或安全風險無法接受。

• 核心 Provider／模型長期不可用。

• 團隊停止維護。

• 產品被新平台取代。

30.2 退場階段

Phase 0｜Decision and Freeze

• 核准 Decision Record。

• 停止非必要新功能與新 Tenant。

• 建立完整 Inventory、Owner、Timeline 與 Communication Plan。

Phase 1｜Notice and Migration

• 通知 Tenant、專業照護者、家屬與必要長者。

• 提供替代服務、匯出與截止日期。

• 凍結 Schema／Contract，避免退場期間再做破壞性變更。

Phase 2｜Read-Only

• 停止新對話記憶、事件候選、主動陪伴、報表與通知。

• 允許核准範圍的查看、匯出、更正、撤回與刪除。

Phase 3｜Access Closure

• 撤銷新登入、API Client、Webhook、Service Account、Secure Link。

• 處理未完成 Export、Deletion、Incident 與 Legal Hold。

Phase 4｜Data Disposition

• 依 Store 執行 Archive、Return、Delete、Anonymize。

• 清除 Graph、Index、Cache、Agent Memory、Analytics、Eval Artifact。

• 保留必要 Audit／Contract／Billing Evidence。

Phase 5｜Infrastructure Teardown

• 關閉 Endpoint、ECS、Aurora、OpenSearch、Neptune、NAT、Queue、Scheduler、Secrets、KMS Grant、DNS 與 Certificate。

• 先確認 Backup／Retention／Legal Hold，再刪除資源。

Phase 6｜Certification and Close

• 產出 Export Receipt、Deletion Certificate、Residual Data Register、Exception Register、Final Cost Report。

• 確認監控、告警、Pager、Webhook 與外部訂閱也已關閉。

## 三十一、長者與家屬的退場體驗

• 用可理解語言說明服務何時停止、哪些功能先停止、資料如何取得與刪除。

• 不在最後一天突然關閉記憶與報表。

• 長者已確認記憶可提供可閱讀匯出，不以 Graph JSON 作唯一格式。

• 家屬只能取得有效分享範圍內已發布資料。

• 服務關閉後 Secure Link 明確顯示已停止，不導向不存在頁面或洩漏狀態。

• 主動陪伴、通知與所有自動排程在退場前提早停止，避免使用者誤認仍在持續照護。

• 不暗示系統停用代表照護關係或機構服務本身終止。

## 三十二、退場 Runbook Catalog

RB-EXIT-01｜API Major Version Retirement

RB-EXIT-02｜Domain Event Version Retirement

RB-EXIT-03｜Agent／Prompt／Tool Bundle Retirement

RB-EXIT-04｜Bedrock Model EOL Migration

RB-EXIT-05｜ASR／TTS Provider Replacement

RB-EXIT-06｜Embedding／OpenSearch Reindex

RB-EXIT-07｜Graph Schema Rebuild／Retirement

RB-EXIT-08｜Family Notification Provider Exit

RB-EXIT-09｜Single Elder Export／Deletion

RB-EXIT-10｜Family Share Revocation

RB-EXIT-11｜Tenant Offboarding

RB-EXIT-12｜Region Migration

RB-EXIT-13｜AWS Account／Ownership Handover

RB-EXIT-14｜Legal Hold Apply／Release

RB-EXIT-15｜Full Product Shutdown

每份 Runbook 需包含 Trigger、Owner、Scope、Prerequisite、Data Inventory、Communication、Commands／Jobs、Validation、Rollback、Evidence、Exit Criteria。

## 三十三、Compatibility／Exit Metrics

• deprecated_client_request_rate。

• unsupported_api_version_rate。

• event_upcast_failure_rate。

• old_consumer_lag。

• deprecated_tool_call_total。

• legacy_prompt_session_count。

• legacy_model_invocation_rate。

• deprecated_asr_route_rate。

• old_index_query_rate。

• graph_schema_fallback_rate。

• expired_feature_flag_count。

• export_request_completion_time。

• export_validation_failure_rate。

• secure_export_download_success_rate。

• deletion_partial_failure_count。

• tombstone_reappearance_blocked_total。

• offboarding_open_item_age。

• residual_resource_count。

• residual_data_exception_count。

• retirement_cost_remaining。

零容忍：

• Retired Version 造成跨長者暴露＝0。

• Export 混入其他長者或 Tenant＝0。

• 撤回分享後仍可開啟報表＝0。

• 刪除後資料重新進 Graph／Index／Report＝0。

• Provider Exit 後 Secret 仍有效＝0。

## 三十四、Monitoring 與 Alert

告警：

• EOL／Retirement Date 接近但 Migration 未達門檻。

• 舊 API／Event／Model 使用率未下降。

• Export Queue 超過期限。

• Deletion Job Partial Failure。

• Offboarding 後仍有登入、通知、Scheduler、Webhook 或成本。

• Feature Flag 已過 Expiry。

• Legacy Prompt／Model 被新 Release 引用。

• Restore 後 Tombstone 未成功套用。

• Secure Export Link 超過 TTL 或異常下載。

Dashboard 顯示：

• Component Lifecycle Timeline。

• Tenant／Client Version Distribution。

• Migration Progress。

• Export／Deletion／Offboarding Status。

• Residual Data／Resource Register。

• Provider／Model／Region Risk。

## 三十五、Ownership 與批准

Architecture Owner：API、Event、Schema、Version Policy。

Data Governance Owner：Export、Retention、Deletion、Legal Hold。

Platform Owner：AWS Resource、Backup、Region、Provider Exit。

AI Owner：Agent、Prompt、Model、RAG、Graph、Eval。

Speech Owner：ASR／TTS Route、Model、Voice。

Product Owner：使用者通知、退場體驗、替代路徑。

Security／Privacy Owner：Scope、Access、Evidence、Incident。

Tenant／Care Organization Owner：機構資料交付與最終核准。

高風險退場至少需雙人核准；大量刪除、KMS、Backup Vault Lock、Object Lock、Account Shutdown 不由單一開發者執行。

## 三十六、Hackathon Implementation Profile

必做：

• API／Event／Agent／Prompt／Model／Graph／Index 版本欄位。

• 一份 Compatibility Matrix。

• 一個 API 或 Event 的雙版本 Contract Test。

• 一個 Model／Prompt Alias＋Fallback。

• 一個 Feature Flag 具 Owner、Expiry、Kill Switch。

• 一條長者資料 Export Demo，使用 Synthetic Persona。

• 一條 Consent Revocation／Deletion Tombstone，證明 Graph／Index 不會復活。

• 一個 Tenant／Persona Offboarding Checklist。

• Demo Seed 與真實資料完全分離。

可延後：

• 完整法律資料可攜套件。

• 多 Region 遷移。

• Compliance Mode Vault Lock。

• 全產品 Shutdown Automation。

• 所有外部 Provider Exit Drill。

不可省略：

• family PUBLISHED Gate。

• elder_id／tenant_id／assignment_id 隔離。

• 未確認 Memory、未覆核 Event、Draft Report 不進 Export。

• Revocation／Deletion 在 Retry／Replay 前重新檢查。

• Export Link 短效、可撤銷、可稽核。

## 三十七、ADR

ADR-16-001｜API 使用 Major Path Version，Minor 採相容演進

狀態：Accepted。

原因：讓舊 App 與外部整合有明確遷移窗口，避免每次新增欄位都建立新 API。

ADR-16-002｜Domain Event 不覆寫歷史契約

狀態：Accepted。

原因：事件需支援重播、稽核與舊資料解讀；破壞性變更新 event_version。

ADR-16-003｜Prompt、Agent、Tool 與 Model Bundle 全部版本化

狀態：Accepted。

原因：只有 Model ID 不足以重現 Agent 行為與安全結果。

ADR-16-004｜Model 透過 Alias／Router 使用，不硬編碼單一 ID

狀態：Accepted。

原因：Bedrock 模型有 Active、Legacy、EOL 生命週期，需可替換與回退。

ADR-16-005｜Export 採角色與 Purpose 限定 Package，不提供資料庫 Dump

狀態：Accepted。

原因：避免其他長者、內部工作資料、Prompt、Secret 與未覆核內容外洩。

ADR-16-006｜Deletion 使用 Tombstone 防止 Replay 復活

狀態：Accepted。

原因：事件驅動、Graph、Search、Backfill 與 Backup Restore 可能重新建立已刪資料。

ADR-16-007｜Graph／Search／Cache 為可重建投影

狀態：Accepted。

原因：退場與刪除以 Aurora 正式狀態為準，不從 Projection 反推真實資料。

ADR-16-008｜S3 Object Lock／Backup Vault Lock 僅在正式保存政策核准後啟用

狀態：Accepted。

原因：不可變保存可提高保護，但錯誤期限也可能造成資料無法刪除與長期成本。

ADR-16-009｜完整退場流程在設計期定義，實作分階段

狀態：Accepted。

原因：符合完整 Target Product 規劃，也避免黑客松過度投入低優先自動化。

## 三十八、待決策

1. Production API／Event／Client 的正式支援期限。

2. App 是否能強制最低版本，長者裝置如何協助升級。

3. Export 的法律時限、資料範圍與格式。

4. 原始語音、逐字稿、Audit、Report、Analytics、Eval Dataset 的正式 Retention。

5. Legal Hold 的核准者與解除流程。

6. Tenant Offboarding 後哪些資料需交還、匿名化或依法保存。

7. Backup Restore 後 Tombstone Delta 的技術實作。

8. AgentCore Memory、LINE、Email、ASR／TTS Provider 的資料刪除證明能力。

9. Model／Embedding／RAG／Graph 的 Rollback Window。

10. Full Product Shutdown 的通知期、替代服務與支援責任。

## 三十九、v0.1 完成判定

□ API、WebSocket、Event、Schema、Database 相容策略已定義。

□ Agent、Prompt、Tool、Model、ASR／TTS、RAG、Graph 演進規則已定義。

□ Feature Flag 與 Deprecation Lifecycle 已定義。

□ Migration Plan、支援窗口與通知內容已定義。

□ 長者、家屬、專業照護者與 Tenant 的 Export Scope 已定義。

□ Export Format、Manifest、State Machine 與安全交付已定義。

□ Consent Revocation、Deletion、Family Share Revocation、Offboarding、Legal Hold 已區分。

□ Aurora、S3、Graph、Index、Cache、Agent Memory、Analytics、Provider 處置已定義。

□ Tombstone、Backup、Restore 與資料復活防護已定義。

□ Provider、Region、Account 與 Full Product Exit 已定義。

□ Runbook、Metric、Alert、Owner、ADR 與 Hackathon Profile 已建立。

## 四十、官方技術參考（檢查日期：2026-07-26）

Amazon Bedrock Model Lifecycle

https://docs.aws.amazon.com/bedrock/latest/userguide/model-lifecycle.html

Amazon S3 Object Lock

https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html

AWS Backup Vault Lock

https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html

Amazon Aurora Snapshot Export to S3

https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-export-snapshot.html

## 四十一、文件集完成狀態

本文件完成後，智慧長照 AI 陪伴系統的 01～16 與 01A 規劃文件共 17 份已建立。

下一階段不是再增加規劃文件，而是進入「規格收斂與實作啟動」：

1. 決定 Python Framework、Repository 與基礎專案。

2. 將 10 文件轉成 OpenAPI、AsyncAPI 與 JSON Schema。

3. 將 06 Domain Model 轉成 Aurora PostgreSQL Physical Schema 與 Alembic Migration。

4. 依 12 文件拆成五人 Sprint Backlog。

5. 實作第一條 Vertical Slice：林阿嬤語音 → 低信心確認 → Agent 回覆 → Event／Memory Candidate → 人工確認 → Graph Projection。

6. 建立 Demo Persona、測試 Dataset、Dashboard、Runbook 與最小通知流程。
