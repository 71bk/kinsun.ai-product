# ADR 0015: Email and password as the primary Kinsun authenticator

- Status: Accepted
- Date: 2026-08-14
- Owner: Project owner
- Supersedes: ADR 0012 only where it selected passwordless Email OTP as the primary Kinsun sign-in method
- Supersedes: ADR 0010 only where it explicitly excluded a Core-owned password authenticator
- Still valid from ADR 0010/0012: Core-owned opaque App Sessions, provider-neutral identities, no automatic linking by email, and Google/LINE as optional linked authenticators
- Related: ADR 0013 account/Elder separation

## Context

Kinsun needs a first-party account system that is independent from Google and LINE. The
passwordless Email OTP slice proved the Core-owned identity and App Session boundaries, but a
synthetic OTP must not remain an alternate login path once Email and Password is the selected
product experience.

An Elder is still a care subject, not necessarily a login principal. In an organization, staff may
create and operate an accountless Elder Profile. If an elder later needs self-service access, the
elder receives an invitation and chooses their own password; staff never sets, reads, or shares it.

## Decision

1. Email and Password is the primary Kinsun-owned authenticator.
2. Password credentials belong to an `actor` (the login principal), never to an `elder`.
3. Passwords are stored only as versioned Argon2id PHC strings. Plaintext passwords are never
   persisted or logged.
4. The existing Email OTP challenge becomes registration email verification and, later, account
   recovery. It may not issue a session for an existing Kinsun identity.
5. Public self-registration is limited to the approved elder self-account and invited family flows.
   Workforce accounts are provisioned or invited by an organization administrator.
6. A successful password verification issues the existing Core App Session. No second session,
   JWT, or browser-visible Core credential system is introduced.
7. Error responses are intentionally generic. Failed attempts are bounded with temporary account
   lockout, and successful verification clears the failure state.
8. Google and LINE remain optional authenticators linked explicitly after authentication. Matching
   email addresses never merge accounts.
9. An organization-created Elder Profile remains accountless by default. Optional self-access links
   the new Actor to the existing `elder.actor_id`; it does not move care data.
10. Local demo accounts are deterministic domain fixtures but their shared QA password must come
    from `DEMO_ACCOUNT_PASSWORD`; it is never committed.

## Initial delivery boundary

This implementation provides registration email verification plus password creation, password
login, logout through the existing App Session revocation, and guarded demo credential
provisioning. Production email delivery, password reset/change, passkeys, MFA, organization
invitation UI, and elder self-account invitation UI remain later slices.

## Security invariants

- OTP cannot authenticate an existing password account.
- Staff cannot self-register.
- Staff cannot set or recover an elder's password.
- Password verification is performed only inside Core.
- The BFF may receive the one-time App Session response and stores it only in the existing
  HttpOnly cookie; browser JavaScript never receives it.
- A valid account/session does not grant elder access without current membership, relationship or
  assignment, consent, and tenant-scoped authorization.

## Consequences

- Existing synthetic OTP-only Kinsun identities require credential provisioning or a guarded demo
  reset before password login.
- Registration keeps one Email verification step, but all later Kinsun sign-ins use the password.
- Password recovery and organization invitations must reuse the same account/Elder boundary and
  cannot introduce shared elder credentials.

## Related documents

- `docs/adr/0010-provider-neutral-oidc-and-application-sessions.md`
- `docs/adr/0012-kinsun-owned-account-and-linked-authenticators.md`
- `docs/adr/0013-separate-account-elder-enrollment-entitlement.md`
- `docs/spec/19智慧長照 AI 陪伴系統－Email Password 與帳號供應 v0.1.md`
