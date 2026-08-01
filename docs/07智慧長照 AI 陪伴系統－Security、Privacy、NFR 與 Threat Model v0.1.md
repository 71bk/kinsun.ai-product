# 07智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1.docx

智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1

### 文件資訊

版本：v0.1

狀態：Draft｜安全、隱私、非功能需求與威脅模型基準，待 AWS 架構、技術 Spike、法務與場域驗證

建立日期：2026-07-26

文件 Owner：待團隊指定

審查者：五人團隊

適用範圍：長者端、專業照護端、家屬端、語音鏈路、Agent、RDS、Graph、Search／Vector、Object Storage、通知與背景工作

### 相關文件

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

## 一、文件目的與邊界

本文件把 05 的工作流與 06 的 Domain Model 轉成可驗證的安全、隱私與非功能需求，回答以下問題：

• 誰可以登入、讀取、修改、覆核、發布、撤回或刪除哪些資料？

• 語音、逐字稿、事件、記憶、報表、Graph、索引與通知如何被保護？

• 系統如何防止跨 tenant、跨 elder、跨角色與跨派案越權？

• Agent、RAG、Tool Calling 與主動陪伴如何避免 Prompt Injection、資料洩漏與繞過規則？

• 系統在失敗、攻擊、斷線、重送或區域故障時，需要達到哪些效能、可靠性與恢復標準？

本文件是產品與架構安全基準，不是正式法律意見。個資、長照、醫療、通訊、保存期限與代理授權的最終做法，仍需由實際營運地區、合作機構、法務與資訊安全人員確認。

## 二、安全與隱私目標

### 2.1 Confidentiality｜機密性

長者與家屬資料只能由具有效身份、角色、關係、派案、同意與用途範圍的人或服務讀取。

### 2.2 Integrity｜完整性

正式事件、記憶、報表、派案、同意與照護紀錄不得被未授權修改；所有重要修改需版本化、可追溯且保留操作者。

### 2.3 Availability｜可用性

語音陪伴、照護摘要與家屬報表在單一依賴失敗時應降級，而不是整體不可使用或顯示錯誤事實。

### 2.4 Privacy｜隱私

資料蒐集、使用、分享、保存與刪除依明確用途控制；只處理完成任務所需的最小資料。

### 2.5 Safety｜內容與照護安全

系統不得產生醫療診斷、改藥、停藥或自動改變正式照護計畫；高風險內容需安全降級或人工處理。

### 2.6 Accountability｜可問責性

每次重要決策與資料變化須能回查 actor、role、elder_id、tenant_id、consent_version、policy_version、來源與 trace_id。

## 三、保護資產與資料分類

### 3.1 Restricted｜高度敏感

• 原始語音、完整逐字稿與可識別聲紋資料。

• 長者基本資料、家庭關係、聯絡方式、地址與派案地點。

• 用藥陳述、健康相關陳述、情緒與陪伴需求事件。

• 專業照護內部筆記、服務紀錄與照護待辦。

• 同意、代理授權、刪除請求與安全稽核紀錄。

• Access Token、Refresh Token、API Key、Secret、加密金鑰與 Secure Link Token。

### 3.2 Confidential｜機密

• 已確認記憶、每日摘要、家屬報表與 Graph 關係投影。

• 模型輸入 Context、檢索結果、Prompt、Tool Parameters 與 Agent Trace。

• 內部錯誤、效能資料、Policy、Rule 與系統設定。

### 3.3 Internal｜內部

• 去識別化測試資料、彙總指標、非敏感操作文件與測試結果。

### 3.4 Public｜公開

• 已核准的產品說明、公開衛教來源與不含任何個資的展示材料。

資料分類規則

• 任何含 elder_id 或可回推長者身份的資料，最低視為 Confidential。

• Restricted 資料不得出現在公開 URL、前端錯誤、普通應用程式日誌、Analytics 或第三方追蹤工具。

• Demo 使用虛擬 Persona 與模擬資料，不使用真實長者資料。

## 四、角色、身份與授權模型

### 4.1 Authentication｜身份驗證

• 長者裝置採受控裝置或簡化登入，但高風險設定、分享與刪除需再次驗證或由合法授權人完成。

• 日照照服員、居服員、管理者與專業審查者使用個人帳號，不共用帳號。

• 家屬透過 App／Web 登入、LINE Login 或具時效的安全連結進入；安全連結不得取代高風險操作的再次驗證。

• 管理者與高權限角色正式環境必須啟用多因素驗證。

• Service-to-Service 使用短效身份與最小權限，不以長期靜態金鑰模擬使用者。

### 4.2 Authorization｜RBAC＋ABAC

RBAC 決定角色可執行的功能；ABAC 再依 tenant_id、elder_id、care_unit_id、relationship_id、assignment_id、share_scope、consent_version、time_window、resource_status 與 purpose 判斷是否允許。

### 4.3 角色基準

長者

• 可使用自己的語音互動、同意、偏好與候選記憶確認。

• 可撤回同意、停用或刪除自己的記憶與分享。

日照照服員

• 只能查看所屬 Care Unit 且被授權的長者。

• 可覆核事件、查看專業摘要與建立 Care Action。

• 不得因同據點而自動取得所有長者的全部資料。

居服員

• 只能查看有效 Care Assignment 的長者與服務所需最小資料。

• Assignment 取消、過期或範圍改變後立即收回權限。

家屬

• 只能查看有效 Family Relationship、Share Scope 與 PUBLISHED 報表。

• 不可查看逐字稿、專業版摘要、內部筆記、未覆核事件、ASR 信心與 Agent Trace。

• 不可修改正式事件、記憶、派案或專業照護待辦。

管理者

• 管理身份、Policy、來源與系統設定，但仍受 tenant、purpose 與資料最小化限制。

• 不因管理角色自動取得所有 Restricted 內容。

### 4.4 Deny by Default

沒有明確 Allow 條件時一律拒絕；任何查詢即使已在前端過濾，後端仍需重新驗證。

## 五、Session、Token 與裝置安全

• Access Token 短效，Refresh Token 可撤銷並綁定裝置或 Session。

• Token 不放在 URL Query、前端日誌、錯誤訊息或 Analytics。

• Web 使用安全 Cookie 或等效保護，避免前端腳本直接讀取敏感 Token。

• Session 需防止 CSRF、重放、固定 Session 與不安全登出。

• 角色、派案、同意或家屬分享變更後，相關 Session／Cache／Secure Link 必須失效或重新授權。

• 受控長者裝置可延長 Session，但資料控制、刪除、家屬分享與管理功能需再次驗證。

• 裝置遺失時應支援遠端撤銷 Session 與清除本機敏感快取。

• 居服員離線草稿在未完成裝置加密、期限、遠端清除與衝突處理前不啟用。

## 六、資料傳輸、儲存與金鑰保護

### 6.1 傳輸中

• 對外與服務間通訊使用加密傳輸。

• 不允許以明文傳輸語音、逐字稿、Token、家屬報表或服務紀錄。

• WebSocket／串流語音連線需身份驗證、時效與重連限制。

### 6.2 靜態資料

• RDS、Object Storage、Graph、Search／Vector、備份與日誌使用受控加密。

• Restricted 與 Confidential 資料依環境與用途分離存取。

• Object Storage 禁止公開 Bucket／Object；使用短效、限用途存取。

• Secure Link Token 只保存雜湊或不可逆驗證值，不保存可直接重用的明文 Token。

### 6.3 金鑰與 Secrets

• Secrets 不提交 Git、Docker Image、前端 Bundle、文件範例或 CI 日誌。

• 開發、測試、正式環境使用不同 Secrets 與資料資源。

• 金鑰與 Secrets 定期輪替；發現洩漏可立即撤銷。

• 應用程式只取得執行任務所需的 Secret，不共享全域管理金鑰。

## 七、資料最小化、同意與目的限制

### 7.1 Purpose-Based Consent

BASIC_VOICE、TRANSCRIPT_STORAGE、CARE_EVENT_EXTRACTION、LONG_TERM_MEMORY、COMPANION_SIGNAL_ANALYSIS、PROACTIVE_COMPANION 與 FAMILY_SHARING 分開記錄。

### 7.2 Processing Gate

任何背景工作在執行前重新檢查：

elder_id → consent purpose → consent_version → effective_at／expires_at → actor／service purpose → policy_version。

### 7.3 Consent Snapshot

正式事件、記憶、報表、Trigger 與刪除工作保存實際使用的 consent_version，不只讀取目前狀態。

### 7.4 撤回

• 撤回生效後立即停止新增處理，不等待實體刪除完成。

• 排程、重試、DLQ 重放與主動 Trigger 也必須重新通過 Consent Gate。

• 分享撤回後停止新報表、通知與安全連結。

### 7.5 Data Minimization

• Agent Context 只注入當前任務所需資料。

• 家屬版內容只取可分享且已發布的摘要。

• Graph 查詢只回傳相關子圖，不回傳整個長者關係網。

• 日誌保留識別碼、狀態與 reason_code，避免完整逐字稿和 Prompt。

## 八、資料保存、刪除與備份原則

• 每種資料需有 Retention Policy、Owner、保存期限、刪除方式與例外理由。

• 原始音訊預設不永久保存；實際期限待場域與法務決定。

• 逐字稿、候選事件、已確認事件、摘要、記憶、報表、通知與 Audit 分別設定期限，不使用同一全域期限。

• 刪除採 Deletion Request＋Deletion Job Item，可追蹤 RDS、Object Storage、Graph、Index、Cache、通知與備份處理。

• Graph、Index 或 Cache 清理失敗時，Consent／Authorization Gate 仍先阻擋讀取。

• 備份需有保存期限、加密與還原測試；刪除請求對備份的處理方式須由法務與架構共同定義。

• 為防止已刪資料因重放重新出現，可保存最小 Tombstone／Deletion Marker，不保留被刪內容。

## 九、日誌、稽核與隱私保護

### 9.1 必須稽核

• 登入、登出、MFA 變更與高權限操作。

• 權限授予、撤銷、Relationship、Assignment 與 Share Scope 變更。

• Consent Granted／Changed／Revoked。

• Event Review、Memory Confirm／Deactivate／Delete。

• Report Publish／Withdraw、Secure Link 建立／撤銷。

• Deletion Request 與各 Job Item 結果。

• 安全 Policy 阻擋、跨 tenant／elder 拒絕與異常大量查詢。

### 9.2 日誌最小欄位

trace_id、actor_id、actor_role、tenant_id、elder_id（必要時 Tokenize）、action、resource_type、resource_id、result、reason_code、policy_version、timestamp。

### 9.3 禁止紀錄

密碼、Access Token、Refresh Token、Secret、Secure Link 明文、完整信用或身份資料、完整原始語音、完整逐字稿與不必要 Prompt Context。

### 9.4 防竄改與存取

安全稽核與普通應用程式日誌分開；只允許必要人員存取，並保留存取稽核。

## 十、家屬 App、LINE／Email 與安全連結

• App／Web 是正式報表介面；LINE／Email 只提供最小預覽與導流。

• 通知內容避免包含用藥、健康、家庭衝突、地址等敏感細節。

• Secure Link 需綁 recipient_id、report_id、有效期限、用途與撤銷狀態。

• URL 不包含 elder_name、診斷、Token 明文或其他敏感 Query。

• 連結被轉傳時仍需身份或一次性驗證，不可只靠知道 URL。

• report Withdrawn、Consent Revoked、Relationship Expired 後連結立即失效。

• 開啟連結時再次驗證 report 仍為 PUBLISHED 且 Share Scope 有效。

• Email 防止將完整報表作為永久附件；LINE 不作為正式資料保存來源。

## 十一、Agent、RAG 與 Tool Calling 安全

### 11.1 Trust Boundary

使用者語音、逐字稿、RAG 文件、Graph 內容、外部 API 回應與 Tool Output 全部視為不可信輸入，不得因來源是資料庫就跳過安全檢查。

### 11.2 Prompt Injection 防護

• System Policy、權限與資料用途不由檢索內容或使用者指令覆寫。

• RAG Chunk 只作為資料，不被當成可執行指令。

• 檢索與生成分離，保留來源與適用範圍。

• 對「忽略規則、顯示其他長者、輸出系統提示、呼叫未授權工具」等要求直接拒絕。

### 11.3 Tool Allowlist

• 每個 Agent 只能使用明確 Allowlist 工具。

• Tool Schema 限制 elder_id、tenant_id、resource_type、action 與最大查詢範圍。

• 任何寫入、發布、通知、刪除與高風險查詢由確定性程式再次授權。

• 不讓模型自行產生可執行 SQL、Graph Query 或任意 URL 並直接執行。

### 11.4 Context Isolation

• Context Builder 先取得授權範圍，再查詢資料。

• 每個資料片段帶 elder_id、tenant_id、status、consent_version 與 source_id。

• 生成前與生成後都檢查是否包含其他長者資料。

• 張阿姨資料不得進入林阿嬤 Prompt、Tool Input、Graph 子圖或回覆。

### 11.5 Output Safety

• 醫療診斷、改藥、停藥、緊急風險推斷、歧視與羞辱內容被阻擋或安全降級。

• 家屬輸出再做 Share Scope、敏感內容與 PII 檢查。

• Agent 不得將未確認記憶或候選事件當作事實。

### 11.6 Agent Trace

保存 model_version、prompt_version、tool_name、source_ids、policy_result、reason_codes 與 trace_id；不保存不必要完整敏感 Prompt。

## 十二、主動陪伴安全

• 主動陪伴需要獨立同意，不沿用一般對話同意。

• 播放前重新檢查 consent、quiet_hours、daily_limit、cooldown、device_state、active_session、recent_rejection 與 source_status。

• Trigger 不能只因「多日未互動」自動判定孤獨或危險。

• 健康、財務、家庭衝突、創傷與其他敏感話題需人工核准或禁止。

• 長者說停止、不要再聊、稍後再說後立即停止；重試不得繞過拒絕。

• 主動內容一次一題、簡短、可退出，不用恐嚇、施壓或情緒操控。

• Trigger、Eligibility、Approval、播放與回饋全部可追溯。

## 十三、Threat Model 方法與信任邊界

### 13.1 信任邊界

TB-01｜長者／照服員／居服員／家屬裝置 ↔ 公開入口。

TB-02｜公開入口 ↔ 應用程式與身份服務。

TB-03｜應用程式 ↔ Agent／模型與 Tool Layer。

TB-04｜應用程式 ↔ RDS／Object Storage／Graph／Search／Cache。

TB-05｜報表服務 ↔ LINE／Email 等外部通知通路。

TB-06｜CI/CD、管理者與雲端控制平面。

### 13.2 威脅分類

• Spoofing：冒用長者、照護者、家屬或系統服務。

• Tampering：竄改事件、記憶、報表、派案、Prompt 或稽核紀錄。

• Repudiation：否認曾授權、覆核、發布或刪除。

• Information Disclosure：跨長者、跨 tenant、通知或日誌洩漏。

• Denial of Service：語音、模型、通知或資料庫資源耗盡。

• Elevation of Privilege：從家屬、居服員或一般管理者提升權限。

## 十四、核心威脅與控制

T-01｜登入冒用

情境：攻擊者取得照護者或家屬帳號。

控制：MFA、高風險再次驗證、短效 Token、異常登入偵測、Session 撤銷。

T-02｜IDOR／修改 elder_id 越權

情境：家屬或居服員修改 URL／API 參數查看其他長者。

控制：後端逐請求 ABAC、Relationship／Assignment 驗證、Deny by Default、Isolation Test。

T-03｜跨 tenant 資料洩漏

情境：查詢、Cache、Graph 或搜尋過濾漏掉 tenant_id。

控制：統一 ElderScope、Repository 強制條件、Policy Test、資料分區與稽核告警。

T-04｜派案過期後仍可存取

控制：每次讀取重新驗證 Assignment 狀態與時間；變更時失效 Session／Cache。

T-05｜家屬看到 Draft／Needs Review

控制：Family Report Repository 只允許 PUBLISHED；前後端皆不可用前端隱藏代替授權。

T-06｜Secure Link 被轉傳

控制：短效、綁 Recipient、一次性或再次驗證、可撤銷、Token 雜湊與開啟稽核。

T-07｜通知內容洩漏

控制：LINE／Email 最小預覽、敏感內容移除、完整內容回 App、錯誤地址驗證與取消訂閱。

T-08｜Prompt Injection 取得其他資料

控制：資料與指令分離、Tool Allowlist、Context Scope、輸出 DLP／PII 檢查與越權拒絕。

T-09｜惡意 RAG 文件

控制：來源允許清單、檔案掃描、審查狀態、Chunk Metadata、指令無效化與引用追溯。

T-10｜Agent 任意呼叫工具

控制：細粒度 Tool 權限、Schema、最大範圍、寫入二次授權、Approval Gate。

T-11｜未確認記憶被引用

控制：只檢索 ACTIVE、confirmed_at 與 consent_version 有效的記憶。

T-12｜Graph 過度揭露關係

控制：查詢前後 Authorization Filter、最小子圖、禁止全圖匯出、Graph 為投影非授權來源。

T-13｜原始語音／逐字稿外洩

控制：短期保存、加密、受控 URL、日誌排除、權限隔離與刪除流程。

T-14｜模型或服務供應商取得過量資料

控制：最小 Context、去識別／遮罩、資料處理設定、禁止把完整資料集送進模型、供應商風險審查。

T-15｜重送造成重複通知或資料

控制：idempotency_key、唯一鍵、Outbox、Consumer 去重與送達狀態。

T-16｜刪除後資料從 Graph／Index 重建

控制：Deletion Marker、Consent Gate、Projection Filter、Outbox 重放前檢查 source status。

T-17｜Log Injection／敏感錯誤外洩

控制：結構化日誌、輸入編碼、錯誤頁不顯示內部堆疊、敏感欄位遮罩。

T-18｜CI/CD Secret 洩漏

控制：Secret Manager、最小 CI 權限、禁止輸出 Secret、依賴與映像掃描、環境隔離。

T-19｜DoS／成本耗盡

控制：Rate Limit、Quota、最大錄音長度、最大 Context、模型 Timeout、佇列背壓與預算告警。

T-20｜主動陪伴騷擾或情緒操控

控制：獨立同意、頻率上限、冷卻、靜默時段、拒絕記錄、敏感話題核准與可退出設計。

## 十五、非功能需求 NFR

以下為 v0.1 工程基準，正式數值需經技術 Spike、預算與場域驗證。

### 15.1 Performance｜效能

• 使用者操作後 300 ms 內顯示已接收或 Loading 狀態。

• 語音停止後 ASR final transcript 目標 p95 ≤ 5 秒。

• LLM 文字回覆目標 p95 ≤ 10 秒。

• TTS 首段可播放目標 p95 ≤ 5 秒。

• 專業照護首頁與長者詳情 API 目標 p95 ≤ 2.5 秒。

• 家屬 Published 報表頁目標 p95 ≤ 3 秒。

• 非同步摘要、Graph 投影與通知不阻塞主要語音回覆。

### 15.2 Availability｜可用性

• 正式產品核心讀取與登入的初始月可用性目標為 99.5%，待成本與架構確認。

• Graph 不可用時，基本語音與 RDS 事實仍可運作，個人化關係查詢降級。

• 通知服務不可用時，App／Web 報表仍可查看。

• 模型不可用時，提供固定安全回覆與稍後再試，不假裝生成成功。

### 15.3 Reliability｜可靠性

• 正式寫入、Outbox 與狀態轉移具交易保護。

• 背景工作至少一次投遞，Consumer 冪等。

• 摘要、通知、投影與刪除工作有最大重試、DLQ 與人工處理。

• 重要操作不得 Silent Failure。

### 15.4 Scalability｜擴充性

• 以 tenant、elder、care_unit、assignment 與日期作為主要分區與查詢維度。

• 語音 Session、摘要、通知與 Graph 投影可獨立擴充。

• Rate Limit 依角色、裝置、tenant 與服務設定。

### 15.5 Recoverability｜恢復能力

• 初始 Production Baseline：RPO 目標 15 分鐘、RTO 目標 4 小時，待架構與成本核准。

• RDS、Object Storage 與設定需有備份及定期還原演練。

• Graph、Search／Vector 與 Cache 可由正式資料重建。

• 還原後仍需重新套用 Consent、Deletion Marker 與目前授權狀態。

### 15.6 Observability｜可觀測性

• 以 trace_id 串起 Voice、ASR、Agent、TTS、Event、Memory、Graph、Summary、Report 與 Notification。

• Dashboard 至少顯示延遲、錯誤率、重試、DLQ、通知成功率、投影延遲、權限拒絕與安全攔截。

• 告警需有 Owner、Severity、處理手冊與升級路徑。

### 15.7 Accessibility｜無障礙與長者可用性

• 長者端提供大按鈕、清楚狀態、語音提示、重新播放與不責怪使用者的錯誤文案。

• 不以顏色作為唯一狀態提示。

• 重要操作可取消、返回與再次確認。

• 專業照護端與家屬端支援鍵盤、可讀標籤、合理字級與對比。

### 15.8 Maintainability｜可維護性

• Policy、Prompt、Model、Schema 與 Retention Rule 版本化。

• Domain 邏輯與雲端服務實作分離。

• 每個工作流有 Owner、Runbook、測試與回滾方法。

### 15.9 Cost Control｜成本控制

• 語音、模型、Graph 與通知皆有使用量與預算告警。

• 限制最大錄音、Context、檢索數量、生成長度與重試次數。

• 非必要背景分析不因每次對話全部重跑。

## 十六、安全測試與驗收

### 16.1 Authentication／Authorization

• 未登入、Token 過期、Session 撤銷與角色停用。

• 修改 elder_id、tenant_id、care_unit_id、assignment_id、report_id。

• 日照、居服、家屬與管理者互相嘗試越權。

• Assignment／Relationship／Consent 在 Session 中途失效。

### 16.2 Privacy

• 日誌、錯誤頁、Analytics、URL、Email 與 LINE 不出現 Restricted 明文。

• 撤回同意後停止新處理。

• Secure Link 過期、撤銷、轉傳與重複使用。

• 刪除後 RDS、Object Storage、Graph、Index、Cache 與前端皆不可讀。

### 16.3 Agent／RAG

• Prompt Injection、系統提示索取、跨長者資料索取。

• 惡意 RAG Chunk、外部 Tool Output 與 HTML／Markdown 注入。

• Agent 嘗試呼叫未允許工具、擴大範圍或執行寫入。

• 未確認記憶、Rejected Event 與 Draft Report 不得進 Context。

### 16.4 Reliability

• ASR／LLM／TTS timeout。

• RDS 成功、Graph 失敗。

• Report Published、LINE 失敗。

• DLQ 重放與 idempotency。

• 備份還原後 Consent／Deletion 狀態仍正確。

### 16.5 Security Tooling

• 靜態程式碼、依賴、Secret、容器映像與 Infrastructure 設定掃描。

• API／Web 動態測試與授權測試。

• 雲端權限與公開儲存檢查。

• 高風險修正後重新測試，不只關閉告警。

## 十七、Secure SDLC 與環境治理

• 開發、測試、Demo 與正式環境分離，不共享資料庫、Bucket、Secret 與管理帳號。

• Pull Request 需通過測試、依賴掃描、Secret Scan 與必要安全審查。

• Infrastructure 與 Policy 變更版本化並可回滾。

• Production 禁止直接手動修改正式資料，例外操作需 Ticket、核准與 Audit。

• Demo 使用虛擬 Persona、合成語音或明確同意的測試資料。

• 第三方套件、模型、MCP、外部 API 與通知服務需列入 Dependency Inventory。

• 不把真實正式資料下載到個人電腦、Notebook 或公開測試工具。

## 十八、Incident Response 基準

### 18.1 Severity

SEV-1：大規模資料洩漏、跨 tenant 越權、金鑰洩漏或核心服務全面不可用。

SEV-2：單一 tenant 敏感資料風險、刪除失敗、家屬錯誤收件或高風險 Agent 越權。

SEV-3：局部功能失敗、有限錯誤內容、通知延遲或非敏感安全弱點。

### 18.2 處理流程

偵測 → 限制影響 → 撤銷 Token／Secret／Session → 保存證據 → 修復 → 還原 → 驗證 → 通報與事後檢討。

### 18.3 最低能力

• 可快速停用通知、主動陪伴、特定 Agent Tool、家屬分享或特定 tenant。

• 可撤銷 Secure Link、Session、Service Credential 與外洩 Secret。

• 可依 trace_id、actor_id、elder_id 與時間範圍追查。

• 事後建立 Root Cause、影響範圍、修復與防再發項目。

## 十九、風險登錄 v0.1

R-01｜跨長者 Context 混入｜Impact：Critical｜控制：ElderScope、雙重 Filter、Isolation Test。

R-02｜家屬收到錯誤或過度敏感通知｜Impact：High｜控制：Share Scope、人工核准、最小通知。

R-03｜居服派案失效仍可查看｜Impact：High｜控制：逐請求 Assignment 驗證與即時撤銷。

R-04｜Prompt Injection 呼叫未授權工具｜Impact：Critical｜控制：Tool Allowlist、Schema、二次授權。

R-05｜刪除後投影重建｜Impact：High｜控制：Deletion Marker、Consent Gate、Projection Filter。

R-06｜語音／逐字稿保存過久｜Impact：High｜控制：短期 Retention、到期刪除、監控。

R-07｜Graph 暫停影響 Demo｜Impact：Medium｜控制：RDS 降級與預先準備重建腳本。

R-08｜LINE／Email 發送失敗｜Impact：Medium｜控制：App 為正式來源、有限重試與告警。

R-09｜模型輸出醫療建議｜Impact：Critical｜控制：Safety Policy、固定降級、紅隊測試。

R-10｜團隊為趕 Demo 使用真實資料｜Impact：Critical｜控制：Demo Data Gate、虛擬 Persona、Repo／Drive 檢查。

## 二十、v0.1 完成判定

□ 角色、身份、RBAC＋ABAC、Relationship、Assignment 與 Share Scope 已定義。

□ Restricted、Confidential、Internal 與 Public 資料已分類。

□ RDS、Object Storage、Graph、Search／Vector、Cache、日誌與通知保護規則已定義。

□ Consent、撤回、Retention、Deletion 與備份處理原則已定義。

□ Agent、RAG、Tool Calling、Context Isolation 與 Output Safety 已定義。

□ 主動陪伴安全條件已定義。

□ 至少 20 項核心威脅與控制已記錄。

□ Performance、Availability、Reliability、Scalability、Recoverability、Observability、Accessibility 與 Cost NFR 已建立基準。

□ 安全測試、Secure SDLC、Incident Response 與 Risk Register 已建立。

□ Demo 不使用真實長者資料，且可展示一條越權阻擋及一條失敗降級證據。

## 二十一、待決策

1. 正式身份服務、MFA 與長者受控裝置登入方式為何？

2. 家屬安全連結採一次性驗證、登入後跳轉或 LINE Login？

3. 原始音訊、逐字稿、事件、摘要、報表與 Audit 的保存期限為何？

4. 哪些家屬報表內容必須人工核准？

5. 多機構共同照護時跨 tenant 授權如何建立與撤銷？

6. 居服員離線草稿是否納入，裝置遺失時如何遠端清除？

7. 模型與外部服務是否會保存請求資料，正式環境可接受的設定為何？

8. Production RTO、RPO、可用性與預算目標是否接受 v0.1 基準？

9. 哪些 Security Audit 需要保存較長時間或不可匿名化？

10. 團隊五人中誰負責 Security Owner、Privacy Owner、Incident Commander 與 Access Review？

## 二十二、下一份文件

08｜智慧長照 AI 陪伴系統－AWS 系統架構、服務選型與 ADR v0.1

08 文件將根據 05、06、07 決定：

• 前端、API、Identity、語音、Agent、Workflow、RDS、Graph、Search／Vector、Object Storage、通知與可觀測性如何部署。

• 哪些 AWS 服務負責同步與非同步工作。

• 網路、帳號、環境、加密、備份、RTO／RPO 與成本架構。

• 每個重要服務選擇的 ADR、替代方案、理由、限制與退場策略。
