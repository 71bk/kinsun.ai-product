# Design: Staff-assisted Accountless Elder Session

## 1. Trust boundaries

```text
Staff browser --HttpOnly ks1 App Session--> Next.js BFF --> Core
       |                                                |
       | creates Elder/profile and pairing secret       | PostgreSQL authority
       v                                                v
Tablet browser --single-use ep1--> BFF exchange --> HttpOnly es1 Elder Session
Tablet browser --HttpOnly es1--> assisted-session BFF --> limited Core endpoints
                                                        |
                                                        +--> Agent Runtime proposal-only
```

`ks1_`, `ep1_`, and `es1_` are distinct credential types. A generic Core endpoint continues to
accept only the authenticated actor path; assisted credentials are parsed only by the dedicated
assisted-session dependency.

## 2. Persistence

### `elder_enrollment`

The additive first enrollment model records tenant/care-unit service context, active window,
creator, and ending metadata. It does not replace `elder.tenant_id` in this slice and does not claim
multi-tenant portability is complete.

### `elder_care_profile_entry`

One row per bounded entry:

- category: `HEALTH_CONDITION | MEDICATION | ALLERGY | CARE_PRECAUTION`
- content: normalized display text, maximum 500 characters
- source type: `STAFF_RECORDED` in this slice
- verification status: `RECORDED | VERIFIED | DISPUTED | RETIRED`
- source actor, tenant, Elder, version, effective/retired timestamps

There is no relationship to Memory tables. AI selection reads only `RECORDED`/`VERIFIED`, non-retired
rows for the current tenant/Elder and applies a fixed item limit.

### `assisted_elder_session`

Stores pairing/session digests, state (`PAIRING | ACTIVE | ENDED | EXPIRED`), tenant, Elder,
enrollment, initiator, authorization reference, pairing/idle/absolute expiry, activation, last seen,
end time, and optimistic version. Raw credentials are never persisted or logged.

### `consent_grant` assisted acknowledgement provenance

The additive acknowledgement revision separates the person represented by a consent record from the
actor who records an assisted-tablet event:

- `confirmation_method = ACTOR_CONFIRMATION` keeps the existing actor-confirmed flow;
- `confirmation_method = ASSISTED_TABLET_ACKNOWLEDGEMENT` requires
  `granted_by_actor_id = NULL`, a live `recorded_by_actor_id`, and the `assisted_session_id`;
- the acknowledgement creates only `BASIC_VOICE`; it cannot grant Memory, event extraction, family
  sharing, or Care Profile projection;
- revocation records the same assisted-session evidence and cancels active conversations.

## 3. Core operations

- `POST /api/v1/organizations/{organization_id}/elders`
  - authenticated worker only;
  - verifies organization equals trusted tenant and care-unit membership;
  - atomically creates Elder, enrollment, relationship, and Care Profile entries.
- `POST /api/v1/elders/{elder_id}/assisted-sessions`
  - authenticated and live-authorized worker;
  - verifies active enrollment and the non-production feature gate;
  - returns raw `ep1_` pairing token once.
- `POST /api/v1/assisted-elder-sessions/exchange`
  - accepts only `ep1_`; locks row; checks single-use and expiry;
  - re-checks initiator/enrollment/authorization; returns raw `es1_` once.
- `GET /api/v1/assisted-elder-sessions/current`
  - accepts only `es1_`; returns bounded Elder-session identity, expiry, and current first-use state.
- `POST /api/v1/assisted-elder-sessions/current/first-use-acknowledgement`
  - accepts only `es1_`, explicit `{ acknowledged: true }`, and idempotency evidence;
  - selects the active policy version server-side and creates only `BASIC_VOICE` when none is active.
- `POST /api/v1/assisted-elder-sessions/current/first-use-acknowledgement/revoke`
  - accepts only `es1_`; revokes active `BASIC_VOICE` and cancels live conversations.
- `POST /api/v1/assisted-elder-sessions/current/companion-turns`
  - accepts only `es1_`; rechecks all live authorization and `BASIC_VOICE` consent;
  - creates one text Conversation Session and runs the canonical Companion Service.
- `POST /api/v1/assisted-elder-sessions/current/end`
  - revokes the current session idempotently.

## 4. Authorization

The creation slice supports active `DAYCARE_CARE_WORKER` users with care-unit membership. `ADMIN`
creation is deferred because the current ElderAccessPolicy deliberately denies ADMIN and no reviewed
organization-admin scope model exists yet. Creation adds a `DAYCARE_ASSIGNMENT` relationship with the
minimal action set needed by the current staff workspace and assisted text session.

Assisted requests reconstruct the initiator's live ActorContext from Core state and then invoke the
existing Elder authorization policy. The token itself never carries trusted role, tenant, Elder,
scope, enrollment, or expiry claims.

## 5. Consent and speaker attribution

Creation and pairing do not auto-grant consent. The Elder tablet first shows a plain-language
purpose-specific acknowledgement. An explicit acknowledgement may create `BASIC_VOICE` through the
dedicated assisted endpoint, but the row does not name the worker as the consenting person and does
not claim verified Elder identity, legal capacity, or representative authority. The Conversation
Session records the worker as initiator (`CAREGIVER`); an accountless Elder has no Elder Actor, so the
existing speaker gate cannot classify the turn as verified Elder speech. Event/Memory proposal
eligibility therefore remains closed unless later speaker evidence explicitly permits it.

## 6. AI Care Profile projection

Core sends `trusted_care_profile` only for `BASIC_VOICE`, only when its rollout flag is enabled, and
only from current `RECORDED`/`VERIFIED` entries. Runtime adds source-labelled context items and a
prompt rule that health data is background for safe interaction only, not authority for diagnosis,
treatment, medication advice, symptom inference, or instructions.

## 7. Frontend

- `/staff/elders/new`: bilingual staff form and one-time handoff result.
- `/elder/pair`: tablet activation; token is read from URL fragment or pasted manually, then posted to
  a same-origin BFF exchange route.
- `/elder/session`: Chinese first-use explanation, text companion, second-confirmation stop action,
  and clear end action.
- `/backend/elder-session/*`: BFF-only cookie boundary for exchange, current session,
  acknowledgement/revocation, turns, and end. The BFF fixes the acknowledgement body and does not
  accept client-selected policy, actor, reason, deletion, tenant, or Elder scope.

The tablet exchange response clears the normal App Session cookie on that browser before setting the
separate Elder Session cookie.

## 8. Rollout gates

Both assisted session API and Care Profile AI context default off. Assisted session enablement is
rejected in production settings in this slice. Production requires ADR/Owner review for entitlement,
legal consent/representative evidence, persistent device enrollment, rate limiting/abuse controls,
voice transport, retention, monitoring, and deployment evidence.
