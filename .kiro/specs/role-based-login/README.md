# 已退役：舊角色式登入設計

2026-10-08 移除已標記 LEGACY／SUPERSEDED 的 requirements 與 design。
舊 Cognito／DynamoDB、OAuth-only 與全域角色映射不可用來實作目前登入或授權。

請讀 [Backend authentication spec](../backend-authentication/requirements.md)及
[ADR 0010](../../../docs/adr/0010-provider-neutral-oidc-and-application-sessions.md)、
[ADR 0012](../../../docs/adr/0012-kinsun-owned-account-and-linked-authenticators.md)、
[ADR 0013](../../../docs/adr/0013-separate-account-elder-enrollment-entitlement.md)、
[ADR 0015](../../../docs/adr/0015-email-password-primary-authenticator.md)。
實作現況以 [AGENTS.md](../../../AGENTS.md)、程式與驗收證據為準。
舊文件可用 `git log --all -- .kiro/specs/role-based-login/` 查閱，不重新執行本 Spec。
