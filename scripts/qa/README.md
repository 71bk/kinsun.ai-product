# Wave 2 real-auth browser acceptance fixture

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
