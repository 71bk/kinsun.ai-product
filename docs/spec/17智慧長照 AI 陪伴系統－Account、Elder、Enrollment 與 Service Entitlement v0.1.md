# 智慧長照 AI 陪伴系統－Account、Elder、Enrollment 與 Service Entitlement v0.1

## 文件資訊

- 版本：v0.1
- 狀態：Accepted Target Domain Baseline｜尚未代表 schema、API 或 Frontend 已完成
- 決策日期：2026-08-14
- 文件 Owner：Project Owner／Backend／Identity／Data Governance
- 適用範圍：帳號、長者、機構、家庭、Membership、Enrollment、Entitlement、Elder Access、Session delegation、離場與居家續用
- 決策權威：[ADR 0013](../adr/0013-separate-account-elder-enrollment-entitlement.md)

## 一、目的與權威邊界

本文件把「User Account 與 Elder Profile 必須分離」轉成可實作、可測試的 Target Domain 規格。它補充並在衝突範圍內優先於既有 01～16 規格與 `.kiro/specs`：

```text
User / Actor = 可以登入並執行操作的 Principal
Elder        = 被照護者，可以完全沒有帳號
Enrollment   = Elder 在哪個服務情境、哪段期間接受服務
Entitlement  = 哪個 Tenant 購買哪些功能與容量
Access       = 哪個 Principal 因何種關係可對哪位 Elder 做什麼
```

本文件描述 Target，不宣稱 repo 已完成以下內容：

- `elder_enrollment`／`service_entitlement` schema
- Organization Admin 建立 Elder 的正式 API／UI
- Staff 選擇 Elder 後的 delegated／kiosk Session
- Elder 離場、轉移與 Household continuation workflow
- production billing、資料可攜或法規核准

現況仍以程式碼、Alembic、OpenAPI、測試與 `AGENTS.md` 為準。Target 與 Current 不得混寫。

## 二、核心 Domain Invariants

1. Elder 的存在不依賴 User Account、Email、Password、Passkey、Google 或 LINE。
2. User Account 的建立不自動建立 Elder、Tenant、Membership 或 Consent。
3. Authentication 成功只證明 Actor 身份，不代表可以讀取任何 Elder Data。
4. `ELDER` 不再是使用語音陪伴的必要 Authentication Role。
5. 所有照護主體資料以 `elder_id` ownership；需要資料隔離／保管責任時另帶 service context。
6. Membership、Enrollment、Entitlement 與 Elder Access 可以獨立啟用、到期及撤銷。
7. 結束 Enrollment 不刪 Elder、不刪 Account，也不改變 `elder_id`。
8. Entitlement 只授權功能與容量，不授權任意 Elder Data。
9. Staff／Family 代 Elder 啟動 Session 時，initiating actor 與 care subject 必須分別記錄。
10. Elder 日後建立自己的 Account，只新增 optional link，不搬 Conversation、Memory、Summary、Event 或 Consent。

## 三、Target Context Map

```text
Kinsun Identity & Access
├── Actor / User Account
├── Auth Identity / Authenticator
├── App Session / Login Audit
└── Tenant Membership + Role
              │
              │ authenticated principal and selected context
              ▼
Care Service Context
├── Tenant
│   ├── Organization
│   └── Household
├── Service Entitlement
└── Elder Enrollment
              │
              │ active service relationship
              ▼
Elder Care Domain
├── Elder
├── Care Relationship / Assignment
├── Consent
├── Conversation / AI Interaction
├── Memory / Care Event / Life Event
├── Daily Summary / Care Insight
├── Follow-up / Care Task
└── Family Notification / Timeline
```

User 對 Elder 的有效存取路徑：

```text
Actor
  ↓ active Tenant Membership + contextual Role
Tenant
  ↓ active Elder Enrollment
Elder
  ↑ Care Relationship / Assignment + scope + time
  ↑ Consent + purpose + resource state
```

## 四、實體定義

### 4.1 Actor／User Account

用途：代表可驗證、可登入、可稽核的 Principal。現行實體名稱保留 `actor`，產品 UI 可稱「使用者帳號」。

包含：

- Account status
- Auth identities／Authenticators
- Email＋Password（Email OTP 僅作註冊驗證／未來復原）、未來 Passkey、Google、LINE
- App Sessions
- Login／security audit
- Tenant memberships

不包含：

- Elder Profile ownership
- 因為登入就自動取得的 Elder scope
- 把長者 Persona 當成永久全域 Role

### 4.2 Elder

用途：代表被照護者的長期 Care Subject。

Target 欄位概念：

```text
elder_id
display_name
preferred_name
preferred_language
communication_preferences
timezone
status
created_at
updated_at
```

`elder.actor_id` 在過渡期只代表 optional self-account link。它必須 nullable，且所有核心 Elder 流程都要支援 null。

### 4.3 Tenant／Organization／Household

`tenant` 是現有技術與安全邊界。Target 產品語言將 Tenant 分成：

- Organization：日照中心、社區據點、長照機構、居服機構。
- Household：家庭自行購買或承接居家使用的服務情境。

本階段不要求把 `tenant` 實體表改名成 `organizations`。Organization 的法人、地址、統編、計費聯絡等商務欄位，只有在實際購買／管理流程需要時才擴充。

### 4.4 Organization Membership

現行 `actor_tenant_membership` 可直接重用。Role 屬於「Actor 在某個 Tenant 的權限」，不是永久貼在 Actor 身上的單一標籤。

Target Membership roles：

- `SYSTEM_ADMIN`：平台級管理；不因角色取得全部照護資料。
- `ORG_ADMIN`：管理單一 Organization 的成員、Enrollment 與 Entitlement 可見資訊。
- `ORG_STAFF`：機構一般工作人員。
- `CAREGIVER`：具有有效關係或 Assignment 時執行照護工作。
- `FAMILY`：仍須有效 Family Relationship 與 Share Scope。

同一 Actor 可以同時在不同 Tenant 擁有不同 Role。`ELDER` 原則上不是 Membership Role；長者自行登入的能力由 optional Elder link 與 self-access policy 決定。

### 4.5 Elder Enrollment

用途：記錄 Elder 在某個 Organization／Household 接受服務的有效期間。

建議最小模型：

| 欄位 | 必要性 | 說明 |
| --- | --- | --- |
| `enrollment_id` | Required | 主鍵 |
| `elder_id` | Required | Care Subject |
| `tenant_id` | Required | Organization／Household context |
| `care_unit_id` | Optional | 日照據點／服務單位 |
| `enrollment_type` | Required | DAYCARE、HOME_CARE、HOUSEHOLD 等 |
| `status` | Required | PENDING、ACTIVE、SUSPENDED、ENDED |
| `valid_from` | Required | 生效時間 |
| `valid_until` | Optional | 預定結束時間 |
| `ended_reason` | Optional | 離場、轉介、取消或其他原因碼 |
| `created_by_actor_id` | Required | 建立者稽核 |

Invariant：同一 Elder 是否可在同一 Tenant 擁有重疊 ACTIVE Enrollment，必須由唯一／排他條件阻擋；跨 Tenant 同時 Enrollment 則由產品與照護政策決定，不以資料庫全域禁止。

### 4.6 Service Entitlement

用途：記錄 Tenant 目前購買或獲配哪些服務能力。

建議最小模型：

| 欄位 | 必要性 | 說明 |
| --- | --- | --- |
| `entitlement_id` | Required | 主鍵 |
| `tenant_id` | Required | 方案持有人 |
| `plan_code` | Required | 方案代碼，不在程式寫死價格 |
| `status` | Required | TRIAL、ACTIVE、PAST_DUE、SUSPENDED、ENDED |
| `valid_from` | Required | 生效時間 |
| `valid_until` | Optional | 到期時間 |
| `feature_set` | Required | 可版本化能力集合 |
| `limits` | Optional | Elder 數、Session 數、通知等容量 |
| `billing_owner_reference` | Optional | 外部計費系統 reference，不存付款敏感資料 |

Invariant：Entitlement 可阻擋建立新付費資源或 Session，但不得單獨使歷史照護資料消失，也不得取代資料匯出、保存與刪除政策。

### 4.7 Elder Access

MVP 採既有模型組合：

- Family／legal access：`care_relationship`
- 日照／居服 access：`care_relationship` 與 `care_assignment`
- Tenant scope：`actor_tenant_membership`
- Service relation：`elder_enrollment`
- Feature availability：`service_entitlement`

暫不建立通用 `elder_access_grant`。若未來需要單一能力旗標，例如 `can_manage_consent` 或跨 Organization 臨時協作，先證明現有 scope 無法清楚表達，再以獨立 ADR 設計 grant。

### 4.8 Optional Elder Self Account Link

第一階段重用 nullable `elder.actor_id`：

```text
Elder E001
  └── actor_id = null              # 無帳號，完全合法

Elder E001
  └── actor_id = U100              # 日後完成驗證後自行登入
```

建立 link 必須：

- 明確選定既有 `elder_id`
- 完成足夠的身分／代理驗證
- 防止一個 Actor 誤綁多位 Elder 或接管既有 Elder
- 留下 audit、link status 與可撤銷證據
- 不搬移或複製 Elder Data

若上述 audit／history 無法由現有欄位安全支援，實作前必須改採獨立 `elder_user_link`，不得只為省表而犧牲接管防護。

### 4.9 Elder Session

不一定立即建立新 table，但所有 Session contract 必須能表達：

```text
elder_id                    # 對話主體
tenant_id / service_context # 使用情境與資料隔離
initiated_by_actor_id       # 實際登入並按下開始的人
initiator_mode              # SELF / STAFF_ASSISTED / FAMILY_ASSISTED / DEVICE
authorization_reference     # relationship / assignment / self-link / device enrollment
entitlement_reference
consent_version
policy_version
started_at / ended_at
```

`initiated_by_actor_id` 不得被寫成 Elder Actor 來掩蓋真實操作者。

## 五、資料 Ownership 與 Data Custody

### 5.1 Care Subject ownership

以下資料以 `elder_id` 為主要 ownership：

- Conversation／Voice Session／AI Interaction
- Candidate／Confirmed Memory
- Care Event／Life Event／Timeline
- Daily Summary／Care Insight
- Consent
- Follow-up／Care Task
- Family Notification／Report
- Graph／Search projection 的 Elder-scoped data

### 5.2 Service context

需要判斷跨 Tenant 隔離、資料保管或來源時，資源同時保存 `tenant_id` 或不可變的 source service context。不能因為多筆資料具有相同 `elder_id` 就直接跨 Tenant 合併查詢。

### 5.3 離場後資料處理

| 資料 | 原機構可否保留 | 家庭是否自動取得 |
| --- | --- | --- |
| Elder 基本資料與偏好 | 依契約／保存政策保留必要版本 | 否；需核准的連結、匯出或建立 Household context |
| 長者確認記憶 | 依 Consent 與來源保存 | 否；可列為資料可攜候選 |
| Published Summary | 依發佈與保存政策 | 否；只有有效分享或核准匯出可取得 |
| 機構內部筆記／任務／排班 | 是，依機構責任與保存政策 | 否 |
| 安全與稽核紀錄 | 是，依安全／法規政策 | 否 |
| AI Candidate／projection | 依來源狀態同步停用、刪除或重建 | 否 |

## 六、核心流程

### 6.1 機構建立無帳號 Elder

```text
ORG_ADMIN 登入並選定 Organization context
→ 驗證 active Membership 與 Entitlement
→ 建立 Elder Profile（不建立 Actor／Identity）
→ 建立 Organization Elder Enrollment
→ 指派 Care Unit／Caregiver
→ 設定 Consent／合法代理資料
→ Elder 出現在授權 Staff 的長者清單
```

### 6.2 Staff 代啟動語音陪伴

```text
Staff 登入
→ 選擇 Organization／Care Unit
→ Server 回傳授權 Elder 清單
→ Staff 選擇 Elder
→ 驗證 Membership + Enrollment + Assignment/Relationship
→ 驗證 Consent + Entitlement + active-session rule
→ 建立 STAFF_ASSISTED Elder Session
→ 切換長者模式
```

Staff 是 session initiator，不自動是 Speaker、Memory confirmer 或 consent actor。依
[Spec 18](18智慧長照%20AI%20陪伴系統－風險分級長期記憶、Speaker%20驗證與版本綁定確認%20v0.1.md)，
Staff MAY 見證「回答者確實是該 Elder、Elder 確實作出回答」，但 witness 不能替 Elder 說「好，記住」
或只按按鈕就完成 MEDIUM Memory confirmation；合法代理同意需另有明確權限模型。

### 6.3 家中無帳號使用

```text
Family／Caregiver 登入 Household
→ 選擇已 Enrollment 的 Elder
→ 驗證 Family Relationship／代理權限與 Entitlement
→ 啟動 FAMILY_ASSISTED 或 DEVICE Elder Session
→ Elder 直接語音互動，不需登入
```

Family／Caregiver 代啟動不會把其語句歸屬給 Elder；多人環境在 Speaker 未驗證前不得建立任何人的個人
Memory。若使用 WITNESSED_VOICE，仍必須由 Elder 本人回答，見證者不能取代同意。

如果沒有任何合法 User／Device 可以建立受控 Session，無帳號本身不等於匿名公開存取；系統必須先完成家庭邀請、裝置 enrollment 或其他核准的 bootstrap。

### 6.4 長者離開日照中心

```text
授權管理者提出結束 Enrollment
→ 顯示受影響 Assignment、Session、Device、Trigger、Notification
→ 記錄 ended_at／reason
→ 撤銷 Staff access 與未開始 Session
→ 停止該 Tenant 的新 AI interaction／排程
→ 依政策保存、匯出或刪除資料
→ Elder 與 optional User Account 均保留
```

### 6.5 機構付費結束後居家續用

```text
原 Organization Enrollment／Entitlement 結束
→ Family 建立或加入 Household
→ Household 取得有效 Entitlement
→ 對同一 Elder 建立 Household Enrollment
→ 完成 Consent、代理權與資料可攜選擇
→ 只把核准資料帶入 Household context
→ 使用同一 elder_id 繼續服務
```

沒有 Household Entitlement 時，可依退場政策提供有限期間的查看／匯出／刪除操作，但不保證可建立新的付費 AI Session。

### 6.6 長者日後自行登入

```text
建立 User Account
→ 完成 Kinsun 身分驗證與必要強化驗證
→ 明確選定既有 Elder
→ 人工或政策核准 link
→ 建立 self-access context
→ 原 Conversation／Memory／Summary／Consent 繼續屬於原 elder_id
```

## 七、Authorization 決策模型

每個 Elder-scoped request 必須回答：

```text
1. Who：哪個 Actor／Service Principal？
2. Where：目前選定哪個 Tenant／Care Unit context？
3. Whom：目標 elder_id？
4. Why：Membership、Enrollment、Relationship／Assignment 的依據？
5. What：要執行哪個 action、讀取哪種 resource？
6. When：所有 scope 是否仍在有效期間？
7. Consent：此 purpose／share scope 是否允許？
8. Entitlement：此 Tenant 是否可使用該功能？
9. Custody：該 resource 是否屬於此 service context，或有合法跨 context 授權？
```

任何一項不足即 deny-by-default。前端隱藏按鈕不是授權控制。

## 八、Target API 影響

以下只代表 Target resource shape；在 OpenAPI 與 route 實作前不得宣稱可用：

```text
POST /api/v1/organizations
POST /api/v1/organizations/{organization_id}/members/invitations
POST /api/v1/organizations/{organization_id}/elders
POST /api/v1/elders/{elder_id}/enrollments
POST /api/v1/elder-enrollments/{enrollment_id}/end
GET  /api/v1/me/authorized-elders
POST /api/v1/elders/{elder_id}/voice-sessions
GET  /api/v1/tenants/{tenant_id}/service-entitlement
POST /api/v1/elders/{elder_id}/account-links
```

原則：

- Organization 建 Elder endpoint 不接受或建立 Email／Password／OAuth identity。
- `elder_id` 是 resource target；`tenant_id`、role 與 actor context 由 Server 解析。
- Session response／audit 可回傳 initiator mode，但不可洩漏不必要的 Actor PII。
- Entitlement failure 與 Authorization failure 使用不同 reason code，且避免洩漏 Elder 是否存在。
- 離場與 link 為高風險 command，需要 idempotency、optimistic concurrency 與 immutable audit。

## 九、Frontend Flow 影響

必須新增或調整：

- Organization Admin：建立 Elder Profile，不出現帳號／Email 必填欄位。
- Staff Dashboard：先選 Organization／Care Unit，再看到 server-authorized Elders。
- Elder Mode：清楚顯示目前服務對象，可安全退出並回到 Staff mode。
- Household：邀請家屬／照護者、建立或承接 Elder Enrollment、顯示方案狀態。
- Offboarding：結束服務的影響預覽、資料處理選項、確認與結果。
- Optional self login：連結既有 Elder，不建立第二份 Elder Profile。

不得保留以下假設：

- 「進入 Elder 頁面的人一定是 `ELDER` Actor」
- 「註冊完成後自動建立 Elder」
- 「一個帳號只有一個永久角色／Tenant」
- 「知道 elderId 就能切換照護對象」
- 「機構方案結束後長者自動沿用相同付費權益」

## 十、Current → Target Gap

| Area | Current repo | Target | 演進方式 |
| --- | --- | --- | --- |
| Account principal | `actor` 混合全域 persona type | Actor／User 只代表 Principal | 保留表；逐步移除 `ELDER` 作為必要條件 |
| Elder | 獨立 `elder`，`actor_id` nullable | 無帳號為正常狀態 | 保留 nullable link；修正 onboarding／policy |
| Tenant | Organization boundary，已出現 HOUSEHOLD 支援 | Organization／Household service context | 重用 `tenant`，補產品語意與 migration |
| Elder service relation | `elder.tenant_id`＋relationship／assignment | 多期間 Enrollment | Additive `elder_enrollment`＋backfill |
| Paid service | 無獨立正式模型 | Tenant-scoped Entitlement | 新增 `service_entitlement` |
| Family link | `care_relationship`／family invitation | Family relationship＋share scope | 重用，不先加 `family_link` |
| Staff access | relationship／assignment＋tenant | 再加 Enrollment、Entitlement | 擴充 Policy，不用通用 grant 起步 |
| Self account | `elder.actor_id` nullable unique | Optional verified link | 先重用；需要歷史時再拆表 |
| Session initiator | 部分流程假設 Elder self | self／staff／family／device 分離 | 擴充 contract、audit 與 UI |
| Offboarding | Tenant offboarding 為主 | Single Elder enrollment ending＋continuation | 新增 workflow 與 negative tests |

## 十一、Database Migration Proposal

本節只規格化順序，不建立 migration。

### Phase 0：資料盤點與決策 Gate

- 列出所有 `ELDER` Actor、nullable／non-null `elder.actor_id`、每位 Elder 的 Tenant、Relationship、Assignment 與資料量。
- 定義 Enrollment type／status、Entitlement plan／status、重疊期間規則與 reason codes。
- 確認資料可攜與保存政策 owner。

### Phase 1：Expand

- 新增 `elder_enrollment` 與 `service_entitlement`，先允許受控 backfill。
- 建立 FK、有效期間、查詢索引、排他／唯一限制與 audit columns。
- 不 drop、rename 或重寫 baseline migration。

### Phase 2：Backfill

- 每個既有 Elder 依現有 `tenant_id` 建立初始 Enrollment。
- 依 Tenant 環境建立明確的 development／trial Entitlement；production 不可假造付費狀態。
- 無法判定或具衝突的資料輸出 review report，不靜默選擇。

### Phase 3：New-write／Compatibility

- 新 Elder write 不建立 Actor。
- 新 Session 寫 initiator、Enrollment／Entitlement reference。
- 讀取新模型優先，legacy fallback 有 metric／log／feature flag。

### Phase 4：Authorization Cutover

- 所有 Elder-scoped API 驗證 Enrollment 與 service context。
- 付費功能另外驗 Entitlement；授權與方案錯誤不可混為同一檢查。
- 驗證離場後下一個 request／Session 立即被拒絕。

### Phase 5：Contract

- fallback 使用率歸零、資料一致性與 rollback window 通過後，才評估解除 `elder.tenant_id` 單一 Tenant 依賴。
- legacy `actor_type=ELDER`、provider-created blank Elder skeleton 與自動 onboarding 分別退場；不與 Expand migration 綁成一次破壞性發布。

## 十二、Acceptance Criteria

### 必須通過

1. 建立 30 位 Elder 時不建立 30 個 Actor／Identity／Email challenge。
2. 無 `actor_id` 的 Elder 能在授權 Staff／Family 操作下完成一個 Session。
3. User U002 可查看 Elder E001，但對同 Tenant 的 Elder E002 仍被拒絕。
4. User 在兩個 Tenant 的 Role／scope 可不同，且必須選定有效 context。
5. 結束 E001 在 O001 的 Enrollment 後，O001 Staff 下一個 request 即無法讀取或啟動 Session。
6. 結束 Enrollment 不刪除 Elder、User、Conversation、Memory、Summary、Event 或 Consent。
7. O001 Entitlement 結束後，不可建立新的付費 Session，但仍依退場政策保留核准的查看／匯出／刪除能力。
8. 建立 Household Entitlement 與 Enrollment 後，可對同一 `elder_id` 續用；未核准機構內部資料不會出現在 Household。
9. Elder 日後 link User 後，所有既有照護資料 ID 與 ownership 不變。
10. 偽造 `elder_id`、`tenant_id`、role、initiator 或 Entitlement reference 均無法越權。

### 必要 Negative Tests

- no membership
- inactive／expired enrollment
- inactive／expired entitlement
- revoked assignment／family relationship
- valid membership but wrong elder
- valid elder but wrong source tenant resource
- session created before revocation but used after revocation
- duplicate／overlapping enrollment conflict
- self-link to an Elder already linked to another Actor
- household continuation attempting to import restricted tenant notes

## 十三、分階段範圍

### 必須現在修

- 文件與 ADR 的 Account／Elder boundary。
- 新帳號流程不再把建立 Elder 當成必然結果。
- Authorization 與 Session 設計明確區分 Actor、Elder 與 Tenant context。
- Enrollment／Entitlement schema、backfill 與 API proposal 審查。

### 可以下一階段修

- Organization／Household 管理 UI。
- Staff-assisted／device Elder Session 完整流程。
- Single Elder offboarding 與 Household continuation。
- Optional Elder self-account linking UI。

### 暫時不要做

- 全面把 `actor` 改名成 `users`。
- 全面把 `tenant` 改名成 `organizations`。
- 未驗證就建立通用 `elder_access_grant`、`family_link`、`elder_user_link` 三套重疊授權表。
- 把 billing provider 細節直接寫進 Domain table。
- 重建資料庫、合併舊 migration 或刪除歷史 ADR。

## 十四、Traceability

- ADR：`docs/adr/0013-separate-account-elder-enrollment-entitlement.md`
- Domain：`docs/spec/06智慧長照 AI 陪伴系統－Domain Model、商業規則與資料生命週期 v0.1.md`
- UX：`docs/spec/04智慧長照 AI 陪伴系統－資訊架構、UX 與 User Flow v0.1.md`
- Workflow：`docs/spec/05智慧長照 AI 陪伴系統－核心工作流、狀態機與錯誤恢復 v0.1.md`
- Security：`docs/spec/07智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1.md`
- Contract：`docs/spec/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`
- Migration：`docs/spec/13智慧長照 AI 陪伴系統－Database Migration、Release 與 Rollback v0.1.md`
- Offboarding：`docs/spec/16智慧長照 AI 陪伴系統－相容性、Deprecation、資料匯出與退場策略 v0.1.md`
