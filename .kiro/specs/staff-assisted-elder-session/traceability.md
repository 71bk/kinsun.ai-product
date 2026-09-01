# Staff-assisted Elder Session Traceability

Updated: 2026-09-01

| Requirement | Domain authority | Planned executable evidence | Status |
| --- | --- | --- | --- |
| R1 Accountless Elder | `elder`, `elder_enrollment`, creator relationship | Model/schema tests and rollback-only Supabase onboarding smoke; no Actor/identity created | VERIFIED |
| R2 Care Profile boundary | `elder_care_profile_entry`; no Memory FK/write | Core model tests plus Agent contract/manifest/prompt tests | VERIFIED |
| R3 One-time handoff | `assisted_elder_session`, token codecs | digest, exchange/replay/expiry/reissue tests and Supabase smoke | VERIFIED |
| R4 Elder-mode constraint | dedicated assisted-session dependency | cross-tenant, expiry, reissue, live-scope and cookie-boundary tests | VERIFIED |
| R5 Safe companion | existing Consent/Conversation/Companion authority | existing consent gate plus third-party speaker/Memory policy suites; dedicated assisted route | VERIFIED |
| R6 Frontend boundary | Next.js BFF HttpOnly elder-session cookie | BFF cookie, credential-separation, CSRF and client-scope stripping tests | VERIFIED |
| R7 Release boundary | settings flags, contracts, CI | production rejection, static/live contracts, build, Supabase schema verification | VERIFIED |

## Source linkage

- ADR 0013: `docs/adr/0013-separate-account-elder-enrollment-entitlement.md`
- Spec 17: `docs/spec/17智慧長照 AI 陪伴系統－Account、Elder、Enrollment 與 Service Entitlement v0.1.md`
- Security/Privacy: `docs/spec/07智慧長照 AI 陪伴系統－Security、Privacy、NFR 與 Threat Model v0.1.md`
- API contracts: `docs/spec/10智慧長照 AI 陪伴系統－API、Event、Tool 與 Data Contracts v0.1.md`
- Database release: `docs/spec/13智慧長照 AI 陪伴系統－Database Migration、Release 與 Rollback v0.1.md`

## Explicit release blockers

- formal service entitlement and billing authority;
- legal representative/consent evidence model;
- durable managed-device enrollment and remote revocation;
- production voice transport, rate limiting, monitoring, retention, and deployment evidence.
