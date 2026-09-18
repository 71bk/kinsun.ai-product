# Demo 管理員與照服員邀請：後端串接

本次交付 Core API、migration、管理員 provisioning、API 契約，及管理頁、啟用頁與 same-origin BFF。
管理員由登入導向或首頁進入 `/admin`；受邀者由 `/join` 設定密碼後使用既有登入流程。目前沒有寄送 Email。
設計決策見 [ADR 0024](../adr/0024-demo-workforce-invitations.md)。

## 環境與初始管理員

只供 development：`KINSUN_NATIVE_AUTH_ENABLED=true`、`STAFF_INVITATIONS_ENABLED=true`。
Core 重啟才會載入旗標；production 不接受此功能。
先確認 DB revision，再執行 additive `alembic upgrade head`，不可 reset seed 或 downgrade。
使用獨立 runtime principal 時，一併更新 `app.database_runtime_principal` 的 grants。

Core Python 環境執行 `python ../../scripts/provision_demo_admin.py`：

- 新增 `admin.demo@kinsun.local`，角色 `ADMIN`，機構 `10000000-0000-4000-8000-000000000001`。
- 密碼取既有 `DEMO_ACCOUNT_PASSWORD`，不輸出明碼。
- 重跑不重設密碼或角色；既有帳號不相容時停止。
- 僅 development 指定本機 DB 或設定 `KINSUN_ALLOW_REMOTE_DEMO_ACCOUNT_PROVISIONING=true` 的 Supabase 開發 DB 可執行。
- 使用既有 Kinsun password login；`GET /api/v1/me` 回傳 `actor_type=ADMIN`、`role=ADMIN`。
  前端依 ADMIN 角色導向 `/admin`，管理員不需具備照服員單位才能進入管理頁。

## 管理員 API

需要 `Authorization: Bearer <ks1_ App Session>`。Core 查驗 active ADMIN、唯一 active tenant membership。
資料限當前機構；不可由請求提供 tenant_id。非 ADMIN／跨機構回 404。
回應均為 `{data, meta}`，錯誤為 ErrorEnvelopeV1。

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/admin/care-units` | 可用單位，`?limit=20&cursor=...` |
| GET | `/api/v1/admin/staff-invitations` | 邀請列表，同樣分頁 |
| POST | `/api/v1/admin/staff-invitations` | 建立，需要 `Idempotency-Key` |
| POST | `/api/v1/admin/staff-invitations/{invitation_id}/revoke` | 撤銷，需要 `Idempotency-Key`、`{"expected_version":1}` |

建立 body：

```json
{
  "email": "worker@example.test",
  "display_name": "Demo 日照照服員",
  "role_code": "DAYCARE_CARE_WORKER",
  "care_unit_id": "30000000-0000-4000-8000-000000000001"
}
```

care_unit_id 取自單位 API，不要使用上述示意 UUID。
日照可選 DAYCARE_CENTER／COMMUNITY_SITE；HOME_CARE_WORKER 只能選 HOME_CARE_AGENCY。
201 的 data 包含 invitation_id、display_name、role_code、care_unit_id、status、expires_at、version、invitation_token。
有效期 24 小時。Token 只顯示一次；相同 idempotency key 重送回 409，不重發 token。
列表／撤銷不含 token 或 email；狀態 ISSUED／ACCEPTED／REVOKED／EXPIRED。
丟失連結時撤銷後，使用新 idempotency key 建立。

## 啟用 API（僅 BFF）

`POST /api/v1/internal/auth/staff-invitations/accept`
由伺服器加 `X-Kinsun-BFF-Authorization: Bearer <KINSUN_AUTH_HANDOFF_SECRET>`。
不要將 secret 或 internal endpoint 暴露為瀏覽器通用代理。

```json
{
  "email": "worker@example.test",
  "password": "recipient-chosen-password",
  "invitation_token": "wi1_<43 characters>"
}
```

email 必須符合綁定地址；密碼 12–128 字元，UTF-8 至多 1024 bytes，不能含 NUL。
成功 200：`data={"status":"ACTIVATED"}`；再走 password login，此 API 不簽發 session。
過期、撤銷、已使用、email 不符、issuer 權限失效或既有帳號皆回統一 401；格式錯誤回 422。
啟用建立 Actor、identity、Argon2id credential、機構會員、單位會員，與消耗邀請同一 transaction。
不授予長者關係、Consent 或居服派案；日照人員可接著走既有建立長者流程。

連結建議 `/join#wi1_...`，讀取後移除 fragment；不要存 query string、
localStorage、analytics 或 log。BFF 必須驗同源 Origin、限制 body、設 no-store，保留 Core 錯誤封套。
啟用成功清除密碼與 token，引導照服員登入。

## 驗證

Unit tests 覆蓋權限、live membership、role/unit、隱私、single-use、到期、撤銷、既有 identity。
PostgreSQL integration tests 僅在 disposable CI DB 執行，不對 Supabase development 重建資料庫。
API schemas、OpenAPI、AsyncAPI 與有效／無效 examples 一併交付。

2026-09-18 本機開發環境驗證：migration 已升至 `c7e9f1a3b546`，獨立 admin 已建立。
Core 8000 已載入新 API 與啟用旗標；實際 HTTP admin 登入、單位／邀請清單及登出成功。
對開發 DB 以單一 rollback transaction 驗證邀請、啟用、重播拒絕、照服員登入、單位會員、
建立長者及撤銷重播，全部成功；測試帳號／長者未保留。此結果不代表 production 部署。

建立無帳號長者與平板交付另需在開發 Core 設定 `ASSISTED_ELDER_SESSIONS_ENABLED=true`，並重新載入服務。HTTP 回歸測試涵蓋配對碼發放、啟用、重播拒絕與目前 session 查詢。
