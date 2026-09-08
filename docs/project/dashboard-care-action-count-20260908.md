# US-C01 Dashboard care-action count — 2026-09-08

Status: implemented and verified locally on `feat/dashboard-care-action-count`, based
on main `84ef958`. Not committed, pushed, or CI-verified yet. This is one US-C01
increment, not the complete overview story or production acceptance.

## Scope and security

- Existing authorized-elders response adds optional nullable `open_care_action_count`.
  Count formal actions in OPEN, IN_PROGRESS and POSTPONED; exclude completed,
  cancelled and all candidates. No schema migration or new endpoint/job.
- Only the returned page's elders are considered. Each professional elder is
  reauthorized through canonical live `care_action:read`; unavailable and family
  results are null, not a misleading zero. Genuine authorized empty results are 0.
- One tenant/elder-bounded grouped count query includes all matching formal actions,
  not a first-100-actions sample. Counts follow read visibility across assignees;
  self-assignment remains the write boundary. No action contents or provenance join.
- Authorization uses sequential per-elder policy checks on one AsyncSession (page
  maximum 100), then one grouped query. This is not constant-query batch authorization;
  measure large-page latency before optimizing the canonical policy path.
- Staff cards show localized counts; family, missing/invalid fields and null hide
  the indicator. Old server responses remain compatible. No additional browser API
  request and no global count inferred from a partially loaded elder page.

## Verification

- Core full unit suite: 1183 passed before the final pagination wiring regression;
  final focused dashboard suite: 8 passed, including that added test. Ruff lint and
  format check passed (391 files).
- Frontend full suite: 410 passed in 52 files; focused dashboard/card tests: 14 passed.
  Typecheck, ESLint and production build passed.
- Static contracts and Core live contract verifier passed. Static examples include
  nullable/positive counts and rejection of negative counts. Live verifier checks
  readiness/unauthenticated boundaries, not authenticated dashboard count results.
- Added four DB cases: professional/family scope, no scope vs authorized zero,
  >100 actions (105 unfinished), terminal exclusion, cross-elder/tenant isolation,
  expired grant, and candidate → adoption → completion counts 0 → 1 → 0.
  Combined identity/workflow files: 58 tests collected only. Execute through existing
  disposable PostgreSQL CI; no development Supabase reset or fixture writes.
- Unit wiring regression requests two elder pages and verifies each count call sees
  only that page's ID while preserving cursor/has_more. SQL test checks tenant,
  elder and status predicates and absence of LIMIT/provenance joins.

## Visual QA

Following `playwright-visual-qa`, used the production build with synthetic API routes,
not real login or a live count backend. Personally inspected all ten full-page PNGs
under local ignored `.visual-qa/dashboard-count-20260908/`:

- `zh-{375,390,430,768,1024,1440}.png`, `en-{390,768}.png`.
- `en-empty-390.png`, `en-error-390.png` (injected 404 after previously loaded cards).

Requested narrow widths 375/390/430 rendered as 376/391/431 CSS viewport pixels;
desktop widths matched requests. DOM document width never exceeded client width.
Counts 105 and 0 were visible; null was absent. English labels and card grids fit.
Search-no-result and error states were readable; after error reload no elder names
or task counts remained. One expected mocked 404 console error, no observed runtime
exception. Limited keyboard check: Tab from search reaches the existing elder link.
Reduced-motion emulation was enabled for empty/error checks; no new animation added.
Loading-state timing, exhaustive keyboard navigation and real-device tests were not
covered in this increment. Screenshots are local evidence, not automated CI E2E.

## Handoff

Review and commit only this increment's source/contracts/docs, preserving the 14
preexisting contract-schema changes and unrelated `.qa` artifacts. Open a PR and
require existing core-db/aggregate checks before claiming remote acceptance.
Do not use PR #32's successful CI as evidence for this new Dashboard increment.
