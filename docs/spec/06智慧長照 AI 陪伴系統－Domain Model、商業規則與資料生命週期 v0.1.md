智慧長照 AI 陪伴系統－Domain Model、商業規則與資料生命週期 v0.1

## 文件資訊

版本：v0.1

狀態：Draft｜Domain 邊界、核心 Entity、Aggregate、Invariant 與資料生命週期基準，待 Security、System Architecture 與 Data Contract 驗證

建立日期：2026-07-26

文件 Owner：待團隊指定

審查者：五人團隊

適用範圍：長者、專業照護者、家屬、照護單位、派案、語音互動、事件、摘要、記憶、Graph、報表、通知、同意、刪除與主動陪伴

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

# 一、文件目的與邊界

本文件將 05 文件中的工作流轉成正式 Domain Model，回答以下問題：

• 系統有哪些核心業務物件？

• 哪些物件必須一起保持一致？

• 哪些狀態轉移合法？

• 哪些規則不能被 Agent、模型或前端繞過？

• 哪些資料是正式事實，哪些只是候選、投影或快取？

• 資料如何建立、版本化、發布、停用、撤回、保留與刪除？

本文件不等同資料庫建表文件。它先定義商業語意與不變條件，後續才由 08 AWS 系統架構與 10 API／Event／Data Contracts 決定實際資料表、Index、Topic、API 與欄位格式。

# 二、Domain 設計原則

1. RDS／交易型資料庫是正式事實來源；Graph DB、搜尋索引、向量索引與快取是可重建投影。

2. AI 只能產生候選內容，不可直接創造授權、權限、正式記憶、正式照護決策或醫療結論。

3. 所有重要資料都需綁定 elder_id、tenant_id、owner／actor、版本與來源。

4. 未確認、待覆核、已發布、已撤回與已刪除必須是明確不同狀態。

5. 資料修改採版本化，不直接覆蓋歷史事實而失去追溯。

6. 刪除與撤回優先於背景排程、通知重試與 Graph／索引延遲。

7. 聚合內維持強一致；聚合間以 Domain Event 與最終一致處理。

8. 權限由關係與作用範圍決定，不只看角色名稱。

9. 家屬只讀取被授權且 Published 的家屬版資料，不等同專業照護者權限。

10. 無資料時保留「未提及／資料不足」，不得用模型補造。

# 三、Bounded Context

## 3.1 Identity & Authorization Context

負責 Actor、Role、Tenant、Care Unit、Relationship、Assignment 與 Authorization Scope。

## 3.2 Elder Profile & Consent Context

負責 Elder、Persona Preference、Consent、Share Scope、Retention Preference 與代理授權。

## 3.3 Conversation Context

負責 Voice Session、Transcript、Language Route、AI Response、Safety Result 與 Context Usage Trace。

## 3.4 Care Record Context

負責 Event Candidate、Verified Event、Review、Daily Summary、Timeline 與 Care Action。

## 3.5 Memory Context

負責 Memory Candidate、Confirmed Memory、Memory Version、Graph Projection 與 Memory Retrieval Policy。

## 3.6 Family Report Context

負責 Family Report、Report Version、Report Publication、Notification Preference、Notification Delivery 與 Secure Link。

## 3.7 Proactive Companion Context

負責 Trigger、Eligibility、Topic Candidate、Approval、Follow-up Plan 與 Interaction Feedback。

## 3.8 Privacy & Data Governance Context

負責 Consent Revocation、Deletion Request、Retention Policy、Audit Record、Data Lineage 與衍生資料清理。

# 四、核心角色與組織模型

## 4.1 Actor

用途：代表可以登入、操作、授權或接收通知的人或系統主體。

主要欄位：actor_id、actor_type、display_name、status、tenant_memberships、created_at。

actor_type：ELDER、DAYCARE_CARE_WORKER、HOME_CARE_WORKER、FAMILY_MEMBER、ADMIN、SYSTEM_SERVICE。

Invariant：Actor 狀態非 ACTIVE 時不得新增業務操作；System Service 不得模擬人工核准。

## 4.2 Tenant

用途：代表照護機構、營運單位或隔離邊界。

主要欄位：tenant_id、tenant_type、name、status、policy_set_id。

Invariant：跨 tenant 讀寫預設禁止；共享必須有明確授權關係與用途。

## 4.3 Care Unit

用途：代表日照中心、社區據點、居家服務單位或服務群組。

主要欄位：care_unit_id、tenant_id、unit_type、name、status。

unit_type：DAYCARE_CENTER、COMMUNITY_SITE、HOME_CARE_AGENCY。

## 4.4 Care Relationship

用途：定義 Actor 與 Elder 之間可做什麼。

主要欄位：relationship_id、elder_id、actor_id、relationship_type、scope、effective_from、effective_to、status。

relationship_type：DAYCARE_ASSIGNMENT、HOME_CARE_ASSIGNMENT、FAMILY_SHARE、LEGAL_REPRESENTATIVE。

Invariant：任何長者資料讀取都必須能回溯至有效 Relationship 或 Assignment。

# 五、Aggregate 與 Aggregate Root

## 5.1 Elder Aggregate

Aggregate Root：Elder

內含：Elder Profile、Language Preference、Communication Preference、Data Preference、Current Consent Reference。

責任：維持長者基本資料、偏好及目前可用的同意版本。

不包含：完整事件、完整記憶、完整報表；這些屬不同 Aggregate。

## 5.2 Consent Aggregate

Aggregate Root：Consent Grant

內含：Consent Purpose、Consent Version、Scope、Effective Period、Revocation Record。

責任：控制每種資料用途是否有效。

## 5.3 Conversation Aggregate

Aggregate Root：Conversation Session

內含：Audio Session、Transcript Version、AI Response、Safety Result、Context Usage。

責任：維持單次對話 Session 的一致狀態與可追溯性。

## 5.4 Care Event Aggregate

Aggregate Root：Care Event

內含：Event Version、Evidence Reference、Review Decision、Correction History。

責任：維持候選、覆核、修正、拒絕與正式事件版本。

## 5.5 Daily Summary Aggregate

Aggregate Root：Daily Summary

內含：Summary Version、Summary Item、Source Event Reference、Review Status。

責任：確保每個摘要重點都可回查來源，且更新時保留版本。

## 5.6 Memory Aggregate

Aggregate Root：Memory

內含：Memory Candidate、Confirmation、Memory Version、Activation State、Projection Status。

責任：確保只有經確認的記憶可啟用及檢索。

## 5.7 Assignment Aggregate

Aggregate Root：Care Assignment

內含：Service Window、Assigned Worker、Elder、Service Scope、Service Record Reference。

責任：控制居服員可見範圍與服務狀態。

## 5.8 Family Report Aggregate

Aggregate Root：Family Report

內含：Report Version、Publication Status、Share Scope、Source References。

責任：確保家屬只看到 Published 且符合授權範圍的資料。

## 5.9 Notification Aggregate

Aggregate Root：Notification Delivery

內含：Channel、Recipient、Delivery Attempt、Opened Record、Secure Link Reference。

責任：管理發送、重試與已讀，不影響報表本身發布狀態。

## 5.10 Care Action Aggregate

Aggregate Root：Care Action

內含：Trigger Reason、Related Event、Assignee、Due Date、Status、Resolution。

責任：將經確認事項轉成可追蹤工作，不讓 AI 自動做照護決策。

## 5.11 Proactive Interaction Aggregate

Aggregate Root：Proactive Trigger

內含：Eligibility Decision、Topic Candidate、Approval、Interaction Result、Follow-up Plan。

責任：確保每次主動陪伴都重新通過同意、頻率、時段與安全規則。

## 5.12 Deletion Aggregate

Aggregate Root：Deletion Request

內含：Deletion Job Item、Target Resource、Processing Result、Failure Reason。

責任：追蹤撤回後的跨系統清理並確保可重跑。

# 六、Entity 定義與核心欄位

6.1 Elder

elder_id、tenant_id、display_name、primary_care_setting、status、preferred_language、preferred_name、response_length_preference、created_at、updated_at。

規則：Demo 只能使用虛擬或去識別資料；長者狀態為 INACTIVE 時停止新互動與新報表。

6.2 Consent Grant

consent_id、elder_id、purpose、status、version、granted_by、granted_at、effective_at、expires_at、revoked_at、policy_version。

purpose：BASIC_VOICE、TRANSCRIPT_STORAGE、CARE_EVENT_EXTRACTION、LONG_TERM_MEMORY、COMPANION_SIGNAL_ANALYSIS、PROACTIVE_COMPANION、FAMILY_SHARING。

6.3 Conversation Session

session_id、elder_id、tenant_id、initiator_type、language_route、state、started_at、ended_at、trace_id、consent_version、policy_version。

6.4 Transcript Version

transcript_id、session_id、version、text、language、asr_model_version、confidence、confirmation_status、created_at。

規則：被低信心否認的版本不得作為正式事件與記憶來源。

6.5 Care Event

event_id、elder_id、tenant_id、event_type、event_time、status、current_version、source_session_id、review_status、created_at。

event_type：MEAL_STATEMENT、ACTIVITY、SLEEP_STATEMENT、MEDICATION_STATEMENT、MOOD_EXPRESSION、SOCIAL_INTERACTION、FAMILY_CONTACT、APPOINTMENT、OTHER。

6.6 Event Version

event_version_id、event_id、version、structured_payload、evidence_text_ref、confidence、created_by、created_at、supersedes_version。

規則：Medication 只保存「長者陳述」，不得有 dosage_is_correct、treatment_advice 等診斷性欄位。

6.7 Review Decision

review_id、target_type、target_id、reviewer_id、decision、reason_code、before_version、after_version、reviewed_at。

decision：VERIFY、CORRECT、REJECT、EXCLUDE、REQUEST_MORE_INFO。

6.8 Daily Summary

summary_id、elder_id、summary_date、summary_type、status、current_version、generated_at、published_at。

summary_type：PROFESSIONAL_DAILY、FAMILY_DAILY、WEEKLY、MONTHLY。

6.9 Summary Version

summary_version_id、summary_id、version、content、source_event_ids、model_version、prompt_version、safety_result_id、created_at。

規則：每個內容重點至少連結一個來源；無來源的 AI 推測不得寫入正式摘要。

6.10 Memory

memory_id、elder_id、tenant_id、memory_type、status、current_version、confirmed_by、confirmed_at、activated_at、deactivated_at、deleted_at。

memory_type：PREFERENCE、IMPORTANT_RELATIONSHIP、ROUTINE、COMMUNICATION_PREFERENCE、PERSONAL_HISTORY。

6.11 Memory Version

memory_version_id、memory_id、version、content、source_event_ids、valid_from、valid_to、created_at。

規則：同一記憶只能有一個 ACTIVE 版本；更正後舊版本轉 INACTIVE。

6.12 Graph Projection Record

projection_id、source_type、source_id、source_version、projection_status、graph_key、attempt_count、last_error、synced_at。

規則：Graph 不是正式事實來源；可由 RDS 與 Outbox 重建。

6.13 Care Assignment

assignment_id、tenant_id、care_unit_id、elder_id、worker_id、service_start、service_end、service_scope、status、version。

規則：HOME_CARE_WORKER 只有在派案有效且 scope 符合時可查看資料。

6.14 Service Record

service_record_id、assignment_id、elder_id、worker_id、service_date、record_type、content、status、created_at、completed_at。

規則：service_record 必須對應有效或剛完成的 assignment；不能脫離派案單獨建立。

6.15 Family Relationship

family_relationship_id、elder_id、family_actor_id、share_scope、status、effective_from、effective_to、consent_version。

share_scope：DAILY_REPORT、WEEKLY_REPORT、MONTHLY_REPORT、IMPORTANT_EVENT、CONTACT_ACTION。

6.16 Family Report

report_id、elder_id、recipient_scope、report_type、period_start、period_end、status、current_version、published_at、withdrawn_at。

6.17 Report Version

report_version_id、report_id、version、content、source_summary_ids、source_event_ids、share_scope_snapshot、created_at。

規則：舊通知導向同一 report_id 的最新可見版本；Withdrawn 後不得顯示舊內容。

6.18 Notification Preference

preference_id、family_actor_id、elder_id、channels、frequency、delivery_time、quiet_hours、status、updated_at。

6.19 Notification Delivery

notification_id、report_id、report_version、recipient_id、channel、status、scheduled_at、sent_at、opened_at、attempt_count、last_error。

規則：通知失敗不得把 report 狀態改回 Draft 或 Withdrawn。

6.20 Secure Link

secure_link_id、recipient_id、report_id、token_hash、expires_at、revoked_at、used_at、status。

規則：URL 不放敏感資料；撤回授權或報表 Withdrawn 後立即失效。

6.21 Care Action

care_action_id、elder_id、tenant_id、action_type、trigger_reason、related_event_ids、assignee_id、due_at、status、resolution、created_by。

action_type：CONTACT_ELDER、CONTACT_FAMILY、CONFIRM_INFORMATION、INVITE_ACTIVITY、FOLLOW_UP、OTHER。

規則：不得建立改藥、停藥、診斷疾病等 action_type。

6.22 Proactive Trigger

trigger_id、elder_id、source_type、source_id、topic_type、status、scheduled_at、expires_at、policy_version、blocked_reason。

6.23 Eligibility Decision

eligibility_id、trigger_id、consent_passed、quiet_hours_passed、frequency_passed、cooldown_passed、device_passed、safety_passed、decision、reason_codes、evaluated_at。

6.24 Follow-up Plan

follow_up_id、elder_id、source_id、scheduled_at、status、expires_at、created_by、completed_at。

status：SCHEDULED、COMPLETED、POSTPONED、CANCELLED、EXPIRED。

6.25 Deletion Request

deletion_request_id、elder_id、requested_by、scope、status、requested_at、effective_at、completed_at。

6.26 Deletion Job Item

item_id、deletion_request_id、resource_type、resource_id、system_of_record、status、attempt_count、last_error、completed_at。

# 七、Value Object

• ElderScope：tenant_id＋elder_id＋relationship／assignment reference。

• ConsentPurpose：用途代碼與必要版本。

• AuthorizationScope：可讀欄位、可做動作、有效期間。

• LanguagePreference：主要語言、允許混語、回覆語言、稱呼方式。

• TimeWindow：start_at、end_at、timezone。

• ReportPeriod：DAILY／WEEKLY／MONTHLY 及期間邊界。

• SourceReference：source_type、source_id、source_version。

• Confidence：value、model_version、threshold_policy；不得直接顯示給家屬。

• ReviewReason：reason_code、optional_note。

• IdempotencyKey：業務唯一性鍵。

• VersionNumber：樂觀鎖與歷史版本。

• RetentionRule：資料類型、保存期限、觸發條件與刪除方式。

# 八、關聯模型

Tenant 1 ─ N Care Unit

Tenant 1 ─ N Actor Membership

Elder 1 ─ N Consent Grant

Elder 1 ─ N Conversation Session

Conversation Session 1 ─ N Transcript Version

Conversation Session 1 ─ N Care Event

Care Event 1 ─ N Event Version

Care Event 1 ─ N Review Decision

Elder 1 ─ N Daily Summary

Daily Summary 1 ─ N Summary Version

Elder 1 ─ N Memory

Memory 1 ─ N Memory Version

Memory／Event 1 ─ N Graph Projection Record

Elder 1 ─ N Care Assignment

Care Assignment 1 ─ N Service Record

Elder 1 ─ N Family Relationship

Elder 1 ─ N Family Report

Family Report 1 ─ N Report Version

Family Report 1 ─ N Notification Delivery

Elder 1 ─ N Care Action

Elder 1 ─ N Proactive Trigger

Proactive Trigger 1 ─ N Eligibility Decision

Elder 1 ─ N Deletion Request

Deletion Request 1 ─ N Deletion Job Item

# 九、核心 Invariant

## 9.1 授權與資料隔離

1. 所有讀取與寫入都必須同時驗證 actor、role、relationship／assignment、tenant 與 elder scope。

2. 日照照服員只能存取所屬據點且被授權長者。

3. 居服員只能存取有效派案範圍內長者。

4. 家屬只能讀取符合 Family Relationship、Share Scope 與 PUBLISHED 狀態的資料。

5. 張阿姨資料不得出現在林阿嬤的 Context、摘要、記憶、Graph 查詢或報表中。

## 9.2 事件與摘要

1. REJECTED、EXCLUDED 或未確認的低信心事件不得進正式摘要。

2. 摘要每個要點必須可回查 source_event_id。

3. 事件更正後，受影響摘要必須建立新版本或標記重建。

4. 無資料欄位必須標示未提及／資料不足。

## 9.3 確認式記憶

1. 只有穩定偏好、重要關係、固定作息與個人歷史可成為候選記憶。

2. 候選記憶未被長者或合法授權人確認前，不得轉 ACTIVE。

3. DEFERRED、REJECTED、INACTIVE、DELETED 記憶不得被檢索。

4. 一般閒聊、一次性事件、醫療推測與陪伴需求推估不得自動成為長期記憶。

## 9.4 家屬報表

1. 家屬端只顯示 PUBLISHED 報表。

2. LINE、Email 與 App／Web 使用同一 report_id；只是呈現長度不同。

3. 通知失敗不影響報表已發布狀態。

4. 報表撤回或分享同意撤回後，安全連結立即失效。

5. 家屬版不得包含逐字稿、內部筆記、ASR 信心、未覆核事件與診斷式分數。

## 9.5 派案與服務

1. Service Record 必須對應有效 assignment_id。

2. EXPIRED、CANCELLED、NO_SHOW 派案不得繼續提供敏感摘要。

3. 同一 assignment、service_date、record_type 不得重複建立正式服務紀錄。

## 9.6 主動陪伴

1. 每次播放前必須重新確認同意、靜默時段、每日上限、cooldown、裝置與拒絕紀錄。

2. Trigger 過期、來源取消或同意撤回後不得播放。

3. 長者拒絕後立即停止，不能因重試再次播放同一 Trigger。

4. 敏感主題必須人工核准或直接禁止。

## 9.7 撤回與刪除

1. Consent 轉 REVOKED 後立即停止新處理，不等待資料實體刪除完成。

2. 新到事件若 consent_version 已失效，必須拒絕。

3. Graph、索引或快取清理失敗時，所有讀取仍先由 Consent Gate 阻擋。

4. Deletion Job Item 必須可冪等重跑。

# 十、資料生命週期

## 10.1 Voice／Transcript

建立：錄音開始後建立 Session；逐字稿由 ASR 產生版本。

使用：只供當次回覆、事件擷取及必要稽核。

版本：低信心修正建立新 transcript version。

保留：依 Consent 與 Retention Policy 決定，預設不永久保存原始音訊。

刪除：撤回、期限到期或合法刪除請求觸發；衍生事件需依 scope 判斷是否同步刪除。

## 10.2 Care Event

建立：由 AI 產生 Candidate 或由照護者新增。

覆核：進 VERIFIED、CORRECTED、REJECTED 或 EXCLUDED。

使用：正式摘要、時間軸、Graph 投影、家屬報表及關懷待辦。

版本：修正建立 Event Version，不直接覆蓋歷史。

停用：被拒絕、排除或來源撤回後不可再使用。

刪除：依資料用途與稽核規則處理，保留必要 tombstone 避免重建。

## 10.3 Daily Summary

建立：依日期與正式事件產生 DRAFT。

發布：專業照護版可在通過 Schema／Safety 後使用；家屬版需符合分享規則。

更新：來源事件更正後建立新版本。

過期：舊版本保留追溯但不作為最新畫面。

刪除／撤回：來源被刪除或分享同意撤回後重建、隱藏或刪除。

## 10.4 Memory

建立：事件／對話形成 Candidate。

確認：長者選擇記住後轉 CONFIRMED／ACTIVE。

使用：只在相關對話注入少量 ACTIVE 記憶。

更正：建立新版本並停用舊版本。

停用：不再適用或被授權人停用。

刪除：RDS 事實、Graph 投影與搜尋索引同步失效。

## 10.5 Family Report

建立：依可分享事件或已發布摘要產生 DRAFT。

覆核：敏感內容進 NEEDS_REVIEW。

發布：轉 PUBLISHED 後 App／Web 可見並建立通知工作。

更新：同一 report_id 建立新版本。

撤回：轉 WITHDRAWN，安全連結失效。

刪除：依分享同意、Retention Policy 與合法要求處理。

## 10.6 Notification

建立：報表 Published 後依 Preference 建立。

發送：PENDING → SENDING → SENT。

已讀：OPENED 僅代表通知或連結被開啟，不等同內容理解。

失敗：有限重試，超過上限進人工處理。

保留：只保留送達狀態與必要稽核，不將通知內容當正式報表副本。

## 10.7 Assignment／Service Record

建立：由機構或排班系統建立派案。

生效：CONFIRMED 後授予最小必要資料權限。

服務：IN_PROGRESS 期間可建立服務紀錄草稿。

完成：COMPLETED 後保留正式服務紀錄。

過期／取消：立即收回資料存取。

## 10.8 Proactive Trigger

建立：排程、事件、提醒或照護者安排產生。

判斷：Eligibility 通過才可進 SCHEDULED／READY。

執行：播放後記錄結果與回饋。

到期：未執行 Trigger 轉 EXPIRED。

取消：同意撤回、來源取消、拒絕或人工拒絕後轉 CANCELLED／BLOCKED。

## 10.9 Consent／Deletion

建立：保存用途、版本、授權人與生效時間。

更新：任何範圍變更建立新版本。

撤回：轉 REVOKED 並發布 ConsentRevoked。

清理：建立 Deletion Request 與 Job Items。

完成：所有工作完成或留下最小必要稽核證據後轉 COMPLETED。

# 十一、System of Record 與投影責任

RDS／交易型資料庫

保存：Actor、Elder、Relationship、Assignment、Consent、Care Event、Summary、Memory、Report、Notification State、Care Action、Trigger、Deletion Job、版本與 Outbox。

Object Storage

保存：經同意且需保留的音訊、較大逐字稿附件、報表檔案或稽核證據；需加密、期限與存取控制。

Graph DB

保存：已確認人物、關係、事件與記憶的投影，用於關係查詢與個人化 Context；不保存唯一正式事實。

Search／Vector Index

保存：可檢索的照護事件、已確認記憶、可信知識 Chunk 或摘要投影；必須帶 tenant_id、elder_id、status、consent_version 與 review_status 等過濾欄位。

Cache

保存：短時間 UI 或 Context 查詢結果；權限或同意變更時必須失效。

# 十二、Graph Domain Model v0.1

建議 Node

• Elder

• Person

• Care Worker

• Family Member

• Care Unit

• Activity

• Place

• Preference

• Routine

• Event

建議 Edge

• ELDER_HAS_FAMILY_MEMBER

• ELDER_SUPPORTED_BY_WORKER

• ELDER_ATTENDS_CARE_UNIT

• ELDER_PARTICIPATED_IN_ACTIVITY

• ELDER_PREFERS

• ELDER_HAS_ROUTINE

• EVENT_INVOLVES_PERSON

• EVENT_OCCURRED_AT

• MEMORY_DERIVED_FROM_EVENT

Graph 規則

1. 所有 Node／Edge 都必須帶 source_id、source_version、elder_id、tenant_id、status 與 synced_at。

2. CANDIDATE、REJECTED、DEFERRED、INACTIVE、DELETED 不可作為 Active Graph Context。

3. 跨 elder 關係若確實存在，也必須以兩側授權及最小資料呈現；第一版 Demo 不做跨長者共享記憶。

4. Graph 查詢回傳後仍需經 Authorization／Consent Filter，不可因在圖中存在就自動可見。

# 十三、資料完整性與一致性策略

• 聚合內：使用交易、唯一鍵、外鍵、狀態轉移檢查與 optimistic locking。

• 聚合間：使用 Transactional Outbox 與 Domain Event。

• 重送：Consumer 依 event_id／idempotency_key 去重。

• Graph／Index：最終一致，失敗可重建。

• 摘要／報表：保存 source_version snapshot，來源更新後標記 stale。

• 權限：每次讀取重新驗證，不能只依登入時快取。

• 刪除：以 deletion_request_id 串起多系統清理。

# 十四、Domain Event Catalog v0.1

• ElderProfileUpdated

• ConsentGranted

• ConsentScopeChanged

• ConsentRevoked

• ConversationSessionCompleted

• TranscriptConfirmed

• CareEventCandidateCreated

• CareEventVerified

• CareEventCorrected

• CareEventRejected

• DailySummaryGenerated

• DailySummaryRebuildRequested

• MemoryCandidateCreated

• MemoryConfirmed

• MemoryDeactivated

• MemoryDeleted

• GraphProjectionRequested

• GraphProjectionFailed

• CareAssignmentCreated

• CareAssignmentExpired

• ServiceRecordCompleted

• FamilyReportGenerated

• FamilyReportPublished

• FamilyReportWithdrawn

• NotificationScheduled

• NotificationSent

• NotificationFailed

• CareActionCreated

• ProactiveTriggerCreated

• ProactiveTriggerBlocked

• ProactiveInteractionCompleted

• DeletionRequested

• DeletionPartiallyFailed

• DeletionCompleted

這些名稱為概念名稱，最終 payload、版本與 Topic 命名由 10 文件確定。

# 十五、商業規則優先級

P0｜不可違反

• 權限、同意、跨長者隔離、候選記憶確認、醫療邊界、家屬只看 Published、撤回後停止新處理。

P1｜核心可靠性

• 事件／摘要版本化、來源追溯、Graph 可重建、通知冪等、派案有效期、刪除工作可重跑。

P2｜產品品質

• 通知偏好、主動陪伴頻率、週月報內容、Care Action 工作流、離線草稿。

# 十六、Demo Persona 對應

林阿嬤

• Tenant／Care Unit：幸福日照中心。

• 專業角色：日照照服員。

• 語言：臺語／國臺混語。

• 核心資料：Conversation、Care Event、Memory、Graph、Daily Summary、Care Action。

張阿姨

• 與林阿嬤同一 Care Unit。

• 用途：多長者概覽與 cross-elder isolation。

• 核心驗證：張阿姨資料不能進林阿嬤 Context 或報表。

陳伯伯

• 場域：居家服務。

• 專業角色：居服員，透過 Care Assignment 取得限時權限。

• 家屬：透過 Family Relationship 取得 Published 報表。

• 核心資料：Assignment、Service Record、Family Report、Notification。

# 十七、測試規則

## 17.1 Aggregate Invariant

• 未確認記憶無法 ACTIVE。

• Withdrawn 報表無法被家屬讀取。

• Expired Assignment 無法建立 Service Record。

• Rejected Event 無法進 Daily Summary。

• Consent Revoked 後無法建立新 Report 或 Trigger。

## 17.2 Cross-Aggregate

• Event 修正後觸發 Summary rebuild 與 Graph projection update。

• Report Published 後建立 Notification，但通知失敗不改變 Report。

• Memory Deleted 後 Graph 與 Index 最終不可檢索。

• Assignment Expired 後 Authorization Scope 立即失效。

## 17.3 Isolation

• 修改 elder_id、tenant_id、assignment_id、report_id 不得越權。

• 同據點多長者仍需逐 elder 驗證。

• 家屬無法讀取專業版摘要或照護內部筆記。

# 十八、v0.1 完成判定

□ 已定義 Bounded Context、Aggregate Root、Entity、Value Object 與關聯。

□ 每個核心 Aggregate 都有責任與 Invariant。

□ 事件、摘要、記憶、報表、派案、通知、同意、Trigger 與刪除生命週期已定義。

□ 已區分正式事實、候選資料、投影、Index 與快取。

□ 已明確規定 RDS 為交易事實來源，Graph 與 Search 為可重建投影。

□ 家屬、日照照服員、居服員與長者權限模型已分開。

□ 已定義版本、來源追溯、冪等與 stale／rebuild 概念。

□ 撤回、刪除與投影失敗時的資料可見性規則已定義。

□ Domain Event Catalog 可供後續 System 與 Contract 文件使用。

□ 三位 Demo Persona 都可映射到 Domain Model。

# 十九、待決策

1. Event 哪些類型可以自動 VERIFIED，哪些一律 Needs Review？

2. Transcript 與原始音訊的預設保存期限為何？

3. Event、Summary、Report、Audit 各自的保留期限與刪除方式為何？

4. 家屬 Share Scope 是否允許不同家屬看到不同類型報表？

5. 專業照護者是否可代長者確認記憶；若可，適用範圍與理由為何？

6. 多機構共同照護時 elder_id 與跨 tenant Relationship 如何管理？

7. 居服員離線草稿是否納入，若納入如何保護裝置資料？

8. Graph 第一版只投影 Memory，或同時投影 Verified Event 與 Care Relationship？

9. 哪些 Audit Record 必須永久保留，哪些可匿名化？

10. 報表 Withdrawal 是隱藏、軟刪除還是建立撤回版本？

# 二十、下一份文件

07｜智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1

07 文件將根據本文件定義：

• 身分驗證與 RBAC／ABAC

• tenant、elder、assignment、family share 的授權規則

• 傳輸／靜態加密與 Secrets 管理

• 語音、逐字稿、報表、Graph 與索引的資料保護

• 同意、撤回、刪除與保存期限

• Prompt Injection、越權、資料洩漏、惡意檔案與通知連結威脅

• 效能、可靠性、可用性、RTO／RPO、可觀測性與測試門檻
