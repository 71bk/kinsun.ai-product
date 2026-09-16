# B02 summary acceptance and bounded fixes — 2026-09-16

## Scope and result

Base: `origin/main` at `6bf89a8`; independent backend worktree, branch
`fix/b02-summary-boundaries`. The review follow-up also adds frontend overflow
error handling. No migration, shared development DB writes or service restart.
B03/B04 QA commits remain on
`qa/b03-b04-real-auth-20260916` and are not included in this branch.

**B02 is not fully accepted.** This increment fixes silent event truncation and
summary update serialization, and adds regression cases. Source-snippet navigation,
frontend rebuild handling and real-auth browser acceptance remain outstanding.

## Implemented fixes

- The existing contract supports 32 summary items. Generation now fetches at most
  33 reviewed current event versions to detect overflow. More than 32 returns
  HTTP 422, `details[].reason = SUMMARY_EVENT_LIMIT_EXCEEDED`, before creating or
  replacing a summary/version/outbox event. No partial draft is returned. This is
  the conservative implementation default proposed during this task, not an Owner
  decision to permanently cap daily event volume. Future complete aggregation
  needs a separate product/contract change.
- `DailySummary` eagerly loads server-generated fields after ORM updates. This
  keeps `updated_at` available when the async API serializes review, regeneration
  and rebuild responses. The regression uses an actual in-memory SQLite ORM
  flush; setting the mapper back to its previous `auto` mode reproduces the
  expired `updated_at` failure. PostgreSQL HTTP coverage is separate below.
- API/OpenAPI descriptions explain the existing Taipei day and new overflow
  behavior. No request/response shape or database schema change.

## Acceptance findings

| Area | Current evidence / boundary |
| --- | --- |
| Source-backed content | Generation uses same tenant/elder, VERIFIED/CORRECTED and `current_version`; source event IDs are retained. Renderer reads explicit source text and otherwise uses a neutral presence statement. |
| Day boundary | Existing inclusive Taipei 00:00:00 through 23:59:59.999999 remains unchanged. Null `event_time` falls back to `created_at`. SQL-boundary unit cases cover year rollover, leap day and maximum date; PostgreSQL selection cases are added but not executed locally. No claim of arbitrary timezone support. |
| Event count | Unit cases for 31/32/33 rows pass. Database case adds a 33rd event after a successful 32-item summary and checks rejection/retry preserve prior versions and outbox. Database execution pending. |
| Corrected content | Database case first generates an empty draft while a candidate is unreviewed, CORRECTs its type/time/content, then explicitly generates version 2 using the corrected source. It checks immutable old content, same-key replay and expired-assignment denial. This does not claim formal events can be corrected again. |
| Rebuild | `/rebuild` marks STALE and writes a request event. `/generate` is the explicit regeneration command. New database case checks both stages, replay and stale-version 409. No automatic worker completion claimed. |
| Source lookup | Existing event detail API returns current structured content and bounded opaque evidence refs with live authorization. Database case tests source lookup and wrong-elder denial. It does not resolve a source evidence snippet. |
| UI | Elder summary page displays shortened event IDs as text, not source navigation. No summary rebuild client/interaction was found. These remain B02 gaps. |

## Verification

The following results are the initial `91929e1` baseline; follow-up results are
recorded in the review section below.

- Focused summary unit/API tests: **14 passed** (includes a real SQLite ORM update).
- PostgreSQL acceptance: **9 cases added, collection only**. Requires disposable
  `TEST_DATABASE_URL`; not executed against shared Supabase.
- Static contracts and CI rule tests: passed; CI rules **26 tests**.
- Full Core unit suite: **1,444 passed** in 91.50 seconds.
- Ruff lint/format for the five changed Python files and `git diff --check`: passed.
- No PostgreSQL integration run, browser QA, live login, deployment or production
  verification in this increment. Existing QA credentials remain retired.

## Remaining work

1. Execute the new PostgreSQL cases in CI and review failures before merging.
2. Define a bounded source-snippet lookup contract and review its authorization,
   provenance and version behavior. Opaque refs must not become public transcript
   or audio URLs; current event text is not proof of original evidence text.
3. Connect summary source navigation and explicit rebuild/regenerate in the
   frontend, then run real-auth and viewport acceptance. Overflow messages are
   implemented in the review follow-up below.
4. Resolve full-day aggregation beyond 32 events if the product needs it. Merely
   increasing the SQL limit cannot bypass the existing bounded item contract.

References:

- [Summary service](../../services/core-api/app/services/summary_service.py)
- [Unit cases](../../services/core-api/tests/unit/test_summary_generation.py)
- [PostgreSQL cases](../../services/core-api/tests/integration/test_summary_acceptance.py)
- [Wave 2 gap audit](wave2-backend-gap-audit-20260915.md)

## Review follow-up: consent and overflow feedback

- Generation checks active CARE_EVENT_EXTRACTION consent before querying source
  events, including the overflow path. `create_draft` retains its write-boundary
  recheck. Tests assert inactive consent rejects before any source query for
  0/32/33 rows; PostgreSQL cases add revoked consent with both 32 and 33 events.
- The frontend API error keeps contract-validated `details`; malformed errors
  never expose those details and BFF errors default to an empty list. Summary
  generation recognizes only HTTP 422 plus the exact summary-date overflow reason.
  English and Traditional Chinese messages explain the limit, no new summary,
  and that retrying does not resolve it. Other failures retain their existing
  handling. The page tests cover precise matching, preserved existing summaries,
  no false success and no automatic retry.
- This does not implement source-snippet navigation, automatic rebuilding or
  retroactive consent checks on already-completed idempotency replay paths.

Follow-up verification:

- Core unit suite: **1,447 passed**; focused summary tests: **17 passed**.
- Frontend full suite: **609 passed, 1 timeout** in the existing late-denial
  unmounted-panel case while Core tests and typecheck also ran. A subsequent run
  of the entire page test file plus API client tests passed **113/113**, including
  that case, without changing its timeout or implementation. The initial full run
  was not clean and is not reported as a full-suite pass.
- Frontend typecheck, production build, ESLint, changed Python Ruff lint/format,
  `git diff --check` and CI rules (26 tests): passed.
- PostgreSQL acceptance: **11 cases collected**, not executed locally. No shared
  development database, real credentials, browser or live provider used.

## First PR CI and fixture correction

Run [35062360218](https://github.com/71bk/kinsun.ai-product/actions/runs/35062360218)
on `1b1d833` passed frontend quality and all other workers except `core-db` (and
its aggregate gate). PostgreSQL integration: **248 passed, 1 failed**. Ten of
the eleven new B02 cases passed. The boundary/source test reached source lookup,
then failed because the fixture used `synthetic:evidence`, which the production
API correctly filters out: the contract requires `evidence:<UUID>`.

The fixture and expected response now share a canonical synthetic evidence UUID.
The API filter is unchanged. The corrected commit still requires a fresh CI run;
this initial failure is not reported as complete B02 database acceptance.
