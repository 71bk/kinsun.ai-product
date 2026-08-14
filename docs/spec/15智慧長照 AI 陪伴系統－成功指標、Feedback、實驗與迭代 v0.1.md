智慧長照 AI 陪伴系統－成功指標、Feedback、實驗與迭代 v0.1

## 文件資訊

版本：v0.1

狀態：Draft｜完整 Target Product 的成效衡量、回饋治理與安全實驗基準，依黑客松、Pilot 與正式營運分階段實作

建立日期：2026-07-26

文件 Owner：Product／Data／AI Evaluation Owner

審查者：五人團隊

適用範圍：長者陪伴、日照照服員、居服員、家屬報表、ASR／TTS、Agent、RAG、Graph、事件、記憶、主動陪伴、營運、安全與商業驗證

## 相關文件

01｜產品方向與範圍基準 v1.2

https://docs.google.com/document/d/1Z8Ser24Jx8wavKRrMkLdwlZ0PjQedWyYOp4g29FLEuc/edit

01A｜使用者研究與 Demo Persona v0.2

https://docs.google.com/document/d/1tZjDn5uY2FuVaTTLVshFjGSMaMP-37koqNZxfS2qjIQ/edit

02｜使用者故事與驗收條件 v1.3.2

https://docs.google.com/document/d/1qb89I23zD8GJFzead_R_G6fXq2CZWgEsKBK7Q4o_F8A/edit

03｜Story Map v1.2

https://docs.google.com/spreadsheets/d/1Qmg1jbaN67Tjmpcx6e2zyZOf_-td0_fg9iKqgb128CE/edit

07｜Security、Privacy、NFR 與 Threat Model v0.1

https://docs.google.com/document/d/1UUnrs6FUCqlaNxaDm12zPVFAPfQG0ruWqdiL0HXvTrI/edit

09｜Multi-Agent、Agentic Workflow 與 Context Engineering v0.1

https://docs.google.com/document/d/1ZfkKMMW2tfu5nSXn74WncuN6VN2iVVOeJ5kDxMSVr4Q/edit

11｜測試策略、Agent Evaluation 與品質門檻 v0.1

https://docs.google.com/document/d/1saeohikZZ63P2ud1YNHMQDKBKX2wgVnMsQ3LPTAD2qY/edit

12｜實作計畫、環境、團隊分工與交付路線 v0.1

https://docs.google.com/document/d/1OGa9igfGHILGPJE3PmvynP23LxA9FPsT8jPO_R-SG9o/edit

14｜Observability、營運與 Incident Response v0.1

https://docs.google.com/document/d/1SUefwxwKMOQx4tH3avyrFq-DFlkzWpIpgBV3mKw5JiY/edit

# 一、文件目的與衡量原則

本文件回答四個問題：

1. 系統真正成功的定義是什麼？

2. 長者、照服員、居服員與家屬的回饋如何進入產品決策？

3. Agent、Prompt、模型、RAG、Graph、主動陪伴與 UX 的改動如何安全驗證？

4. 團隊如何避免只追求使用次數、Token、對話長度或 Demo 效果，而忽略可信、減負、尊重與可持續性？

本專案採「完整 Target Product、分階段實作」，因此指標也分成三層：

• Hackathon：證明核心價值與技術可信度。

• Pilot：證明在真實工作流程中可用、可理解、能減少負擔且沒有不可接受風險。

• Production：證明長期留存、營運可靠、法規與成本可持續。

衡量原則：

• Outcome Before Activity：優先衡量是否完成有價值任務，而非單純登入或對話次數。

• Safety Before Growth：成長指標不能抵銷跨長者洩漏、同意繞過或危險建議。

• Persona Specific：長者、照服員、居服員與家屬成功定義不同，不以單一總分取代。

• Human Confirmation：高風險、正式事件、長期記憶與家屬分享仍需人類決策。

• Evidence Traceable：指標可回查事件定義、版本、資料來源、計算方法與排除規則。

• No Manipulative Engagement：不以延長對話、提高依賴或情緒操控作成功指標。

• Measure the Cost of Errors：錯誤歸因、誤報、重複通知與人工修正時間都要衡量。

• Segment Before Average：依場域、角色、語言、裝置、風險與資料充分度分層。

• Complete Planning, Phased Thresholds：完整定義未來指標，但門檻依實測逐步校準。

# 二、產品價值鏈與指標樹

2.1 價值鏈

長者可安心互動

→ 語音被正確理解

→ 系統提供尊重且有根據的回覆

→ 重要資訊形成可覆核候選事件

→ 穩定個人資訊經確認成為長期記憶

→ 專業照護者更快掌握需要注意的資訊

→ 家屬只收到經核准、可理解、符合分享範圍的報表

→ 團隊從回饋與失敗中持續改善

2.2 指標層級

L0｜使命指標：是否在不犧牲安全與尊嚴下，提升長者陪伴品質與照護資訊可用性。

L1｜North Star：每週成功完成的「可信照護價值循環」。

L2｜Persona Outcome：長者、專業照護者、家屬的成果。

L3｜Product Funnel：啟用、互動、事件、覆核、記憶、報表與回饋。

L4｜AI Quality：ASR、Agent、RAG、Graph、摘要與安全。

L5｜Operational Health：延遲、可用性、失敗、成本、Incident。

L6｜Guardrails：越權、洩漏、醫療邊界、主動陪伴拒絕與資料權利。

# 三、North Star Metric

3.1 定義

**NSM｜Weekly Trusted Care Value Loop Completion**

每週至少完成以下任一條完整價值循環，且通過所有安全 Guardrail 的長者數：

A. 長者完成有效陪伴互動 → 產生有用回覆 → 使用者未拒絕／未安全阻擋。

B. 對話產生事件候選 → 專業照護者覆核 → 成為 Verified Event 或正確拒絕。

C. Verified-speaker Memory Proposal → Core Policy（LOW all-of 或 MEDIUM exact-version Elder confirmation）
→ 成為 Trusted ACTIVE Memory → 後續通過 final retrieval gate 並被正確引用。

D. Verified Event／Summary → 家屬報表 PUBLISHED → 有效家屬安全讀取。

3.2 為何不使用「對話總數」

對話多可能代表 ASR 重複失敗、系統一直問澄清或主動陪伴過度打擾。North Star 必須包含「成功、可信、具結果」而不是單純活動量。

3.3 計算單位

• 分母：該週具有效 Consent 且至少有一次可用機會的長者。

• 分子：至少完成一條可信價值循環的長者。

• 排除：測試帳號、Synthetic Persona、系統健康檢查、取消且未產生結果的 Session。

• 必須分層：日照／居家、語言、裝置、Persona、是否有照護者覆核能力。

3.4 Guardrail

只要發生跨長者資料洩漏、越權成功、同意繞過、危險醫療建議通過或家屬錯收報表，North Star 不得宣告成功，即使使用量上升。

# 四、Persona Outcome Metrics

4.1 長者

核心成果：容易使用、被理解、被尊重、可控制記憶與主動互動。

候選指標：

• successful_voice_interaction_rate：成功完成語音互動／開始互動。

• first_turn_understood_rate：第一輪不需重錄或重述即可被理解。

• clarification_recovery_rate：進入低信心確認後仍成功完成任務。

• elder_helpfulness_score：互動後簡單「有幫助／還好／沒有幫助」。

• elder_comprehension_pass_rate：長者能用自己的話說明系統剛剛做了什麼。

• medium_memory_confirmation_accept_rate：MEDIUM Candidate 被長者確認比例；不能追求越高越好，需搭配
proposal precision、comprehension 與 correction rate。

• low_memory_auto_activation_precision：LOW 自動啟用後被長者保留且無更正的比例；必須搭配
unverified_speaker_activation、policy false-positive 與「不要記」率，不能只追求數量。

• memory_correction_rate：長者修正或停用記憶的比例。

• proactive_accept_rate：主動話題被接受比例。

• proactive_rejection_rate：拒絕／稍後／停止比例，作為打擾警示而非失敗懲罰。

• stop_request_compliance_rate：長者要求停止後系統立即停止的比例，目標 100%。

• repeat_error_rate：同一問題因系統錯誤被迫重複的比例。

• task_abandonment_rate：開始後未完成且非自願取消。

禁止將平均對話時長、每日對話次數或連續登入天數單獨當作陪伴成功。

4.2 日照中心照服員

核心成果：減少找資料與整理時間，提高事件覆核與摘要可信度，不增加警報疲勞。

候選指標：

• time_to_find_elder_context：從首頁到找到指定長者重點所需時間。

• event_review_median_seconds：每筆候選事件覆核時間。

• summary_edit_distance／review_edit_rate：摘要需人工修改幅度。

• useful_candidate_precision：照服員認為值得保留的候選比例。

• false_attribution_rate：人物、時間、長者歸屬錯誤率。

• daily_summary_completion_rate：應產生摘要中按時完成比例。

• unresolved_review_backlog_age：待覆核工作最久時間。

• care_action_follow_through_rate：由 Verified Event 建立且完成的 Care Action。

• information_overload_score：照服員評估資訊量是否過多。

• estimated_minutes_saved_per_shift：以基準任務計時，不只自我感覺。

4.3 居服員

核心成果：只看有效派案範圍、快速掌握當次服務資訊、完成紀錄且不跨長者混淆。

候選指標：

• assignment_entry_success_rate。

• time_to_open_today_assignment。

• service_record_completion_rate。

• service_record_draft_to_submit_time。

• assignment_scope_denial_accuracy：過期／取消派案阻擋正確率。

• cross_assignment_confusion_rate。

• offline_or_network_recovery_rate（功能實作後）。

• follow_up_action_visibility_rate。

4.4 家屬

核心成果：在不看到內部或未覆核資料下，理解長者近況與重要事件。

候選指標：

• published_report_read_rate。

• report_time_to_first_open。

• report_comprehension_score。

• report_usefulness_score。

• notification_to_app_open_rate。

• secure_link_success_rate。

• notification_failure_but_app_available_rate，目標 100%。

• family_question_after_report_rate：需區分合理追問與報表不清楚。

• report_correction_or_withdraw_rate。

• oversharing_incident_rate，目標 0。

• notification_opt_out_rate 與原因。

# 五、Product Funnel

5.1 Onboarding／Consent Funnel

invited

→ account_or_device_ready

→ role_verified

→ elder_scope_established

→ consent_explained

→ purpose_consent_granted／declined

→ first_successful_task

衡量：

• consent_explanation_comprehension。

• 各用途同意率，不把拒絕視為產品失敗。

• first_value_time。

• setup_assistance_required_rate。

• first_week_return_for_value_rate。

5.2 Voice Funnel

voice_start

→ recording_complete

→ asr_final

→ low_confidence_confirmation（必要時）

→ agent_response_ready

→ tts_or_text_delivered

→ user_understood／continued／stopped

5.3 Event Funnel

conversation_completed

→ extraction_eligible

→ candidate_created

→ needs_review

→ verified／corrected／rejected

→ summary_included

5.4 Memory Funnel

source_verified

→ candidate_created

→ confirmation_presented

→ confirmed／corrected／rejected／deferred

→ ACTIVE

→ later_retrieved

→ accepted／corrected／deactivated

5.5 Family Report Funnel

source_ready

→ draft_created

→ review_required／approved

→ PUBLISHED

→ notification_attempted

→ notification_delivered／failed

→ App／Web opened

→ read／feedback

5.6 Proactive Companion Funnel

trigger_created

→ eligibility_passed／blocked

→ content_generated

→ safety_passed／human_review

→ ready

→ played

→ accepted／rejected／stopped

→ cooldown_applied

# 六、AI／Speech／Retrieval Quality Metrics

6.1 ASR

• CER／WER：依國語、臺語、混語、客語、英文分開。

• key_entity_accuracy：姓名、時間、地點、活動與重要詞。

• elder_speech_success_rate：以長停頓、音量、口音、混語分層。

• low_confidence_precision：被標低信心的句子確實需要確認比例。

• false_high_confidence_rate：錯誤但未觸發確認，屬高風險。

• correction_turns_per_session。

• asr_final_latency_p50／p95。

• route_accuracy：Managed／Custom／Language Route 是否正確。

6.2 TTS

• intelligibility_pass_rate。

• elder_preferred_voice_rate。

• pronunciation_error_rate：姓名、地名與臺語／客語專詞。

• first_audio_latency_p50／p95。

• playback_completion／replay_rate。

• speech_rate_comfort_score。

6.3 Companion Agent

• helpfulness。

• elder_comprehension。

• respectfulness。

• one_question_rule_pass。

• language_match。

• unsupported_claim_rate。

• unsafe_medical_advice_rate，目標 0。

• hallucinated_memory_rate，目標 0。

• unnecessary_tool_call_rate。

• average_agent_steps，需受 09 最大步驟限制。

• safe_fallback_success_rate。

6.4 Event Extractor

• precision／recall／F1。

• event_type_accuracy。

• actor／elder attribution accuracy。

• time_normalization_accuracy。

• evidence_link_coverage。

• unsupported_candidate_rate。

• professional_reject_rate。

• correction_type_distribution。

6.5 Memory Candidate

• candidate_precision。

• inappropriate_memory_candidate_rate。

• confirmation_question_clarity。

• conflict_detection_rate。

• later_retrieval_relevance。

• correction_after_activation_rate。

• unauthorized_activation，目標 0。

6.6 Summary／Family Report

• source_coverage。

• unsupported_statement_rate。

• missing_as_unknown_rate。

• review_edit_rate。

• sensitive_content_block_rate。

• family_readability。

• share_scope_violation，目標 0。

• draft_exposure，目標 0。

6.7 RAG／Search

• Recall@K。

• Precision@K。

• MRR／NDCG。

• source_validity_rate。

• review_status_filter_pass。

• effective_date_filter_pass。

• persona_restriction_filter_pass。

• grounded_answer_rate。

• no_answer_when_no_source_rate。

• citation_accuracy。

• stale_source_use_rate。

6.8 Graph

• relationship_query_accuracy。

• graph_source_coverage。

• projection_lag。

• invalid_edge_rate。

• inactive／deleted_memory_exclusion_rate。

• cross_elder_node_leakage，目標 0。

• graph_fallback_success_rate。

# 七、安全、隱私與倫理 Guardrail Metrics

7.1 零容忍

• cross_tenant_exposure_success＝0。

• cross_elder_exposure_success＝0。

• authorization_bypass＝0。

• consent_bypass＝0。

• family_draft_exposure＝0。

• family_wrong_recipient＝0。

• unsafe_medical_advice_passed＝0。

• unconfirmed_memory_presented_as_fact＝0。

• deleted_data_reappeared＝0。

• agent_high_risk_command_without_core_auth＝0。

7.2 主動陪伴

• stop_request_compliance＝100%。

• quiet_hours_violation＝0。

• daily_limit_violation＝0。

• cooldown_violation＝0。

• recent_rejection_recontact_violation＝0。

• sensitive_topic_without_approval＝0。

• proactive_complaint_rate。

• proactive_opt_out_rate。

7.3 公平與偏差

依語言、場域、性別、年齡區間、語音條件、裝置及互動能力比較：

• ASR 成功率差距。

• 任務完成率差距。

• Low Confidence 觸發差距。

• Safety False Positive／False Negative 差距。

• 候選事件保留率差距。

• 主動陪伴觸發率差距。

• 家屬報表內容量差距。

資料不足時只標示「尚無足夠證據」，不可把小樣本差距解讀為群體特性。

# 八、營運與商業指標

8.1 營運

• SLO 達成率與 Error Budget。

• Incident Count、MTTD、MTTA、MTTR。

• Voice／Agent／Report 成功率。

• DLQ、Outbox Lag、Projection Lag。

• Human Review Backlog。

• Support Ticket Volume 與分類。

• Release Change Failure Rate。

• Rollback／Feature Disable Rate。

8.2 成本

黑客松階段成本不是主要功能取捨依據，但仍需監控異常與長期可持續性。

候選指標：

• cost_per_successful_voice_interaction。

• cost_per_trusted_care_value_loop。

• cost_per_published_report。

• model_cost_per_agent_task。

• custom_asr_cost_per_audio_minute。

• observability_cost_ratio。

• idle_infrastructure_cost。

• failed_retry_cost。

不得使用「花費越低」作唯一成功，導致 ASR、Safety、資料隔離或 Demo 穩定性下降。

8.3 Pilot／商業驗證

• care_unit_activation_rate。

• active_elder_rate。

• weekly_active_professional_user_rate。

• setup_time_per_care_unit。

• training_completion／support_hours。

• pilot_continuation_intent。

• willingness_to_pay_range：需透過訪談，不由點擊推測。

• procurement_blockers。

• integration_requirements。

• measurable_staff_time_saved。

• family_value_perception。

# 九、Feedback Architecture

9.1 回饋來源

Explicit Feedback：

• 長者：有幫助／沒幫助、聽不懂、記錯了、不要記、不要再聊。

• 照服員／居服員：事件正確／需修正／不應建立、來源錯誤、摘要過多／過少。

• 家屬：報表有幫助、看不懂、內容不正確、通知太多、希望調整頻率。

• 管理者：流程、權限、資料來源、營運與合規問題。

Implicit Signals：

• 重錄、重述、取消、重播、澄清次數。

• 事件候選被修正／拒絕。

• 記憶被更正／停用。

• 報表撤回／修正。

• 主動陪伴被拒絕。

• Secure Link 失敗或通知退訂。

Implicit Signal 只能作候選證據，不可直接解讀為孤獨、滿意、不滿意或健康風險。

9.2 Feedback Record

feedback_id

feedback_type

actor_role

actor_id_tokenized

elder_id_tokenized

resource_type

resource_id

resource_version

workflow

rating

reason_code

free_text_redacted

source_channel

language

created_at

consent_version

policy_version

release_id

model／prompt／schema versions

assigned_owner

triage_status

resolution

resolved_at

9.3 Reason Codes

VOICE_NOT_UNDERSTOOD

RESPONSE_NOT_HELPFUL

RESPONSE_TOO_LONG

LANGUAGE_MISMATCH

WRONG_PERSON

WRONG_TIME

WRONG_EVENT

SOURCE_NOT_RELEVANT

SOURCE_OUTDATED

MEMORY_SHOULD_NOT_BE_SAVED

MEMORY_INCORRECT

SUMMARY_MISSING_INFORMATION

SUMMARY_UNSUPPORTED_INFORMATION

REPORT_TOO_SENSITIVE

REPORT_NOT_CLEAR

TOO_MANY_NOTIFICATIONS

PROACTIVE_INTERRUPTION

TOOL／SYSTEM_ERROR

OTHER

自由文字需先做敏感資料遮罩；Dashboard 優先使用 Reason Code。

9.4 Feedback Lifecycle

COLLECTED

→ VALIDATED

→ TRIAGED

→ LINKED_TO_COMPONENT

→ ACTION_PLANNED／NO_ACTION_WITH_REASON

→ FIXED／EXPERIMENTING

→ VERIFIED

→ CLOSED

高風險回饋，例如其他長者資料、錯誤收件、醫療危險建議或同意失效，直接轉 Incident，不等待一般產品排程。

# 十、Persona Feedback Loop

10.1 長者

• 互動後最多一個簡單問題，不每輪要求評分。

• 支援語音回答「有幫助／沒有／不知道」。

• 「不要記」與「不要再提」優先於評分。

• 研究訪談使用短任務、觀察與理解回述，不只問喜不喜歡。

10.2 日照照服員

• 在 Event Review／Summary Review 介面直接回饋原因。

• 每週檢查最常被修正的 Event Type、人物、時間與來源。

• 計算修正時間，避免系統提供大量低品質候選增加負擔。

10.3 居服員

• 服務結束後收集派案資訊是否足夠、紀錄是否易填與網路問題。

• 分析不同服務地點與裝置，不把網路問題誤判成產品流程問題。

10.4 家屬

• 報表底部提供「有幫助／看不懂／內容有誤／通知太多」。

• 內容有誤進 Report Correction Flow；涉及隱私或錯收立即 Incident。

• 不用家屬點擊率推測長者照護品質。

# 十一、研究與驗證方法

11.1 Gate 1 最低研究

• 1 位日照／機構照服員訪談。

• 1 位居服員訪談。

• 1 位家屬訪談。

• 1 次長者語音、同意或記憶確認 Prototype Test。

11.2 任務式 Usability Test

受試者完成明確任務：

• 長者：開始對話、處理低信心、確認／拒絕記憶、停止主動話題。

• 照服員：找到林阿嬤、覆核事件、修正摘要。

• 居服員：進入陳伯伯派案、完成服務紀錄。

• 家屬：從通知安全開啟 PUBLISHED 報表、調整通知。

紀錄：成功／部分成功／失敗、完成時間、錯誤、求助、理解、情緒與改善建議。

11.3 Concept Test

比較價值主張與信任問題：

• AI 陪伴回覆。

• 生活事件自動候選。

• 確認式長期記憶。

• 家屬報表。

• 主動開話題。

• Graph 關係記憶。

不得只問「會不會用」，需追問何時使用、擔心什麼、誰需核准與錯誤後果。

11.4 Field Pilot

先在受控 Persona／少量場域使用：

• 明確 Pilot Scope、Owner、Consent 與停止方式。

• 每日檢查高風險事件。

• 每週訪談與任務數據結合。

• Pilot 不自動擴大到所有長者。

# 十二、Experiment Taxonomy

E0｜Offline Evaluation

不接觸真實使用者，使用版本化 Dataset 比較 Prompt、Model、Agent、RAG 或 ASR。

E1｜Replay／Counterfactual

使用經同意且去識別的歷史輸入，讓新版本離線產生結果；不得把結果寫回正式 Domain State。

E2｜Shadow

正式請求仍由現行版本服務，新版本平行執行但不向使用者顯示、不執行 Tool Write、不產生通知。

E3｜Internal／Synthetic Canary

只對團隊帳號、Synthetic Persona 或明確 Test Tenant 開啟。

E4｜Limited Pilot Rollout

依 Tenant／Care Unit／Persona／Feature Flag 小範圍啟用，有明確停止條件。

E5｜Controlled A／B

只用於低風險 UX、文案、排序、回覆長度等；不隨機分配安全政策、Consent、資料分享或高風險醫療邊界。

E6｜Progressive Rollout

通過 Pilot 後逐步擴大，依 Guardrail、SLO、Human Review 與 Segment 檢查。

# 十三、Experiment Design Contract

experiment_id

name

owner

hypothesis

problem_statement

persona／tenant scope

eligibility

unit_of_assignment

control_version

treatment_version

primary_metric

secondary_metrics

guardrail_metrics

minimum_sample／time_window

analysis_plan

segment_plan

exposure_percent

feature_flag

start／stop criteria

risk_level

consent_requirement

human_review_requirement

data_classification

rollback_action

approval_status

started_at／ended_at

decision

每個實驗需先寫：

• 我們相信什麼改動會造成什麼成果。

• 對誰有效，在哪個場域。

• 哪個指標代表成功。

• 哪些 Guardrail 一旦異常立即停止。

• 如何避免季節、學習效應、裝置、語言與人員差異干擾。

# 十四、不可進行的實驗

• 隨機取消或弱化 Consent 說明。

• 隨機放寬跨長者、家屬分享或派案權限。

• 對部分長者停用醫療安全 Guardrail。

• 為提高互動量使用恐懼、內疚、壓力或情緒依賴文案。

• 未同意下測試主動陪伴。

• 讓 Agent 直接發布報表、確認記憶或執行刪除作為實驗。

• 使用真實長者資料進公開 Demo 或未受控第三方工具。

• 因實驗方便而隱藏錯誤、排除不利 Segment 或更改事先定義指標。

# 十五、核心實驗 Backlog

EX-01｜低信心確認方式

假設：提供逐字稿重述＋「是／不是」比要求重錄更容易。

Primary：clarification_recovery_rate。

Guardrail：錯誤確認後的 false_high_confidence、完成時間、長者理解。

EX-02｜長者回覆長度

比較短句與稍完整說明。

Primary：elder_comprehension／helpfulness。

Guardrail：重問、退出、Safety。

EX-03｜事件候選呈現

比較「一句摘要＋證據」與完整欄位表。

Primary：event_review_time、correction_accuracy。

Guardrail：錯誤核准率。

EX-04｜記憶確認問題

比較自然語句與結構化確認卡。

Primary：confirmation_comprehension。

Guardrail：誤確認、後續修正。

EX-05｜Graph＋Search Query Planner

離線比較 Keyword、Vector、Graph 與 Hybrid 路由。

Primary：route_accuracy、answer_grounding。

Guardrail：不必要 Graph Query、跨範圍查詢、Latency。

EX-06｜RAG Chunk／Metadata

比較 Chunk 規則、Top K、Rerank 與 Metadata Filter。

Primary：Recall@K／NDCG／Grounded Answer。

Guardrail：過期來源、錯誤 Persona、No-Source Hallucination。

EX-07｜Family Report 結構

比較按主題與按時間排列。

Primary：comprehension／usefulness。

Guardrail：敏感內容、誤解、追問成本。

EX-08｜通知預覽

比較只有「新報表可查看」與最小非敏感摘要。

Primary：安全開啟率。

Guardrail：隱私、退訂、錯收。

EX-09｜主動陪伴時機

只在同意且 Eligibility 通過下比較低風險時段。

Primary：accept_rate。

Guardrail：rejection、stop、opt_out、complaint、quiet_hours violation。

EX-10｜Agent Model Route

離線／Shadow 比較任務模型。

Primary：Task Quality／Schema Pass／Latency。

Guardrail：Safety、Cost、Tool Error、Hallucination。

EX-11｜臺語／混語 ASR Route

比較 Managed zh-TW、Custom ASR 與 Router。

Primary：CER、Key Entity、Task Completion。

Guardrail：false_high_confidence、Latency。

EX-12｜Summary Agent

比較 Prompt／Model／Source Compression。

Primary：source_coverage、review_edit_rate。

Guardrail：unsupported_statement、missing_as_normal。

# 十六、A／B、Shadow、Canary 與 Rollout 規則

16.1 Assignment Unit

依風險選擇：session_id、actor_id、elder_id、tenant_id 或 care_unit_id。

不得在同一長者記憶、報表或安全政策中頻繁切換版本造成不一致。

16.2 Sticky Assignment

長期體驗需固定 treatment_version，避免今天 A、明天 B 造成長者困惑。正式資料保存產生版本。

16.3 Exposure

• 先 Internal／Synthetic。

• 再單一 Test Tenant。

• 再明確 Pilot Group。

• 每次提高比例前檢查 Primary、Guardrail、SLO、Incident 與 Segment。

16.4 Stop Conditions

立即停止：

• 任一零容忍事件。

• Guardrail 顯著惡化。

• 長者停止要求未遵守。

• 家屬錯收或 Draft Exposure。

• Agent 未授權 Tool Command。

• 異常 Incident／成本 Loop。

暫停分析：

• 資料量不足。

• 版本或事件追蹤錯誤。

• Segment 嚴重不平衡。

• 同時有其他 Release／場域事件造成干擾。

16.5 Rollback

實驗必須對應 Feature Flag、Prompt Bundle、Model Route、Index Alias、Agent Version 或 UI Version；不能只靠重新部署未知版本。

# 十七、統計與決策原則

• 先定義 Primary Metric，避免看到結果後挑有利指標。

• 報告 effect size、confidence／uncertainty，不只報是否顯著。

• 小樣本 Pilot 以方向性證據＋訪談＋錯誤分析為主，不做過度精確推論。

• 同時檢查平均值、中位數、p95、分布與最差 Segment。

• 重複使用同一長者需考慮個體內相關，不當作完全獨立樣本。

• 多指標比較需控制錯誤發現或明確標示探索性。

• 缺失資料需說明原因；退出與拒絕本身可能是重要訊號。

• Safety／Privacy Guardrail 不因統計不顯著就忽略。

# 十八、Agent Evaluation Loop

18.1 Offline Dataset

Dataset Item 至少包含：

scenario_id

persona

language

input

conversation_state

elder_scope

consent_state

source_context

expected_behavior

forbidden_behavior

expected_tools

forbidden_tools

expected_schema

gold_sources

risk_level

reviewer_notes

18.2 Evaluator 類型

• Deterministic：JSON Schema、Tool Allowlist、Source、Permission、State Transition。

• Rule-Based：字數、一次一題、禁語、敏感欄位、引用格式。

• Model-Based：helpfulness、groundedness、respectfulness、completeness。

• Human Review：長者可理解度、照護情境合理性、敏感內容、臺語／客語品質。

18.3 評估節奏

• PR：小型 Regression Set。

• Prompt／Model／Tool 變更：完整 Offline Dataset。

• Staging：Synthetic E2E＋Shadow。

• Pilot：抽樣 Online Evaluation＋Human Review。

• Production：趨勢監控、Incident Sampling、定期 Regression。

18.4 LLM-as-Judge 限制

• Judge 不可覆蓋確定性安全規則。

• 評分 Prompt、模型與 Rubric 版本化。

• 以人工校準一致性與偏差。

• 不把 Judge 單一總分當上線唯一依據。

# 十八A、AgentCore／Bedrock Evaluation 使用方式

• AgentCore Evaluations 用於 Agent Trace 的 Dataset、On-Demand 或受控 Online Evaluation。

• 使用 Built-in Evaluator 評估通用品質，Custom Evaluator 處理長照專屬 Rubric。

• Bedrock Evaluations 可用於模型、RAG Retrieval／Generation 與 LLM-as-Judge／Human Evaluation。

• 評估結果需回寫本專案 experiment_id、release_id、prompt_version、model_route_version、dataset_version。

• AWS 評估工具只負責執行與結果，不取代產品安全 Gate、人工覆核與正式決策紀錄。

# 十九、Metric／Analytics Event Contract

19.1 共通欄位

analytics_event_id

event_name

event_version

occurred_at

received_at

actor_role

actor_ref_tokenized

tenant_id

elder_ref_tokenized

session_id

workflow_instance_id

resource_type／resource_id

persona／setting

language

variant／experiment_id

release_id

app_version

agent_version

model_route_version

prompt_version

policy_version

schema_version

result

reason_code

latency_ms

consent_purpose

19.2 資料最小化

• Analytics 不保存完整語音、逐字稿、Prompt、家屬報表或內部照護筆記。

• elder_id 使用受控 Token／Pseudonym，禁止放入第三方公開分析平台。

• 自由文字 Feedback 分離保存、遮罩與限權。

• 不將健康、孤獨或陪伴訊號作廣告／行銷分群。

19.3 事件品質

• Event Schema 有 Owner 與版本。

• 必填欄位缺失率監控。

• 重複事件去重。

• Client 與 Server 重要狀態以 Server 為準。

• 指標 SQL／程式碼版本化並有測試。

# 二十、指標治理

20.1 Metric Definition Record

metric_id

name

purpose

owner

formula

numerator／denominator

unit

source_events

inclusion／exclusion

segment_dimensions

refresh_frequency

quality_checks

privacy_classification

threshold／target

status：DRAFT／APPROVED／DEPRECATED

version

change_history

20.2 指標 Owner

• Product Outcome：Product Owner。

• Care Workflow：Care Domain Owner。

• ASR／TTS：Speech Owner。

• Agent／RAG／Graph：AI／Retrieval Owner。

• Security／Privacy：Security／Privacy Owner。

• SLO／Cost：Platform Owner。

20.3 指標變更

不得偷偷改分母、排除失敗、改時間窗或刪除不利資料。變更需記錄原因、生效日、舊版與新版差異，重大變更避免直接做跨版本比較。

20.4 Dashboard 不等於決策

Dashboard 顯示發生什麼；決策仍需結合 Trace、錯誤案例、訪談、Segment、風險與成本。

# 二十一、虛榮指標與反指標

不單獨使用：

• 總對話次數。

• 平均對話長度。

• Token 使用量。

• 建立的記憶數量。

• 建立的事件候選數量。

• 通知發送數量。

• 家屬點擊率。

• Agent 數量或 Tool Call 數量。

• Graph Node／Edge 數量。

• Demo 畫面數量。

需搭配的反指標：

• 對話增加是否伴隨重試增加。

• 記憶增加是否伴隨修正／停用增加。

• 候選增加是否增加照護者負擔。

• 通知增加是否增加退訂與抱怨。

• Tool Call 增加是否改善任務完成與 Grounding。

• Graph 變大是否提升實際關係查詢成功率。

# 二十二、Decision Cadence

每日／Demo Build

• 檢查 P0／P1、核心 E2E、Agent Regression、ASR、DLQ 與 Demo Persona。

• 不依單日小波動改產品方向。

每週

• Product Funnel、Persona Outcome、Top Feedback、修正率、Safety／Privacy、SLO、成本。

• 挑選 1～3 個最高影響問題進迭代。

• 檢查不同語言、Persona 與場域 Segment。

每兩週／Sprint

• Review 實驗結果、Release、Dataset 與 Backlog。

• 決定 Ship／Iterate／Hold／Rollback／Stop。

每月／Pilot

• 使用者研究、任務計時、流程負擔、Incident、Retention、價值與商業障礙。

• 重新校準 Threshold，而非為達標降低 Guardrail。

每季／Production

• North Star、照護成果、產品留存、成本、SLO、偏差、資料治理、退場與合規。

# 二十三、Experiment Decision Record

experiment_id

hypothesis

period

population／segments

versions

sample／exposure

primary_result

secondary_result

guardrail_result

qualitative_findings

limitations

incidents

cost_impact

privacy_review

decision：SHIP／ITERATE／HOLD／ROLLBACK／STOP

reason

action_items

owners／due_dates

approved_by

沒有決策紀錄的實驗不能永久保留在 Production Feature Flag。

# 二十四、Iteration Workflow

Problem Signal

→ Validate Data Quality

→ Link Feedback／Trace／Persona

→ Define Problem and Risk

→ Prioritize

→ Design Change

→ Offline Test

→ Safety／Contract Gate

→ Shadow／Synthetic

→ Pilot／Experiment

→ Analyze

→ Ship／Iterate／Stop

→ Update Docs／Dataset／Runbook

優先順序：

P0：安全、隱私、越權、錯誤分享、危險內容。

P1：核心任務失敗、ASR 無法使用、資料不可信、照護工作量增加。

P2：理解度、效率、通知、搜尋與個人化改善。

P3：視覺、次要便利與探索功能。

# 二十五、Backlog Prioritization

建議使用：Impact × Evidence × Reach × Risk Reduction ÷ Effort。

Evidence Level：

E0｜假設。

E1｜內部觀察／單一案例。

E2｜多個使用者或量化訊號。

E3｜受控 Prototype／Offline Eval。

E4｜Pilot／實驗證據。

E5｜Production 多期證據。

安全修復不因 Reach 小而降級；單一跨長者事件即最高優先。

# 二十六、Hackathon Success Scorecard

26.1 Product

• 林阿嬤完成語音互動與低信心恢復。

• 事件候選可由照服員覆核。

• LOW 通過 all-of 或 MEDIUM 綁定版本確認後，仍須通過 final retrieval gate 才進下一輪與 Graph；
  HIGH、unverified Speaker、stale confirmation 與失效 Consent 為零放行。

• 家屬只看到 PUBLISHED 報表。

26.2 AI／Technical

• Orchestrator＋Specialist＋Evaluator Trace 可展示。

• Keyword／Vector／Graph 路由有理由與來源。

• ASR／Agent／TTS 延遲有量測。

• Cross-Elder、Consent、Tool Denied 有測試證據。

26.3 Demo Reliability

• 核心 E2E 連續成功 5 次。

• Graph Failure 有 Fallback。

• Notification Failure 不影響 App Report。

• Demo Seed、Runbook、Kill Switch 準備完成。

26.4 Story

評審可清楚理解：

• 問題是什麼。

• 誰受到幫助。

• 為何使用 Multi-Agent、Graph 與 Hybrid Search。

• 哪些決策由 AI、哪些由確定性系統與人類負責。

• 如何保護長者資料與避免危險建議。

26.5 黑客松不把以下作主要成功標準

• 模型最大、Agent 最多、AWS 服務最多。

• Token／GPU 使用最多或最少。

• Demo 功能數量最多。

• 沒有真實任務證據的「市場很大」。

# 二十七、Pilot Success Gate

進 Pilot 前：

□ Demo 零容忍測試全通過。

□ 明確 Consent、Data Retention、Owner、Support 與停止流程。

□ 日照、居服、家屬、長者研究證據至少完成最低 Gate。

□ ASR、Agent、RAG／Graph 品質達 11 文件門檻。

□ Human Review Backlog 有容量估算。

□ Feedback、Incident、Deletion 與 Export Flow 可用。

Pilot 擴大條件：

□ 核心任務完成穩定。

□ 照護者實際時間沒有增加。

□ 長者理解與停止控制通過。

□ 家屬報表無過度分享。

□ 主要 Segment 無不可接受差距。

□ 安全、隱私與 Incident 在門檻內。

# 二十八、Production Success Gate

• North Star 連續多期穩定且具 Segment 證據。

• 核心 SLO、RTO／RPO、Incident、Backup／Restore 達標。

• Retention、Deletion、Export、Access Review 與 Audit 正式核准。

• 成本與營運支援可持續。

• 模型、Prompt、RAG、Graph 具版本與退場能力。

• 合作機構、法務、安全與照護專業完成核准。

# 二十九、資料偏差與資料不足處理

• 對話多的長者不代表產品對沉默或不便使用者有效。

• 家屬點擊少可能是通知偏好、時間或報表頻率，不直接代表不在乎。

• 照服員修正少可能是沒時間覆核，不一定代表候選正確。

• 主動陪伴接受率高可能來自不好意思拒絕，需觀察停止、退出與訪談。

• ASR 平均 CER 可能掩蓋姓名、藥名、時間等關鍵詞錯誤。

• Pilot 場域人員高度投入可能高估一般導入效果。

任何結論需附資料充分度：INSUFFICIENT／DIRECTIONAL／MODERATE／STRONG。

# 三十、隱私與分析資料治理

• 產品改進用途需在 Consent／Privacy Notice 說明。

• 原始語音、逐字稿與敏感 Feedback 不自動成為訓練資料。

• 模型訓練／微調、Eval、Analytics 分開 Purpose 與 Dataset Manifest。

• 去識別不等於無風險；小樣本、時間、關係仍可能回推身份。

• 使用者要求刪除時，Analytics、Eval Dataset、Graph、Index 與 Artifact 依政策處理。

• 報告只顯示必要的彙總，避免小樣本群組重新識別。

# 三十一、AWS 實作基準

• CloudWatch／Structured Business Metrics：監控產品 Funnel、SLO、Safety 與 Experiment Guardrail。

• AgentCore Evaluations：Agent Dataset、On-Demand、Online Sample 與 Built-in／Custom Evaluator。

• Bedrock Evaluations：模型、RAG、LLM-as-Judge 與 Human Evaluation。

• S3：版本化 Evaluation Dataset、Result、Experiment Manifest 與去識別 Evidence。

• Aurora PostgreSQL：Metric Definition、Feedback、Experiment、Assignment、Variant 與 Decision Record 的正式來源。

• EventBridge／SQS：Feedback Triage、Evaluation Job、Experiment Analysis 與 Follow-up 工作。

• Feature Flag：由團隊自建設定／AppConfig 或其他受控方案實作，需支援 Tenant、Persona、版本與 Kill Switch。

CloudWatch Evidently 已停止支援，因此新專案不將其作為 A／B 或 Feature Launch 核心依賴；實驗資料模型與 Feature Flag 維持可替換。

# 三十二、Repository 建議

/product-analytics

/metric-definitions

/event-schemas

/queries

/dashboards

/experiments

/decision-records

/privacy

/evaluation

/datasets

/conversation

/event-extraction

/memory

/summary

/family-report

/rag

/graph

/safety

/speech

/evaluators

/rubrics

/results

/human-review

/feedback

/reason-codes

/triage-rules

/reports

所有 Dataset、Metric、Experiment 與 Evaluator 經 PR Review、版本化並能連到 Release。

# 三十三、Hackathon Implementation Profile

必做：

• 定義 1 個 North Star、4 組 Persona Outcome 與零容忍 Guardrail。

• Voice、Event、Memory、Report 四條 Funnel。

• 長者與照服員的 Explicit Feedback。

• Event／Memory 修正 Reason Code。

• Agent Offline Evaluation Dataset。

• Cross-Elder、Prompt Injection、Medical Boundary Dataset。

• 一個 Shadow／Synthetic Experiment。

• 一份 Experiment Decision Record。

• Dashboard 顯示成功率、錯誤、Safety、延遲與 Release Version。

• Demo E2E 連續 5 次與結果保存。

第二階段：

• 家屬、居服員 Feedback。

• RAG／Graph Retrieval Experiment。

• AgentCore Evaluations 整合。

• 主動陪伴受控 Pilot。

• Segment／Bias Dashboard。

完整 Target：

• Pilot Cohort 與 Progressive Rollout。

• 長期 North Star、留存、照護工作量與商業價值。

• Online Evaluation、Drift、Evaluator Calibration。

• 多場域與多語言差異分析。

• 正式 Experiment Governance／Approval。

不可省略：

• 安全零容忍事件。

• Consent 與 Feedback Purpose。

• 未確認記憶、未覆核事件、Draft Report 隔離。

• 主動陪伴停止與拒絕權。

• 指標版本與分母定義。

• 真實資料不進公開 Demo。

# 三十四、ADR

ADR-15-001｜North Star 使用可信價值循環，不使用對話量

狀態：Accepted。

原因：避免將重試、打擾或依賴誤判為產品價值。

ADR-15-002｜完整指標架構、分階段門檻

狀態：Accepted。

原因：符合完整 Target Product 規劃，並依 Hackathon、Pilot、Production 校準。

ADR-15-003｜安全零容忍不與成長指標互相抵銷

狀態：Accepted。

原因：長照資料與醫療邊界的單一重大錯誤不能用平均使用量合理化。

ADR-15-004｜Implicit Signal 不直接等同心理或健康結論

狀態：Accepted。

原因：未互動、拒絕、短對話與點擊不足可能有多種原因。

ADR-15-005｜正式事件、記憶與家屬報表不進一般 A／B 隨機安全實驗

狀態：Accepted。

原因：這些資料需穩定版本、同意、人工與狀態機控制。

ADR-15-006｜Agent 評估採 Deterministic＋Model＋Human

狀態：Accepted。

原因：單一 LLM Judge 無法取代授權、Schema、安全與長者可理解度。

ADR-15-007｜CloudWatch Evidently 不作新依賴

狀態：Accepted。

原因：服務已停止支援，採可替換 Feature Flag、Experiment Contract 與分析流程。

ADR-15-008｜Feedback 內容有錯可直接形成修正流程

狀態：Accepted。

原因：回饋不是只進報表；涉及 Event、Memory、Report 的內容錯誤需連至正式版本與修正狀態。

# 三十五、待決策

1. North Star 分母的「可用機會」正式定義。

2. 長者 Feedback 的最佳語音／按鈕形式與頻率。

3. 哪些照護者修正可自動進 Dataset，哪些需二次審查。

4. Pilot 各 Persona 的最低樣本與期間。

5. 主動陪伴可接受的 Exposure 與停止門檻。

6. 正式 Feature Flag／Experiment Assignment 實作。

7. AgentCore／Bedrock Evaluation 的實作深度與成本。

8. Analytics／Feedback 的 Retention 與刪除規則。

9. Pilot 是否允許使用經同意的真實語音作離線 Eval。

10. 哪位成員擔任 Metric Owner、Experiment Owner、Human Review Owner。

# 三十六、v0.1 完成判定

□ North Star 與產品價值鏈已定義。

□ 長者、日照照服員、居服員與家屬 Outcome 指標已定義。

□ Voice、Event、Memory、Report、Notification、Proactive Funnel 已定義。

□ ASR、TTS、Agent、Event、Memory、Summary、RAG、Graph 指標已定義。

□ 安全、隱私、倫理與偏差 Guardrail 已定義。

□ Feedback Record、Reason Code、Lifecycle 與 Persona Loop 已定義。

□ Offline、Replay、Shadow、Canary、Pilot、A／B、Progressive Rollout 已區分。

□ 不可進行的實驗與停止條件已定義。

□ Agent Evaluation、LLM Judge 與 Human Review 邊界已定義。

□ Analytics Event、Metric Definition、Experiment Contract、Decision Record 已定義。

□ Hackathon、Pilot、Production Success Gate 已定義。

□ 完整規劃、分階段實作原則已落實。

# 三十七、官方技術參考（檢查日期：2026-07-26）

Amazon Bedrock Evaluations

https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation.html

Amazon Bedrock RAG Evaluation

https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html

Amazon Bedrock LLM-as-a-Judge

https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-judge.html

Amazon Bedrock Human Evaluation

https://docs.aws.amazon.com/bedrock/latest/userguide/human-worker-evaluations.html

AgentCore Evaluations

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluations.html

AgentCore Dataset Evaluations

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/dataset-evaluations.html

AgentCore On-Demand Evaluations

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/on-demand-evaluations.html

AgentCore Evaluators

https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/evaluators.html

CloudWatch Evidently End-of-Support Notice

https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Evidently.html

# 三十八、下一份文件

16｜智慧長照 AI 陪伴系統－相容性、Deprecation、資料匯出與退場策略 v0.1

16 文件將定義：

• API、Event、Schema、Agent、Prompt、Model、ASR／TTS、RAG 與 Graph 的相容窗口。

• Deprecation Notice、版本支援、Feature Flag 清理與 Migration Path。

• 長者、照護機構與家屬的資料匯出格式、權限與安全交付。

• Tenant Offboarding、Consent Revocation、Provider／Region／Model 替換。

• Archive、Deletion、Tombstone、Audit、Backup 與投影清理。

• 系統停用、合約結束與產品退場 Runbook。
