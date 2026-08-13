# ADR 0010：Provider-neutral OIDC 身分與 Core-owned Application Session

- 狀態：Implemented；Google／LINE direct OIDC、Core App Session、explicit linking 與 Cognito repository retirement 已完成
- 日期：2026-08-11
- 完成日期：2026-08-13
- Owner：Project Owner
- 相關：[ADR 0006](0006-frontend-stack-and-app-topology.md)、
  [ADR 0007](0007-canonical-backend-and-aws-deployment-authority.md)、
  [LINE Login 官方文件](https://developers.line.biz/en/docs/line-login/overview)、
  [Google OpenID Connect 官方文件](https://developers.google.com/identity/openid-connect/openid-connect)

## 背景

黑客松期間 Frontend BFF 曾經由 Cognito Hosted UI 取得 access token，Core 再以 Cognito `sub` 解析正式
Actor、Tenant membership 與角色。這個做法當時能快速接入 AWS，但會讓登入、帳號連結、
Session 與部署設定一起綁定 Cognito。專案後續由單一維護者以低成本環境完成，不應為了保留登入
而被迫保留整套 Cognito runtime。

產品同時需要 Google 與 LINE 首次註冊，也需要同一個人以兩種方式登入同一份長照資料。Google
與 LINE 沒有可跨 Provider 自動比對的共同 immutable identifier；email 可能缺少、變更或由不同人
共用，因此不能作為自動合併依據。長者、家庭關係、Consent、報告與記憶又是高敏感 domain state，
錯誤合併的代價遠高於要求使用者再次驗證。

本 ADR 原先定義目標架構與分階段切換規則。2026-08-13 Owner 確認沒有需要遷移的 Cognito 帳號，
且黑客松 AWS 帳號已無法操作；repository 因此直接完成最後退場，不再維持雙 authenticator。

## 決策

### 1. Actor 是唯一正式帳號，ExternalIdentity 只是登入方式

```text
Actor
  ├─ ExternalIdentity(provider=GOOGLE, subject_digest=...)
  └─ ExternalIdentity(provider=LINE,   subject_digest=...)
```

- 正式 Actor、角色、Tenant membership、狀態與 Consent 只存在 Core database。
- 外部身分以 verified `(provider, subject)` 解析，不以 email、display name 或 browser 輸入解析。
- `external_identity` 保存 domain-separated keyed digest，不保存可直接用於登入比對的 raw subject。
  LINE 推播所需的可逆 destination 仍使用既有獨立加密欄位與權限邊界。
- 一個 active external subject 只能屬於一個 Actor；一個 Actor 每個 Provider 最多一個 active
  identity。Actor 可同時具有 Google 與 LINE identity。

### 2. Google 與 LINE 都可首次註冊，但角色規則不由 Provider 決定

- `ELDER` 可由 Google 或 LINE 完成首次註冊並建立 household。
- `FAMILY` 可由 Google 或 LINE 完成首次註冊，但仍必須兌換有效 Family Invitation；email-bound
  invitation 只有在 Provider 回傳相符的 verified email 時才能兌換。
- Staff、Admin 與 Content Manager 不得自助取得角色；必須先有 Core-side provisioning／membership。
- LINE email 是 optional；缺少 email 不得阻擋未綁 email 的長者或 Family Invitation onboarding。

### 3. 未知身分先進 pending flow，不立即建立第二個 Actor

Provider 驗證成功但查無 `external_identity` 時，BFF／Core 建立短效、單次 pending transaction，
讓使用者選擇：

1. 我是新使用者：依角色與 invitation policy 建立 Actor；或
2. 我已有帳號：重新驗證已綁 Provider，證明同時控制兩個身分後，把 pending identity 綁到
   既有 Actor。

相同 verified email 只能觸發 bounded duplicate warning，不能自動建立 link。若新 identity 已綁到
另一個 Actor，流程 fail closed。MVP 不自動合併兩個已有 domain data 的 Actor；必須人工審核，
後續若要提供 merge tool 需另立 ADR。

### 4. Core 擁有 opaque Application Session

- OAuth Authorization Code exchange 留在 Next.js BFF；使用 PKCE、`state`、`nonce` 與固定 callback。
- Provider ID token 只在登入／連結時使用，Core 必須獨立驗證 signature、issuer、audience、expiry、
  nonce 與 subject。BFF 不得以自行宣告的 subject 直接建立 Session。
- Core 核發至少 256-bit entropy 的 opaque Session token；database 只保存 SHA-256 digest，不保存 raw
  token。Provider access／refresh token 不作為 application session。
- Browser 只透過 `__Host-kinsun_session` 的 `HttpOnly; Secure; SameSite=Lax; Path=/` Cookie 持有
  credential。BFF 轉成 private Core request 的 Bearer credential，不轉發 browser Cookie。
- Core 每次由 Session 重新載入 active Actor、Tenant membership 與 Tenant status。Session 不保存可
  覆蓋正式授權的 role claim。
- Logout 必須 server-side revoke Session；只清除 Cookie 不算登出完成。

### 5. 分階段切換並保留明確 gate

1. 新增 provider-neutral identity constraint 與 `app_session` foundation。
2. 實作 Core verifier、pending identity、Session service 與完整 failure-path tests。
3. 先切 Google direct OIDC，再切 LINE direct OIDC／identity linking。
4. BFF、Core、onboarding、logout 與 account settings 全部通過後才將 runtime 切為 App Session。
5. Owner 確認沒有既有 Cognito 帳號後，移除 Cognito SDK、環境變數、IaC 與
   `actor.cognito_sub`；migration 若意外發現非空值會 fail closed。

Phase 1 不新增可啟用的 auth mode，不接受 App Session，不改當時的 callback，也不刪 Cognito。Phase 2A
只加入 Core 內部 Session lifecycle。Phase 2B 只加入 Core 內部 Google ID-token verifier，仍不新增公開
Session 建立 API、不註冊 App Session authenticator。Phase 2C 加入未綁 route 的 BFF authorization
transaction、callback envelope validation 與 code-exchange helper，但在 Core handoff 完成前不註冊公開
start／callback route。這讓 schema／service／verifier／BFF helper 先行與 runtime auth 切換保持可
區分，避免未完成的登入流程被誤開。Phase 2D/3/4 已完成；Phase 5 於 2026-08-13 完成。

## 理由

- 產品真正需要的是一份 Actor／Consent／家庭資料可由多種登入方式存取，不是建立自己的 Identity
  Provider 或密碼系統。
- Explicit linking 要求驗證兩個 Provider，可避免同 email、email 重用與未驗證 email 造成帳號接管。
- Opaque server-side Session 能立即 revoke，且不需要讓 Provider token 長期存在 browser 或每次傳到
  Core。
- 現有 Core 已把角色與 membership 放在 database，替換 verifier 不必重寫 domain authorization。
- 既有 `external_identity` 的 active subject／actor partial unique indexes已符合多 Provider cardinality，
  一般化約束比建立第二張互相競爭的 identity table 更安全。

## 後果

正面：

- Cognito 已從 repository runtime、前端、契約與 IaC 移除；Supabase 只作為目前的 PostgreSQL
  provider，不使用 Supabase Auth。
- Google、LINE 可登入同一 Actor，且未來可增加其他 OIDC Provider。
- Logout、停權、membership 失效與 identity revoke 可由 Core 即時生效。
- LINE Login 與 Messaging API 可共用同一 Provider user ID，但仍保有不同 Channel secret 與用途邊界。

代價與緩解：

- 專案自行承擔 Session lifecycle、rotation、revocation 與 anomaly logging；以短效 Session、hash-only
  persistence、bounded active sessions 與完整 failure-path tests 緩解。
- 沒有實名驗證時無法保證一個真人絕不故意建立兩個 Actor；接受此限制，MVP 保證的是一個外部
  identity 只屬於一個 Actor，並用 pending／link UX 降低誤建。
- 已形成兩個正式 Actor 的資料合併涉及 Consent 與稽核；MVP 接受人工處理，不做自動 merge。
- Direct OIDC provider 設定仍需由部署環境安全注入；範例設定預設關閉，避免未完整設定時半啟用。

## 替代方案

### 保留 Cognito

落選。Managed auth 能降低部分安全維護，但讓個人專案繼續依賴無法長期控制的 AWS 帳號與部署資源。

### 改用 Supabase Auth

落選。能較快完成 migration，但只是把登入權威換到另一個 vendor；本專案已具備 BFF、PKCE、Core
authorization 與 PostgreSQL，直接 OIDC 的額外工作可控。

### 依相同 verified email 自動合併

落選。LINE email 並非必有，且長照 domain 的誤合併後果包含跨家庭資料、Consent 與報告暴露。

### 自建 email／password／OTP／MFA

明確不做。密碼儲存、帳號恢復、MFA 與 abuse prevention 不服務本階段差異化，安全維護成本過高。

## 實作備註

- Phase 1 migration 只允許 `external_identity.provider IN ('GOOGLE','LINE')`，後續新增 Provider 必須再做
  migration 與 verifier review。
- `app_session.token_digest` 固定保存 lowercase SHA-256 hex；raw token 只在核發 response 與 BFF
  HttpOnly Cookie 中短暫存在，不進 log、trace、metric、URL 或資料庫。
- Identity linking、unlinking 與 Session revocation 都必須產生 bounded audit／outbox evidence；payload
  不得含 raw subject、token、email 或 Cookie。
- Phase 2A Session policy 已定案並以 bounded settings 驗證：
  - `ELDER`／`FAMILY_MEMBER`：idle 7 天、absolute 30 天；
  - Workforce／Admin／Content Manager：idle 8 小時、absolute 24 小時；
  - touch 最多每 5 分鐘一次、recent-auth window 10 分鐘、每 Actor 最多 5 個 live Session；
  - `SYSTEM_SERVICE` 不得取得 browser App Session。
- Session 核發會鎖定 active ExternalIdentity／Actor、確認唯一 active tenant membership，並保證新核發
  credential 不會因同時間戳排序而被 active-session cap 誤撤銷。驗證時重新解析 Actor、role、membership
  與 Tenant；identity／actor 停權、Session revoke、idle／absolute 到期都 fail closed。
- Phase 2B Google verifier 固定使用 Google 公開 JWKS，且只接受 `RS256`、Google issuer、單一且完全
  相符的 audience、有效 `exp`／`iat`、BFF 所產生且完全相符的 expected nonce、有效 `sub`，以及在
  有值時完全相符的 `azp`。JWKS 依 `Cache-Control` bounded cache，簽章失敗時只強制 refresh 一次。
- Google `sub` 是唯一登入識別；email 只有在 `email_verified` 為真時才保留，且永遠不得依 email
  自動解析或連結 Actor。拒絕紀錄不得包含 token、subject、nonce、email 或其他 Provider claim。
- `GOOGLE_OIDC_CLIENT_ID` 由 BFF 與 Core verifier 共用；`GOOGLE_OIDC_CLIENT_SECRET` 僅屬 BFF，Core
  settings 不讀取它。
- Phase 2C BFF foundation 固定使用 Google authorization／token endpoints，callback 由
  `FRONTEND_ORIGIN` 與 `/backend/auth/google/callback` 組成，不接受環境變數覆寫。交易使用獨立的
  `HttpOnly; SameSite=Lax` 短效 signed Cookie、獨立 32+ byte HMAC secret、state、nonce 與 S256 PKCE；
  callback envelope 要求單一 `code`／`state`／`iss`、固定 Google issuer，且過期 callback 不得清除
  較新的交易。
- BFF code exchange 只回傳 nonce-correlated ID token 給未來 Core handoff；Google access／refresh token
  不保留、不進 Cookie、不進 log。BFF 的 nonce check 只做 transaction correlation，ID token 在 Core
  verifier 完成 signature／claim 驗證前仍不可信。
- Phase 2D application flow 已完成並由三個明確 gate 控制：BFF 的 `GOOGLE_DIRECT_OIDC_ENABLED`、Core
  的 `GOOGLE_OIDC_HANDOFF_ENABLED` 與 `APP_SESSION_AUTH_ENABLED`。Google start 共用
  `/backend/auth/login`，direct callback 固定為 `/backend/auth/google/callback`；BFF-to-Core handoff、
  `pending_external_identity` 短效交易與 router 均已掛載在 gate 後。
- Existing active Google identity 會取得 Core-owned App Session；未知 ELDER／FAMILY identity 必須先到
  明確確認頁，並在單一 database transaction 內完成 pending token consumption、Actor／Tenant／Membership／
  ExternalIdentity 建立、ELDER onboarding 或 FAMILY invitation redemption，再核發第一個 App Session。
  未知 STAFF 不得自行註冊；verified email 只供衝突與 invitation recipient 檢查，永不自動 link 舊 Actor。
- BFF 使用獨立 `__Host-kinsun_session`（development 為 `kinsun_session`）HttpOnly Cookie；Core runtime
  只接受 `ks1_` Core App Session；驗證失敗後不會 fallback 到其他 bearer token。
  登出先呼叫 `POST /api/v1/auth/logout` 撤銷 server-side Session，成功後才清 Cookie。
- 三個 gate 的 committed example 預設仍為 false；實際環境要同時提供 Google console callback、
  provider secret、handoff secret 與 identity HMAC secret。沒有 Cognito Actor 需要 migration，且不得用
  相同 email 取代 explicit linking。
- LINE direct application flow 使用獨立的 `LINE_DIRECT_OIDC_ENABLED`、`LINE_OIDC_HANDOFF_ENABLED` 與
  共用的 `APP_SESSION_AUTH_ENABLED` gate。BFF 固定使用 LINE Login v2.1 Authorization／Token endpoint、
  PKCE、state、nonce 與 signed transaction；Core 透過 LINE 官方 verify endpoint 獨立驗證 ID Token。
  既有 LINE identity、ELDER pending onboarding、FAMILY invitation redemption 與 STAFF fail-closed 規則
  均共用 provider-neutral service；LINE email 維持 optional，且不作為自動連結依據。
- LINE direct flow 的 Channel ID／secret、callback 與獨立 secrets 必須由各 runtime 注入；committed
  example gates 維持 false。Direct sign-in 不等於 cross-provider account linking；同一 Actor 新增 LINE identity 仍須
  完成同時驗證兩個 Provider 的 Core-native explicit linking flow。
- Core-native Google→LINE explicit linking 現已實作：發起者必須持有 recent Core App Session，callback
  交易綁定該 Session 的不可逆 digest，Core 再獨立驗證新的 LINE ID Token。未綁 LINE subject 可直接
  加入目前 Actor；若 subject 已屬另一 Actor，絕不依 email 搬移或合併。
- 已存在的兩個 Actor 只在來源是單一 LINE identity、單一 ELDER membership、單一 HOUSEHOLD／Elder
  onboarding 骨架，且沒有 Consent、關係、事件、報告、記憶、對話、邀請或其他正式 domain rows 時，
  才可經第二次明確確認完成 consolidation。確認時重新檢查資料、撤銷兩邊所有 Session、撤銷來源
  identity、停用來源 Actor／Elder／Membership／Tenant，並在主要 Actor 建立新的 LINE identity 與
  Session；歷史 identity／Session 不改 actor_id。任何正式資料一律回 `MANUAL_REVIEW_REQUIRED`。

## 必要驗證

- Database constraint 阻止同 Provider subject 綁到兩個 active Actor。
- Database constraint 阻止同 Actor 綁兩個 active Google 或兩個 active LINE identity。
- Session digest 唯一、raw token 不持久化，revoked／idle expired／absolute expired 全部拒絕。
- Provider token 的錯誤 signature、issuer、audience、expiry、nonce、subject 全部拒絕。
- 相同 email 不自動 link；兩個 Provider 未完成雙方驗證不能 link。
- Identity 已屬另一 Actor 時零搬移、零 Session、零 domain side effect。
- Actor、membership 或 Tenant 失效後，既有 Session 下一次 request 立即拒絕。

## Rollback

Phase 1 可在不存在 Google identity 與 App Session rows 時 downgrade，恢復 LINE-only provider constraint。
若已有新 provider／session data，downgrade 必須 fail closed，先依核准的資料退場程序 revoke／清理；不得
靜默刪除登入或稽核資料。
Phase 2D migration 只可在 `pending_external_identity` 無資料時 downgrade；不得靜默刪除尚未完成的登入交易。
Cognito retirement revision 只會在 `actor.cognito_sub` 全為 null 時 upgrade；若意外存在資料會拒絕執行。
Downgrade 只恢復 nullable legacy 欄位與 constraint，不會恢復已刪除的 Cognito runtime。
