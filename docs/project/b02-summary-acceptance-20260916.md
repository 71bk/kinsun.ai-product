# B02 summary acceptance and bounded fixes — 2026-09-16

## Scope and result

Base: `origin/main` at `6bf89a8`; independent backend worktree, branch
`fix/b02-summary-boundaries`. No frontend edits, migration, shared development DB
writes or service restart. B03/B04 QA commits remain on
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
3. Connect summary source navigation, explicit rebuild/regenerate and actionable
   overflow messages in the frontend, then run real-auth and viewport acceptance.
4. Resolve full-day aggregation beyond 32 events if the product needs it. Merely
   increasing the SQL limit cannot bypass the existing bounded item contract.

References:

- [Summary service](../../services/core-api/app/services/summary_service.py)
- [Unit cases](../../services/core-api/tests/unit/test_summary_generation.py)
- [PostgreSQL cases](../../services/core-api/tests/integration/test_summary_acceptance.py)
- [Wave 2 gap audit](wave2-backend-gap-audit-20260915.md)
