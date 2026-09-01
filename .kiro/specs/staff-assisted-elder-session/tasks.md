# Tasks: Staff-assisted Accountless Elder Session

- [x] 1. Confirm Account/Elder and tablet-handoff boundary
  - Reuse ADR 0013, Spec 17, current App Session, authorization, consent, and Companion seams.
  - Keep worker identity, Elder care subject, enrollment, and tablet credential distinct.
  - _Requirements: R1–R7_

- [x] 2. Add additive persistence and domain models
  - Add `elder_enrollment`, `elder_care_profile_entry`, and `assisted_elder_session` migration/models.
  - Add token codecs, repositories, current-state and cross-scope tests.
  - _Requirements: R1–R4, R7_

- [x] 3. Implement Core onboarding and assisted-session API
  - Atomically create accountless Elder, enrollment, relationship, and Care Profile.
  - Issue/exchange/current/end short-lived credentials with live authorization rechecks.
  - Add the consent-gated text companion turn.
  - _Requirements: R1–R5_

- [x] 4. Add bounded Care Profile context to Agent Runtime
  - Extend the request contract and manifest with source-labelled Care Profile items.
  - Add prompt/contract/negative tests proving no instruction following or medical authority.
  - _Requirements: R2, R5, R7_

- [x] 5. Implement the staff and tablet frontend flow
  - Add bilingual staff creation/handoff UI.
  - Add tablet exchange BFF, HttpOnly Elder Session cookie, elder-mode chat, and end cleanup.
  - _Requirements: R6_

- [x] 6. Synchronize contracts and verification evidence
  - Update Core/Agent OpenAPI, schemas, examples, and live/static verifiers only for implemented routes.
  - Run targeted Core/Agent/Frontend suites, formatting/lint/typecheck/build as applicable, plus
    `git diff --check` and status review.
  - _Requirements: R7_
  - Static contracts, live Agent verification, unit suites, frontend typecheck/build, lint,
    offline Alembic SQL compilation, Supabase additive migration verification, and a rollback-only
    synthetic onboarding/pairing/session smoke pass. Destructive empty-database migration
    round-trip remains intentionally unrun because no disposable `TEST_DATABASE_URL` is configured.

## Completion rule

Completion means a synthetic, local accountless Elder can be created and a single-use tablet handoff
can run a consent-gated text turn without sharing staff credentials. It does not mean production
entitlement, production voice, legal authority, durable device management, or deployment is approved.
