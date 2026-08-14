# ADR 0013：分離登入帳號與長者主體，並以 Enrollment 與 Entitlement 管理服務

- 狀態：Accepted
- 日期：2026-08-14
- Owner：Project Owner
- 部分取代：ADR 0012 的 Decision 1、`ELDER` 帳號角色假設與 elder registration rollout 用語
- 不取代：ADR 0012 的 Kinsun 自有帳號、可綁第三方 Authenticator、Email OTP 與 Core App Session 決策
- 相關：[ADR 0003](0003-core-api-framework-and-schema-authority.md)、[ADR 0010](0010-provider-neutral-oidc-and-application-sessions.md)、[ADR 0011](0011-bounded-empty-account-consolidation.md)、[ADR 0012](0012-kinsun-owned-account-and-linked-authenticators.md)

## 背景

Kinsun 未來同時服務日照中心、長照機構、居家照護、家庭照護、家屬與系統管理者。一個機構可以有數十位長者，但只有少數管理者與照服員需要登入。要求每位長者建立 Email、密碼或 OAuth 帳號，會把「被照護者」錯誤建模成「登入 Principal」，也會造成共用帳號、冒充長者、離開機構時難以撤權及資料歸屬不清。

目前 Core 已有獨立 `actor`、`elder`、`tenant`、`actor_tenant_membership`、`care_relationship` 與 `care_assignment`，Conversation、Memory、Care Event、Daily Summary 與 Consent 也多數已以 `elder_id` 為照護主體。主要缺口是 onboarding 仍可能同時建立 Actor、Household Tenant、Membership 與 Elder；`actor_type=ELDER` 仍混合產品 Persona 與登入授權角色；`elder.tenant_id` 又讓一位長者只能屬於單一服務情境。

此外，「機構購買 Kinsun」與「機構照顧某位長者」是不同事實。若沒有獨立的服務關係與方案權益，系統無法安全表達長者離開機構、轉到另一機構、回家繼續使用，或機構停止付費後應停用哪些功能。

## 決策

### 1. Account Principal 與 Care Subject 分離

1. `Actor` 是 Core 的 Principal；對人類使用者而言，產品語言稱為 User Account。
2. `Elder` 是被照護者的 Domain Entity，不是登入帳號，也不必有 Email、密碼、Passkey、Google 或 LINE identity。
3. Authentication、Authenticator、App Session 與 Login Audit 只屬於 Actor／User Account。
4. `actor_type=ELDER` 成為 legacy compatibility 值；Target Authorization 不得要求 Elder 一定具有 Actor，也不得以該值作為存取長者資料的充分條件。
5. 現有 nullable、unique `elder.actor_id` 可在過渡期表達「這位長者選擇性連結自己的 User Account」。它不是 Elder 存在的前置條件。只有需要連結歷史、多帳號政策或審核狀態時，才另立 ADR 評估 `elder_user_link` 表。

### 2. Tenant 表達服務與資料隔離情境

1. Target 概念使用 `Organization` 與 `Household`；MVP 優先重用現有 `tenant`，不立即進行實體表改名。
2. 機構、日照中心、居服單位與家庭是不同 Tenant／Service Context。
3. `actor_tenant_membership` 只連結可登入 Principal 與 Tenant，角色屬於該 Membership，不是 Actor 的永久全域身份。
4. 同一 Actor 可以在多個 Tenant 擁有不同角色；登入成功不會自動取得任何 Elder 資料。

### 3. Enrollment 表達 Elder 接受服務的關係

Target 新增邏輯實體 `elder_enrollment`：

```text
elder_enrollment
- enrollment_id
- elder_id
- tenant_id
- care_unit_id nullable
- enrollment_type
- status
- valid_from
- valid_until nullable
- ended_reason nullable
- created_by_actor_id
- created_at / updated_at
```

Enrollment 表示「哪位 Elder 在哪個 Organization／Household、哪段期間接受服務」，而不是帳號或資料所有權。Elder 可以沒有帳號，也可以先後或在政策允許下同時具有多筆 Enrollment。

### 4. Entitlement 表達誰購買服務與可使用功能

Target 新增邏輯實體 `service_entitlement`：

```text
service_entitlement
- entitlement_id
- tenant_id
- plan_code
- status
- valid_from
- valid_until nullable
- feature_set / limits
- billing_owner_reference nullable
- created_at / updated_at
```

Entitlement 決定 Tenant 可否建立新 Session、使用哪些功能及容量；它不授予某個 Actor 對任意 Elder 的資料權限，也不代表購買者擁有 Elder 身份或全部資料。

### 5. Authorization 採 RBAC 加 Elder-scoped ABAC

存取 Elder Data 至少同時驗證：

```text
authenticated Actor
  + active tenant membership and role
  + active elder enrollment in selected service context
  + care relationship or care assignment
  + requested action / share scope
  + consent, purpose and effective time
  + resource tenant/data-custody context
```

MVP 重用 `care_relationship` 與 `care_assignment` 表達 family、legal representative、日照與居服存取，不先建立通用 `elder_access_grant`。只有現有模型無法表達逐項能力、臨時委任或跨機構共同照護時，才新增 grant 模型。

### 6. Care Data ownership

1. Conversation、Memory、Confirmed／Candidate Memory、Care Event、Daily Summary、Care Insight、Consent、Follow-up、Care Task、Family Notification、AI Interaction 與 Timeline 必須以 `elder_id` 作為 Care Subject ownership。
2. 需要隔離或判定資料保管責任的資源，同時保存 `tenant_id` 或等價的 service/data-custody context。
3. `elder_id` 相同不代表所有 Tenant 都能互讀資料；授權仍以資料建立情境、關係、同意、目的與保存政策判斷。
4. Client 傳入的 `elder_id`、`tenant_id`、role 或 initiator 只可視為 target／hint；Server 必須從已驗證 Session 與 Core records 重新推導。

### 7. 無帳號長者與代啟動 Session

1. Staff 或家庭照護者登入後，可以在有效 Membership、Enrollment、Relationship／Assignment、Consent 與 Entitlement 下選擇 Elder 並啟動 Elder Session。
2. Elder Session 必須保留 `elder_id`、service context、initiating actor、授權依據、consent/policy version 與 trace。
3. Elder 不需要登入，介面也不得把 Staff／Family Session 顯示成 Elder 自己完成了 Authentication。
4. 高風險資料管理、分享、刪除與同意操作仍要求具權限 Actor，必要時再次驗證。

### 8. 離開機構、轉換場域與居家續用

1. 長者離開機構時，結束該 `elder_enrollment`，撤銷相關 assignment、staff access、未開始 Session、device authorization 與後續自動排程。
2. 不刪除 Elder，不刪除長者可能擁有的 User Account，也不把帳號交給機構處理。
3. 若原服務由機構購買，Enrollment 或 Entitlement 結束後，長者不會自動免費繼續使用該機構方案。
4. 居家續用需要建立 Household Tenant／Context、有效 Household Enrollment 與 Household Entitlement。可由家屬帳號代為啟動；長者仍可沒有帳號。
5. 不自動把機構內部筆記、照護任務、員工稽核或受契約管制資料搬到家庭。可攜資料範圍必須經長者／合法代理人授權、資料分類、原 Tenant 責任與保存政策核准。

## 資料分類與攜出原則

| 分類 | 例子 | 離開機構後預設處理 |
| --- | --- | --- |
| Elder subject data | 基本資料、語言與溝通偏好 | Elder 保留；跨 Tenant 使用需核准的連結或移轉流程 |
| 可攜候選資料 | 長者確認記憶、核准發布摘要、可理解匯出 | 經 Consent、目的與接收 Tenant 驗證後匯出或匯入 |
| Tenant operational data | 照服員內部筆記、排班、任務、服務紀錄 | 原 Tenant 依契約與保存政策保留；不自動分享 |
| Security/audit data | 登入、授權、操作與事故紀錄 | 由原資料控制責任方依安全與法規政策保存 |
| Derived AI data | Candidate、Embedding、Graph／Search projection | 依來源資料、Consent、Tenant scope 同步撤銷、重建或刪除 |

正式產品上線前，資料控制者、共同控制、委外處理、保存期限與可攜範圍仍須法務、資安及合作機構核准。本 ADR 不構成法律意見。

## 最少變更落地策略

### 重用

- `actor`：登入 Principal；暫不物理改名為 `users`。
- `external_identity`／Kinsun identity 與 `app_session`：Authenticator 與 Session。
- `tenant`：Organization／Household 的服務與隔離情境。
- `actor_tenant_membership`：User 對 Tenant 的角色與 scope。
- `elder`：Care Subject；保留現有 `elder_id`。
- `care_relationship`：Family、Legal Representative 及既有關係授權。
- `care_assignment`：照服員／居服員的有效派案。

### Target 必要新增

- `elder_enrollment`
- `service_entitlement`

### 暫不新增

- 實體 `users`／`organizations` 改名：只增加 migration 風險，無法立刻改善 Domain boundary。
- `elder_access_grant`：先驗證 relationship／assignment 是否足夠。
- `family_link`：先重用 `care_relationship(FAMILY_SHARE／LEGAL_REPRESENTATIVE)`。
- `elder_user_link`：先重用 nullable `elder.actor_id`；需要歷史或複數連結時再拆。
- Password credential：Email OTP 已定案；Passkey 另期處理。

## 遷移原則

採 Expand → Migrate → Contract，禁止重建正式資料庫或合併既有 migration 歷史：

1. Expand：新增 Enrollment／Entitlement 與必要索引；既有 `elder.tenant_id`、`elder.actor_id` 不刪除。
2. Backfill：依現有 Tenant、Elder、Membership、Relationship 與 Assignment 建立可稽核的 Enrollment／Entitlement；無法判定者進人工清單。
3. New-write：新建 Elder 不再要求 Actor；新 Session 必須寫入可驗證 service context 與 initiator。
4. Compatibility：讀取期間可由新模型優先、舊欄位 fallback；每次 fallback 記錄 metric。
5. Authorization cutover：所有 Elder 資料入口改以 Membership＋Enrollment＋Relationship／Assignment＋Consent 判斷。
6. Validate：驗證 cross-elder、cross-tenant、expired enrollment、expired entitlement、revoked assignment、離場撤權及 household continuation。
7. Contract：fallback 歸零且 rollback window 結束後，另立 migration／ADR 決定是否移除 `elder.tenant_id` 依賴與 legacy `actor_type=ELDER` 路徑。

## 後果

### 正面

- 機構可以建立大量無帳號 Elder Profile，符合真實日照與長照作業。
- 家屬、照服員與長者不必共用帳號，也不需冒充 Elder。
- 長者離場、轉換場域與日後自行登入不需要搬動既有 `elder_id` 照護歷史。
- 付費權益、照護關係與資料存取成為三個可獨立撤銷的邊界。

### 代價

- 所有 onboarding、role routing、tenant selection 與 Session creation 都要區分 Principal 與 Care Subject。
- `elder.tenant_id` 的單 Tenant 假設需要分階段解除，不能一次 drop。
- 跨 Tenant 資料可攜需要產品、契約、Consent 與法規共同決策，不能只靠技術 FK 解決。
- 過渡期會同時存在 legacy `ELDER` Actor 與無帳號 Elder，測試矩陣會增加。

## 未採方案

### 每位 Elder 強制建立 User Account

不符合日照／機構作業，會導致虛假 Email、共用密碼與帳號代操作風險。

### 機構帳號持有 Elder 全部資料

把服務購買者誤當成 Care Subject 或全部資料的永久所有者；長者離場與資料可攜會失去清楚邊界。

### 立即新增完整通用 Grant／Organization／Link 表群

會在需求尚未驗證前增加十多張表及 migration 風險。現有 Tenant、Membership、Relationship、Assignment 與 nullable link 足以支撐第一階段。

### Elder 離場時複製全部資料到 Household

可能洩漏機構內部紀錄、破壞來源與稽核語意，也忽略原 Tenant 的保存責任。

## 實作前 Gate

- Product Owner 核准 Enrollment 與 Entitlement 的狀態機及方案規則。
- Data Governance／法務核准資料分類、可攜與離場保存政策。
- Backend 提交實際 migration proposal、backfill 規則與 rollback 證據。
- Security 提交 staff-represented Elder Session、device authorization 與即時撤權 threat model。
- Frontend 提交 Organization／Household onboarding、Elder selection、離場與續用 flow。

## 相關規格

- `docs/spec/06智慧長照 AI 陪伴系統－Domain Model、商業規則與資料生命週期 v0.1.md`
- `docs/spec/07智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1.md`
- `docs/spec/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`
- `docs/spec/16智慧長照 AI 陪伴系統－相容性、Deprecation、資料匯出與退場策略 v0.1.md`
- `docs/spec/17智慧長照 AI 陪伴系統－Account、Elder、Enrollment 與 Service Entitlement v0.1.md`
