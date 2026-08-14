# ADR 0012: Kinsun-owned accounts with linked authenticators

- Status: Partially Superseded
- Date: 2026-08-14
- Owner: Project owner
- Supersedes: ADR 0010 only where it selected third-party OIDC as the primary account-creation entry point
- Partially superseded by: ADR 0013, only where this ADR treated the domain profile／`ELDER` role as part of every account and used `elder registration` as the canonical rollout
- Still valid: Kinsun-owned accounts, optional linked authenticators, verified Email OTP, Core-owned opaque App Session, no automatic email linking, and the development-only synthetic reset policy

## Context

The first authentication slice let Google or LINE create the first Core actor. That made an external identity provider look like the account authority even though the Core `actor`, membership, tenant, consent, and authorization records are already the real domain authority.

Kinsun needs accounts that remain valid independently of Google or LINE. Existing provider-created rows are synthetic QA data and do not require migration. They must not be deleted until the replacement path is working and verified.

## Decision

1. A Kinsun account is the Core-owned `actor` plus its active tenant memberships and domain profile.
2. `external_identity` records are authenticators, not accounts. The approved providers become `KINSUN`, `GOOGLE`, and `LINE`.
3. The MVP Kinsun authenticator is a verified email address using a short-lived, single-use verification code. Passwords are not introduced in this phase.
4. The existing Core-owned opaque App Session remains the only browser session credential.
5. A matching email address never auto-links identities. Google and LINE may only be attached to an already authenticated Kinsun account through an explicit, recent-authenticated linking flow.
6. Existing synthetic Google/LINE users are not migrated. After the Kinsun flow passes integration tests, a development-only guarded reset recreates synthetic Kinsun accounts.
7. The local fixed-code email adapter is allowed only when `APP_ENV=development`. It must never return or log the code. Production fails closed until a real email delivery adapter is configured.
8. Passkeys are the preferred Phase 2 authenticator. They do not block this MVP.

## Security boundaries

- Verification challenges expire, are single-use, store only opaque-token and code digests, and lock after a bounded number of failed attempts.
- Identity, challenge-code, and BFF-to-Core secrets are independent and server-only.
- An `ELDER`, `FAMILY_MEMBER`, or workforce role is determined from Core records, never from a form field alone.
- Workforce accounts cannot self-register.
- Family registration still requires a valid Core invitation.
- The development reset must check the environment and operate only on declared synthetic records.

## Consequences

- Users can register and sign in without a Google or LINE account.
- Google/LINE remain convenient optional sign-in methods after explicit linking.
- Email delivery is a release blocker for production but not for local QA.
- The old provider-first onboarding endpoints remain historical compatibility code until their account-creation branch is retired; they are not the canonical registration path.

## Rollout order

1. Add schema support and the Kinsun email challenge.
2. Add Core start/complete endpoints and App Session issuance.
3. Add frontend register/sign-in/verification screens.
4. Verify elder registration, existing-user login, family invitation, staff refusal, expiry, replay, and lockout.
5. Run the guarded development reset and recreate synthetic accounts.
6. Add explicit Google and LINE linking from the sign-in-methods page.

## Temporary exception

- Exception: deterministic local email verification code
- Owner: Project owner
- Expiry: 2026-09-30 or the first production authentication release review, whichever comes first
- Production behavior: fail closed

## Related documents

- `docs/adr/0010-provider-neutral-oidc-and-application-sessions.md`
- `docs/adr/0011-bounded-empty-account-consolidation.md`
