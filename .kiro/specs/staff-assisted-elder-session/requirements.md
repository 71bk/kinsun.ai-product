# Requirements: Staff-assisted Accountless Elder Session

## 1. Status and scope

This spec defines the first non-production vertical slice for an institution worker to create an
accountless Elder, record bounded Care Profile facts, and hand a short-lived Elder Session to a
tablet. It implements the seam defined by ADR 0013 and Spec 17 without treating `Actor == Elder` as
a domain invariant.

The slice is deliberately release-blocked in production. Tenant billing entitlement, durable device
enrollment, production voice transport, legal-representative authority, and offboarding remain
separate gates. No real elder data may be used for verification.

## 2. Glossary

- **Accountless Elder**: an `elder` row whose nullable `actor_id` is `NULL`; no email, password,
  OAuth identity, or browser App Session is created.
- **Care Profile Entry**: a staff-recorded health condition, medication, allergy, or care precaution
  with explicit source, status, version, and actor provenance. It is not AI Memory.
- **Pairing Credential**: a high-entropy, single-use secret transferred to the tablet. Only its
  digest is stored.
- **Elder Session Credential**: a high-entropy, revocable, short-lived credential accepted only by
  the assisted-session API. It is not a staff App Session.
- **Initiator**: the authenticated worker who created the Elder Session. The initiator is not
  automatically the speaker, consent actor, or Memory confirmer.
- **Tablet First-use Acknowledgement**: the plain-language, purpose-specific confirmation shown on
  the active Elder tablet before AI companion use. It records the assisted session and the worker
  who recorded the event, but does not fabricate an Elder Actor or claim legal-representative
  authority.

## 3. Requirements

### R1 — Create an accountless Elder

1. An active institutional worker in the selected tenant and care unit may create an Elder Profile.
2. The request shall accept display name, preferred name, preferred language, care setting, care
   unit, and bounded Care Profile entries; it shall not accept email, password, OAuth identity, or
   client-supplied actor/tenant IDs.
3. Core shall create the Elder, active Organization enrollment, creator relationship, and initial
   Care Profile entries atomically.
4. The resulting Elder shall have `actor_id = NULL` and appear only in server-authorized lists.
5. Cross-tenant care-unit IDs and unsupported roles shall fail closed without partial writes.

### R2 — Keep Care Profile separate from AI Memory

1. Health conditions, medications, allergies, and care precautions shall be stored as Care Profile
   entries with source actor, source type, verification status, current version, and timestamps.
2. Staff-entered facts shall begin as `RECORDED`, not as a diagnosis or clinically verified fact.
3. Care Profile data shall never create a `memory`, `memory_version`, embedding, or Memory Candidate.
4. Only active, non-disputed entries may enter bounded AI context, and only when the explicit
   non-production context feature gate is enabled.
5. Runtime prompts shall treat entries as data, never instructions, and shall prohibit diagnosis,
   treatment, medication changes, and health inference.

### R3 — Issue and exchange a one-time tablet handoff

1. An authorized worker may issue one pairing credential for one active enrollment and Elder.
2. Core shall persist only token digests and return the raw pairing credential exactly once.
3. Pairing shall expire within a bounded period, be single-use, and exchange into a distinct Elder
   Session credential.
4. Exchange shall not require or copy the worker's App Session to the tablet.
5. Reuse, expiry, ended enrollment, revoked worker access, wrong Elder, and disabled feature gate
   shall fail without revealing additional Elder data.

### R4 — Constrain Elder mode

1. The Elder Session credential shall be accepted only by assisted-session endpoints.
2. Every request shall re-check session status/expiry, active enrollment, live initiator identity,
   tenant membership, and the initiator's Elder authorization.
3. The session shall be locked to the server-stored tenant and Elder; request bodies cannot switch
   either scope.
4. Tablet requests shall retain the real `initiated_by_actor_id`; Core shall not fabricate an Elder
   Actor for an accountless Elder.
5. Ending, idle expiry, or absolute expiry shall immediately prevent future turns.

### R5 — Run a safe first companion turn

1. The first slice may provide text companion turns while production voice/device enrollment remains
   release-blocked.
2. Before the first turn, the tablet shall explain that AI processes the entered conversation,
   does not provide medical care, and does not currently receive Care Profile or create automatic
   long-term Memory; Core shall record explicit acknowledgement against a server-selected policy.
3. The acknowledgement shall create only a purpose-separated `BASIC_VOICE` grant through a
   dedicated assisted-session API. `granted_by_actor_id` shall remain `NULL`; Core shall separately
   record the live worker and assisted session as evidence without claiming the worker consented on
   the Elder's behalf.
4. Each turn shall require active `BASIC_VOICE` consent through the existing Core consent gate.
5. The tablet shall allow the Elder to stop AI companion use with a second confirmation. Revocation
   shall cancel active conversations immediately and block later turns until acknowledgement is
   completed again.
6. The turn shall create a normal Core-owned Conversation Session whose initiator is the worker and
   whose care subject is the accountless Elder.
7. Accountless assisted turns shall not auto-create or confirm long-term Memory because Elder
   speaker verification is unavailable.
8. AI context shall be bounded, source-labelled, tenant/elder scoped, and omitted safely when the
   Care Profile context feature gate is disabled.

### R6 — Frontend handoff boundary

1. Staff UI shall create the Elder and display a transferable one-time tablet link/token.
2. The tablet shall exchange the pairing credential through a BFF route and store only an HttpOnly
   Elder Session cookie.
3. Pairing activation on a tablet shall clear any staff App Session cookie on that tablet.
4. Elder mode shall expose only first-use acknowledgement, companion, stop-companion, and
   end-session actions; no staff navigation, account management, Memory management, or general
   consent-management controls shall appear.
5. Ending the session shall revoke Core state and clear the Elder Session cookie.

### R7 — Evidence and release boundary

1. Unit tests shall cover token format/digest, single-use exchange, expiry, revocation, cross-scope,
   no-Actor creation, and Care Profile exclusion rules.
2. Integration tests requiring PostgreSQL may run only against disposable `TEST_DATABASE_URL`.
3. Executable endpoints must be synchronized with OpenAPI/schema/examples before completion.
4. Production enablement requires a later reviewed entitlement, legal consent/authority, device
   enrollment, rate-limit, and operational security gate.

## 4. Acceptance journey

```text
worker App Session
  -> create accountless Elder + enrollment + Care Profile
  -> issue one-time pairing credential
tablet (no worker credential)
  -> exchange once -> HttpOnly Elder Session
  -> show locked Elder identity -> plain-language first-use acknowledgement
  -> text companion turn -> optional immediate stop/revoke
  -> end or expire -> credential rejected
```
