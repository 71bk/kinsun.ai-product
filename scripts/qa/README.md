# Wave 2 real-auth browser acceptance fixture

## B03/B04 real-auth campaign (2026-09-16)

`event_review_fixture.py` is fixed to `b03-b04-real-auth-20260916`, which is already
retired. **Do not prepare again or renew it.** Default `inspect` uses a read-only
transaction; `prepare`, `expire`, and `retire` require `--allow-synthetic-write`.
Pass the existing development configuration with `--env-file /path/to/.env`.
Target checks require the development Supabase URL shape, current B03/B04 revision,
native login and App Session authentication, with fake authentication disabled.

The campaign creates an isolated tenant/unit, one worker, two elders, two-hour
memberships and a relationship, and synthetic consent/policy/conversation/legacy
events. Prepare refuses an existing campaign or private bootstrap. Expire only
shortens the exact relationship after ownership checks. Retire also disables its
actor, credentials and sessions, expires the remaining grants and removes the
private bootstrap account fields. Business evidence remains for audit.

`.qa/event-review-real-auth.cjs <frontend-checkout-path>` uses real form login and
the installed Playwright dependency from that checkout. It never injects cookies
for authentication or mocks responses. Its locale cookie is presentation only.
The historical flow pauses at `.qa/local/b03-ready-to-expire.json`; the operator
expires the relationship with the guarded fixture before writing the matching
`b03-expired.json` marker. Failed runs also require retirement; do not leave active
credentials. Neither script may be rerun against the retired campaign.

Offline safety tests: `tests/unit/test_event_review_fixture_safety.py` in Core.
Evidence and limitations: [acceptance report](../../docs/project/b03-b04-real-auth-20260916.md).

This is an **opt-in manual development tool**, not a CI database fixture and not
evidence that browser acceptance has passed. Run from the repository root using
the Core environment. No Docker or disposable database rebuild is involved.

```powershell
uv run --frozen --project services/core-api python scripts/qa/wave2_browser_fixture.py inspect
uv run --frozen --project services/core-api python scripts/qa/wave2_browser_fixture.py prepare --allow-synthetic-write
uv run --frozen --project services/core-api python scripts/qa/wave2_browser_fixture.py expire --allow-synthetic-write
```

## Safety and scope

- Default is read-only inspection. `prepare` and `expire` require explicit write
  opt-in. Settings are loaded from root `.env` without changing process-wide
  environment or provisioning credentials. Never print or commit that file.
- Only `APP_ENV=development` and an asyncpg Supabase `/postgres` URL are accepted.
  This validates the configured target's shape, not the operational environment's
  identity; the operator must independently confirm it is the development DB.
- The fixed campaign is `wave2-browser-20260907`. **It already exists in the
  development database; do not run `prepare` again.** Existing IDs cause failure,
  never overwrite. There is deliberately no reset/delete/recreate command.
- Uses the existing synthetic staff actor with current tenant membership. Creates
  one isolated synthetic unit, two elders (one unassigned), and a four-hour scoped
  membership/assignment. Does not repair legacy demo membership role codes.
- Creates three synthetic formal source events and promotes proposals through the
  real candidate service. This does **not** exercise live Agent generation or the
  human VERIFY HTTP route; never label these source events as live AI evidence.
- `expire` locks and verifies the two exact campaign authorization rows and their
  ownership before shortening validity. Re-running cannot extend expired access.
  It retains all synthetic entities, actions, candidates and provenance for audit.
- No notifications, migrations, credential changes, delete, truncate, schema reset,
  changes to pre-existing relationships, or integration rebuilds are performed.

## Browser procedure and evidence boundary

Use a production frontend build and real Core server with fake authentication
disabled. Log in through `/staff/sign-in` using the existing demo credential; do
not paste the password into an evidence file or tool output. Then open:

`/staff/elders/13edb8e7-788c-5847-b0e0-05769f0713ce`

Record actual outcomes separately for:

1. Candidate adopt / reject / exclude; repeat-click behavior.
2. Manual create, start, postpone with new due date/reason, complete and cancel.
3. Same-key replay and stale-version conflict through the authenticated BFF.
4. Unassigned elder and mismatched resource rejection without data leakage.
5. Expire the campaign authorization, then test stale UI and replay rejection.
6. Read back persisted state after each group; logout after acceptance.
7. Screenshot and inspect desktop 1440×900 and mobile 375×812 / 390×844 / 430×932,
   with DOM overflow and visible-control assertions.

`inspect` hashes all columns of this elder's actions, candidates and outbox rows,
plus completed idempotency claims linked to those resource IDs. The digest does
not cover unrelated tables, incomplete claims without resource IDs, source event
provenance, or authorization rows. An unchanged digest is only evidence for that
bounded set, not proof of zero writes across the entire database.

Offline safety tests run in the existing Core unit suite:

```powershell
uv run --frozen --project services/core-api pytest services/core-api/tests/unit/test_wave2_browser_fixture_safety.py -q
```

Real-browser and live Agent evidence must remain separate from the offline tests
and from PR #29's PostgreSQL-backed HTTP tests. Do not mark Wave 2 Task 3.1b
complete just because this helper or its safety tests passed.

## Live Agent chain inspection (2026-09-08)

`wave2_agent_chain_inspect.py` is read-only and fixed to the synthetic
`wave2-agent-chain-20260908` campaign. It neither prepares fixtures nor changes
authorization. Run from the repository root:

```powershell
uv run --project services/core-api python scripts/qa/wave2_agent_chain_inspect.py
```

It resolves the exact session claim, then follows event/version, review,
candidate, adopted action, provenance and outbox links in one read-only snapshot.
No credentials or conversation/proposal content are printed. See
`docs/project/wave2-agent-chain-qa-20260908.md` for completed local chain acceptance
and remaining CI/merge work; successful inspection alone is not acceptance.

`wave2_agent_chain_membership.py` defaults to read-only inspection of the exact
owner-approved campaign membership:

```powershell
uv run --project services/core-api python scripts/qa/wave2_agent_chain_membership.py inspect
```

The campaign membership already exists and is expired. **Do not prepare again or
renew it.** `prepare`/`expire` require `--allow-synthetic-write`; prepare refuses an
existing ID, creates at most four hours of access and never repairs legacy roles.
Expire locks and validates membership/actor/tenant/unit/role ownership and can
only shorten validity. Imports do not load settings or connect. Target validation
is the same development Supabase URL-shape check as the inspector, not independent
proof of environment identity. No assignment/Consent/credential or schema changes.

## Previous service record real-auth campaign (2026-09-14)

`previous_record_fixture.py` is fixed to `previous-record-real-auth-20260914`.
This campaign is already prepared and retired. **Do not renew or prepare it again.**
Default `inspect` is a read-only transaction; target validation requires the development
Supabase URL shape, not independent proof of environment identity.

```powershell
uv run --project services/core-api python scripts/qa/previous_record_fixture.py inspect
```

The reviewed prepare path creates two isolated workers with Argon2id passwords and
KINSUN identities, four memberships capped at four hours, two synthetic tenant/unit/elder
sets, six assignments, and one explicitly seeded historical note. It refuses existing
campaign IDs or the private bootstrap file. The file `.qa/.env.previous-record-real-auth`
is git-ignored; never print or commit its credentials. Retirement scrubs its accounts.

`prepare`, `add-login-memberships`, `expire-reader`, and `retire` require
`--allow-synthetic-write`. The additive login helper only fills missing campaign tenant
memberships, bounded by existing unit expiry; it never extends validity or replaces rows.
Session issuance requires tenant-level membership, and assignment access may also use
that row, so expiry must shorten both tenant and unit memberships. Retirement additionally
disables only the two campaign actors and revokes their identities, credentials and sessions.
It preserves synthetic records and outbox evidence; it does not reset any schema/data.

Inspection hashes every column in campaign service records/outbox, plus the original
source record separately. It reports no note content, credential hash, token or DSN.
Unchanged digests only cover this bounded set; auth/session changes are excluded.
Offline safety tests are `tests/unit/test_previous_record_fixture_safety.py` in Core.

Actual acceptance, failed QA assumptions, screenshot scope, final revocation and the
separate development auth rotation follow-up are recorded in
`docs/project/previous-service-record-real-auth-20260914.md`.
