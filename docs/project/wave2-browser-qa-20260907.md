# Wave 2 real-auth browser QA — 2026-09-07

## Result

**F1/F2 fixed and revalidated locally; not a full Wave 2 release pass.** Real staff
login, Browser → Next.js BFF → Core → development Supabase workflow, replay,
stale-tab conflict and authorization expiry were exercised. The initial baseline
results below found two frontend issues; a subsequent production rebuild and
real-auth recheck closed both. Live Agent → VERIFY HTTP evidence remains open.

- Initial product commit: `b985ed674c5be1624355609580282fd8621bedd7` (merged PR #29).
  Fix verification used the local working tree on `test/wave2-caregiver-browser-e2e`
  before commit; no remote CI pass is claimed.
- Local production frontend build; Core on loopback; fake authentication disabled.
- Existing synthetic `staff.demo@kinsun.local` credential read locally from `.env`;
  real form submission established the session. No credential reset, cookie
  injection, fake API response, or intercepted response substitution.
- Playwright MCP controlled a dedicated Chrome via loopback CDP. The local login
  helper kept password/session values out of output. Request observation captured
  only synthetic care-action commands, their idempotency keys and responses.
- Alembic head: `d1f3a5c7e9b0`. No migration, DB rebuild, Docker, reset or deletion.
- Fixture campaign: `wave2-browser-20260907`, elder
  `13edb8e7-788c-5847-b0e0-05769f0713ce`. Setup used the real candidate promotion
  service with three synthetic formal source events. **Not live Agent or VERIFY
  HTTP evidence.** See [fixture runbook](../../scripts/qa/README.md).

## Observed acceptance results

| Case | Actual result |
| --- | --- |
| Real staff login and assigned elder detail | Login succeeded; three formal source events and three pending candidates displayed |
| Adopt, double-click confirmation | One POST, 200; one adopted candidate, one formal action, one created outbox event |
| Reject / exclude | Both 200; saved `NOT_NEEDED` / `OUT_OF_SCOPE`; action/outbox counts remained 1/1 |
| Adopted action lifecycle | OPEN v1 → IN_PROGRESS v2 → POSTPONED v3 → COMPLETED v4; updated due and resolution persisted |
| Manual create and cancel | Create 201, OPEN v1 → IN_PROGRESS v2 → CANCELLED v3; resolution persisted |
| Two real tabs with stale version | First tab updated manual action; stale tab cancellation returned 409 and displayed reload guidance |
| Terminal controls | Completed and cancelled cards exposed no further transition buttons |
| Nine successful commands replayed with original key/body | Original HTTP statuses and structurally identical `data` snapshots; older snapshots remained older versions, not current state |
| Unassigned elder page | No elder content; only no-access message |
| Cross-elder adopt / update vs nonexistent elder | Four requests returned 404 with identical error code/message/reason, excluding per-request correlation ID |
| Expired assignment/membership, fresh create from stale UI | 404 and no-access message; no new action; UI retained prior local content (F1) |
| Expired authorization, successful adopt/dismiss/update/create replay | All four returned 404; prior success snapshots did not bypass live authorization |
| Reload after expiry | No-access view replaced all elder content |
| Logout | Returned to `/sign-in`; authenticated BFF `/api/v1/me` returned 401 |

Replay comparison initially used JSON string equality, which differed because
JSONB reorders object keys. Recursive key-order normalization confirmed all nine
`data` objects equal, including nested provenance; no values differed. Response
`meta` is per-request and deliberately excluded from snapshot equality.

## Database evidence and retirement

Final retained synthetic records: one isolated unit, two elders, three source
events/versions, three candidates, two terminal actions, seven action outbox
events and nine completed resource-linked idempotency claims. Existing demo
membership, credentials and care data were not changed.

- Adopted action `80fa200b-5bbf-4288-8d3a-c2ad4384fdcf`: COMPLETED v4.
- Manual action `e9394ecb-2197-4084-a46c-6cec8ce773ba`: CANCELLED v3.
- Candidate decisions: ADOPTED / REJECTED / EXCLUDED, all v2.
- Only campaign relationship `26d11a64-f6a0-599d-9e7c-ca25f9747396` and membership
  `bb63607d-d513-5ef7-9acf-1e220bf4d37d` were expired, at
  `2026-09-07T08:57:09.944281Z`. No existing authorization was expired or extended.
- Final digest before replay, after replay, after cross-scope attempts, and after
  expiry/fresh-write/replay rejection remained:
  `77de106865f26b933c40963009f94e54ad613a84de3b931dfe95bb780811f150`.

Digest scope: all columns of this elder's actions/candidates/outbox plus completed
claims linked to those resource IDs. It excludes authorization rows, source
provenance, incomplete claims without resource IDs and unrelated tables; it is
not proof of zero writes across the whole database.

## Visual evidence

Following `playwright-visual-qa`, screenshots were personally inspected alongside
DOM assertions. Local screenshots are in `.qa/`; not automatically uploaded.

| Requested viewport | State / file |
| --- | --- |
| 1440×900 | Adoption confirmation: `wave2-adopt-desktop.png` |
| 375×812, 390×844, 430×932 | Postpone form: `wave2-postpone-{width}.png` |
| 375×812, 390×844, 430×932, 1440×900 | Empty candidate list + terminal cards: `wave2-complete-{width}.png` |
| 390×844 | Stale-tab conflict: `wave2-conflict-390.png` |
| 390×844 | Expired authorization before/after reload: `wave2-expired-390.png`, `wave2-expired-refresh-390.png` |
| 390×844 | Logout/login entry copy: `wave2-logout-copy-390.png` |

Chrome reported mobile `innerWidth` as 376/391/431 despite requested 375/390/430;
desktop was 1440. At every measured state, document scrollWidth equalled
clientWidth (no horizontal overflow). Postpone controls were visible and enabled;
terminal cards had zero transition buttons. No layout fix/rebuild was necessary.
The screenshots are desktop Chrome viewport emulation, not real-device evidence.

## Initial findings — resolved in the follow-up below

### F1 — Medium: authorization denial does not clear stale local content

After the fixture authorizations were expired, submitting the already-open create
form returned 404. The UI showed the correct no-access message, but left the old
cards, source-event choices, editable form and original expiry label visible.
Reloading removed them. This is stale authorized content, **not a successful
unauthorized read/write**; subsequent commands were consistently denied by Core.

Source: `packages/frontend/src/components/care/CareActionPanel.tsx`, create catch
around line 333 (and analogous mutation catches): only `setErrorKey(...)` runs;
`finally` clears busy state. It does not invalidate the enclosing elder access
context or clear cached action/source/form state. This is reproducible state
handling, not animation, stale build assets, or clipping.

Recommended follow-up: distinguish authorization loss from ordinary validation,
resource-not-found and 409 errors; revalidate the elder access context and fail
closed on confirmed scope loss, clear stale content and disable pending commands.
Add component tests and repeat real-auth expiry QA. Do not indiscriminately treat
every resource 404 as loss of the entire elder scope.

### F2 — Low: entry-page copy still presents Google as mandatory

Logout leads to `/sign-in`, whose introduction says identity is confirmed with
Google first. The actual accepted staff path is Kinsun email/password. Source:
`packages/frontend/src/app/sign-in/page.tsx:50`. Update the entry copy consistently
with the current authentication policy and locale rules in a separate fix.

## Fix and real-auth revalidation

F1 now invalidates the enclosing elder workspace on care-action 401/403/404,
unmounting cards, source choices, pending forms and dialogs before a live
elder/access-context recheck. An individual resource 404 is not by itself treated
as confirmed elder-wide denial. A successful recheck remounts with current
permissions; a failed recheck stays closed. Automatic rechecks are bounded and
mutations are never automatically retried. Ordinary 409/422/500 errors preserve
input. Late responses from an unmounted panel cannot restart access recovery.

F2 replaces the Google-first introduction with email/password entry copy and
translates all chooser text in `zh-Hant` and `en`, preserving all three routes
and existing session-cleanup behavior.

Verification after the production rebuild:

- Frontend: **315 tests passed across 50 files**, including 14 workspace access
  regression cases and 4 sign-in cases; TypeScript and repository ESLint passed.
  Production build passed. The final two added tests cover late success/denial
  responses; no product code changed after the build used for browser QA.
- New isolated campaign `wave2-browser-20260907-fix-recheck`, elder
  `b6e8c70e-7e1e-534d-8ef2-acca7d535de4`; the original campaign was not renewed.
  Local `.qa/wave2_recheck.py` reuses the guarded fixture with separate fixed IDs.
- Real login and adoption succeeded. Two real tabs retained an unsent manual
  create form and an adoption dialog. After expiring only the new campaign's
  membership and relationship, each submit made exactly one POST and received
  404, followed by one elder GET and one access-context GET (both 404).
- At the moment those recheck GETs started, both tabs already had **zero private
  elder text and zero inputs/selects/textareas/dialogs**. The final no-access
  screen appeared without reload, extra mutation, or refetch loop.
- New relationship `f54df9b5-0afd-5a3e-b070-d1b1e3a504ab` and membership
  `dda2d912-860c-586e-ae14-081f2f79d607` expired at
  `2026-09-07T09:44:18.335710Z`. Retained: one unit, two elders, three formal source
  events/versions, three candidates, one OPEN v1 action, one outbox event and one
  completed resource-linked claim. No existing demo authorization was changed.
- The same bounded digest scope described above was unchanged before expiry,
  after expiry and after both rejected commands:
  `4e3880bcaa02f57b69fb7ae2392190c2f0e060b8f66ef636bdac17dc0114915c`.
- Logout returned to the revised `/sign-in`; BFF `/api/v1/me` returned 401.

Following `playwright-visual-qa`, rebuilt screenshots were personally viewed and
paired with DOM checks. Files are local in `.visual-qa/wave2-fix-20260907/`:

| State | Requested CSS viewports | Screenshot files |
| --- | --- | --- |
| Adoption dialog before expiry | 1440×900 | `adoption-before-expiry-1440.png` |
| Create/adopt rejection without reload | 390×844 / 1440×900 | `create-denied-390.png`, `adoption-denied-1440.png` |
| Denied screen width regression | 375×812, 390×844, 430×932, 1440×900 | `denied-{width}.png` |
| Chinese sign-in chooser | 375×812, 390×844, 430×932, 1440×900 | `signin-zh-Hant-{width}.png` |
| English sign-in chooser | 390×844, 768×1024 | `signin-en-{width}.png` |
| English error, keyboard focus, reduced motion | 390×844 | `signin-en-error-keyboard-390.png` |

Mobile `innerWidth` again read 376/391/431; desktop/tablet read 1440/768. In every
measured state scrollWidth equalled clientWidth (scrollbars excluded from client
width). Text and cards were not clipped; chooser links retained their routes and
were at least 149 CSS px tall. Tab focused the elder link with a visible solid
outline; reduced-motion matched true and was restored afterward. These are
desktop Chrome emulations and a limited keyboard check, not full accessibility
certification. Neither finding was a transient, stale-bundle or layout defect.

## Not covered / release boundary

- Live Agent → source VERIFY HTTP → candidate → database chain.
- Production deployment, standalone-image startup, external provider callbacks,
  notification delivery, medical-proposal browser rejection, cross-tenant browser
  identity, real devices, full-workflow English/reduced-motion coverage and full
  keyboard accessibility (the sign-in chooser alone was rechecked above).
- Existing CI PostgreSQL tests cover additional negative/concurrency cases; this
  session does not turn those into browser coverage or rerun their DB rebuild.
- New fixture guard tests previously passed 32 cases; Core unit suite 1139 passed,
  fixture/test Ruff lint/format passed. Those offline results are separate from
  this manual browser evidence. No new CI result or PR is claimed by this report.
