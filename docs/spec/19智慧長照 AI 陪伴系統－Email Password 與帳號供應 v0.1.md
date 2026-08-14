# 智慧長照 AI 陪伴系統－Email Password 與帳號供應 v0.1

## 文件狀態

- 版本：0.1
- 狀態：Accepted Implementation Baseline
- 日期：2026-08-14
- 決策來源：ADR 0015

## 目標

Kinsun 的可登入 Principal 使用自有 Email＋Password 帳號；Google／LINE 是可選的第三方
登入方式。`Actor/User Account` 與 `Elder Profile` 維持分離，機構建立的長者預設不需要
Email 或密碼。

## Domain invariants

```text
Actor / User Account
├── Kinsun Email Identity
├── Password Credential (Argon2id)
├── optional Google / LINE Identity
└── App Session

Elder Profile
├── accountless (default for organization care)
└── optional actor_id link (elder self access)
```

- Password credential 只能由 Actor 擁有，不可由 Elder、Tenant 或 Staff 代管。
- 建立 Elder Profile 不得同時要求 Email／Password。
- Staff 不得知道、設定或代輸入長者密碼。
- `elder.actor_id` 的 optional link 不改變 Conversation、Memory、Event、Summary、Consent
  的 `elder_id` ownership。
- Authentication success 不等於 Elder authorization success。

## MVP flows

### Existing account login

```text
Browser form → Next.js BFF → Core Email/Password verification
             → existing Core App Session → HttpOnly cookie
```

登入失敗、帳號不存在、Credential 不存在、Credential 鎖定一律回傳相同的認證失敗結果。

### Elder self-registration

```text
Email + display name
→ short-lived Email verification challenge
→ code + chosen password
→ Actor + Kinsun identity + household Elder Profile
→ Password Credential
→ Core App Session
```

OTP 只證明註冊 Email；如果 Email 已屬於既有 Kinsun identity，OTP 不得成為登入替代路徑。

### Family registration

與 Elder self-registration 相同，但必須另外具備有效的 Family invitation，才能建立 Family
Actor 與正式 Elder access relationship。

### Workforce account

STAFF／ORG_ADMIN 不開放公開註冊。帳號必須由 organization invitation、管理供應流程或受控
demo seed 建立。使用者本人設定密碼後，才可由 Email＋Password 登入。

### Organization Elder creation

Organization Admin 建立的是 accountless Elder Profile。未來需要 elder self-access 時，另外
啟動 account invitation，由長者或合法代表驗證 Email 並自行設定密碼，再 link 到既有 Elder。

## Password policy

- 長度：12～128 個字元，UTF-8 不超過 1024 bytes。
- 儲存：Argon2id PHC encoded string；每筆使用獨立隨機 salt。
- 參數以 `parameter_version` 管理，驗證舊版本成功後可於後續版本 rehash。
- 密碼不得出現在 log、outbox、audit payload、URL、Cookie 或 API response。
- Credential 狀態支援 `ACTIVE`、`LOCKED`、`REVOKED`。
- 連續失敗達上限後暫時鎖定；鎖定到期後可再次驗證。

## Persistence

新增 `password_credential`：

| Column | Purpose |
| --- | --- |
| `password_credential_id` | PK |
| `actor_id` | 唯一 FK，Credential owner |
| `password_hash` | Argon2id PHC string |
| `algorithm` | 固定 `ARGON2ID` |
| `parameter_version` | Hash policy version |
| `status` | ACTIVE／LOCKED／REVOKED |
| `failed_attempt_count` | bounded failure state |
| `locked_until` | temporary lock expiry |
| `password_changed_at` | credential freshness |
| `last_verified_at` | successful verification time |
| `version` | optimistic state version |

Email lookup remains a keyed digest in `external_identity(provider=KINSUN)`; no plaintext provider
subject is added. `actor.email` remains profile/contact data and is not identity authority.

## Internal API

```text
POST /api/v1/internal/auth/kinsun/email/start
POST /api/v1/internal/auth/kinsun/email/complete
POST /api/v1/internal/auth/kinsun/password/login
```

- `email/start` starts registration verification and never reveals account existence.
- `email/complete` requires verification code plus the chosen password and only creates a new
  account. Existing identities fail generically.
- `password/login` accepts Email＋Password and returns the existing one-time App Session envelope
  only to the authenticated BFF.

## Demo fixtures

`scripts/seed_demo.py` may provision deterministic Kinsun identities and credentials only when
`DEMO_ACCOUNT_PASSWORD` is explicitly provided. At least one seeded Elder remains accountless to
prove the domain separation. Seed output may print demo emails but never the password.

## Acceptance criteria

1. Elder and Family can complete verified registration and subsequently use Email＋Password.
2. A valid OTP for an existing Kinsun identity cannot issue a session.
3. STAFF registration is rejected; a seeded/provisioned STAFF credential can log in.
4. Wrong passwords return a generic failure and increment bounded lockout state.
5. Successful login clears failure state and issues the existing App Session format.
6. Password values and hashes never appear in API responses or logs.
7. Seeded accountless Elder has no linked Actor, external identity, password credential, or App Session.
8. Google/LINE identity behavior and explicit linking boundaries remain unchanged.

## Deferred

- Production email provider
- Password reset/change and session-wide revocation
- Organization member invitation UI
- Optional Elder self-account invitation/link UI
- Passkey and MFA
- Breached-password checking and adaptive abuse/risk controls
