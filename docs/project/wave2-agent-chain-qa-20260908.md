# Wave 2 live Agent chain acceptance — 2026-09-08

## Status and scope

**Task 3.1c local acceptance complete; new regression CI/merge pending.** Real
authenticated Browser fetch → BFF → Core → running Agent Runtime → Gemini → Core
→ Supabase produced a review-required event with a private Care Action proposal.
Following explicit owner approval, a new at-most-four-hour synthetic staff unit
membership enabled human VERIFY and adoption through the actual staff UI. The
result is one self-assigned formal OPEN action. That membership is now expired;
the original legacy membership, assignments and Consents remain unchanged.

Base: merged PR #31, `c3d9138`; work branch `test/wave2-agent-chain`.
Campaign: `wave2-agent-chain-20260908`.

This is a local development acceptance, not production deployment, ASR/TTS,
RAG acceptance, or autonomous formal state changes. Both demo accounts logged in
through the real password forms; commands were issued with authenticated in-page
fetch through the BFF (not a clicked companion form). No HTTP response was mocked.
The text input was synthetic missed-contact content, not a real elder statement.
Gemini supplies the companion reply; Event/Action proposal extraction is the
current deterministic Agent implementation, not an LLM formal-state decision.

## Defect found and fixed

The initial companion POST returned 500. `AgentCareActionCandidateProposal.as_payload()`
contains a native `datetime`. `CareEventService` validated the payload but persisted
the original dictionary into `care_event_version.care_action_candidate_proposal`.
SQLAlchemy's JSONB serializer raised `TypeError: Object of type datetime is not JSON serializable`.

The fix persists `action_proposal.model_dump(mode="json")` **after** the existing
schema and deterministic safety checks accept it. Denied/medical proposals remain
discarded; the fix neither promotes an event nor creates a formal action.
Regression tests use plain `json.dumps`, not a permissive `default=str`, and cover
native UTC datetime, ISO string and UTC+08 datetime. Before the fix the two datetime
cases failed; after it all three pass and preserve the typed proposal's meaning.

Read-only DB inspection after the failure found only the separately committed
CREATED conversation, its creation outbox row and its completed session claim.
There was no persisted Agent run, event, version, action candidate, formal action
or completed turn claim for this campaign. After restarting Core with the fix,
the same session and turn key succeeded. A subsequent identical completed-turn
request returned 409 / `VERSION_OR_IDEMPOTENCY_CONFLICT`, as the endpoint specifies.

## Stage 1 evidence — before human VERIFY

- Core `FAKE_AUTH_ENABLED=false`; real App Session and native password auth enabled.
- Agent `MODEL_PROVIDER=gemini`, configured model `gemini-3.6-flash`,
  `SERVICE_IDENTITY_ENABLED=true`; no fallback to mock or service-identity bypass.
- Runtime reported `staging_rag_unavailable` during startup. This BASIC_VOICE
  missed-contact case does not establish any RAG capability.
- Session POST 201; fixed companion POST 200 / `SUCCESS` / `ALLOW`.
- Session `df0adca1-264b-4060-9446-75e258b552b4`: COMPLETED, text,
  synthetic Elder initiator, Consent version 1.
- Agent run `524ebdc2-6b24-56ec-bb95-7bb8517f9e3e`: SUCCESS,
  `companion-agent`, version `1.0.0`, model `gemini-3.6-flash`, measured runtime
  adapter latency 1818 ms (one sample, not an SLA).
- Event `29130d25-e35b-48cc-8897-51f6b1bdffaa`: EXPECTED_CONTACT_MISSED,
  NEEDS_REVIEW, version 1; source_session_id matches the session above.
- Event version `b4ec0c56-2ad8-452f-a845-5fc971ad02c8`: private action proposal
  present; ELDER / VERIFIED_ELDER speaker evidence from authenticated text.
- Zero reviews, Care Action Candidates and formal Care Actions for this chain.
  The proposal is intentionally not a visible candidate until human VERIFY.
- Three scoped outbox rows: conversation created, conversation completed, event
  candidate created. Outbox delivery/consumer execution is not asserted.
- Two completed scoped idempotency claims: session and turn.

`scripts/qa/wave2_agent_chain_inspect.py` reproduces the bounded DB inspection in a
REPEATABLE READ, READ ONLY transaction. It resolves the session by the hashed,
tenant/actor-scoped session idempotency key; BFF assigns its own correlation ID,
so the caller-supplied correlation header is not used as campaign identity.
It exposes only selected metadata, never credentials, full input, reply, proposal
content or response snapshots. Its scope is this chain, not a database-wide audit.

## Stage 1 verification and browser observation

- Frontend production build passed on the PR #31 baseline; no frontend code changed.
- Core unit suite: **1160 passed** (including 19 new offline inspector safety tests
  and two additional parameterized JSON serialization cases).
- Relevant companion/persistence/promotion/inspector suite: **42 passed**.
- Ruff lint passed for all four modified/new Python files.
- Staff access-context GET: 404; actual page displays 「沒有查看權限」.
- Following `playwright-visual-qa`, personally inspected four denied-page PNGs in
  `.visual-qa/wave2-chain-20260908/staff-denied-{375,390,430,1440}.png`.
  Requested viewports: 375×812, 390×844, 430×932, 1440×900. Windows reported innerWidth
  376/391/431/1440 and document clientWidth 361/376/416/1425; scrollWidth equalled
  clientWidth throughout, zero main inputs and zero dialogs. No visual defect was
  found in these denied states. This does not cover authorized review/adoption UI,
  English, keyboard, reduced motion or real-device interaction this campaign.
- No destructive integration tests, DB rebuild, reset, migration or credential reset.
  The pre-existing 14 contract-schema worktree modifications are untouched.
- No commit, push, PR or new CI evidence yet.
- Final formatting check: four Python files passed; post-format focused suite
  27 passed. Both demo accounts logged out through BFF (200), with subsequent
  `/me` returning 401; dedicated QA Chrome closed.

## Stage 2 — authorized human VERIFY and adoption

The existing unit membership uses legacy `DAYCARE_WORKER`, not the required
`DAYCARE_CARE_WORKER`; initial access-context was 404. With explicit owner approval,
`wave2_agent_chain_membership.py` inserted only membership
`bbefbc47-d4aa-506a-b077-8cbca266bb46` for the existing synthetic staff/unit.
Its UTC start was `2026-09-08T02:53:07.135602Z`, initial end
`2026-09-08T06:53:07.135602Z`. No legacy row was repaired or renewed. An initial
prepare SQL enum/varchar bind error rolled back; casting actor_type to text fixed
the helper before the successful insert.

The staff logged in through the password form on the production frontend, opened
the exact event, selected VERIFY and confirmed. The first POST returned 500:
after flush, `_response` read expired `CareEvent.updated_at`, triggering implicit
async SQL and `MissingGreenlet`. The review transaction rolled back: the event
remained NEEDS_REVIEW with no review, candidate or action. Adding
`CareEvent.__mapper_args__ = {"eager_defaults": True}` fixes retrieval of the
server/on-update timestamp, matching the existing mutable Care aggregates.
The mapper regression failed before the fix and passed afterward. No migration
or API contract changed.

After restarting Core with both fixes, the actual UI sequence succeeded:

- VERIFY POST: 200, VERIFIED version 1, one review
  `d7e27f47-b9a5-4345-a722-a2864d94c295`, before/after version 1.
- One PENDING_REVIEW candidate `d58e866e-7ebc-46ad-9db0-fde9b1b49a9f`, version 1;
  still zero formal actions before adoption. Source is the event/version above,
  VERIFIED, extractor `care-action-candidate-v1`.
- 「檢視並採用」 → edit title/due/priority → 「採用並建立待辦」: 200,
  candidate ADOPTED version 2. No adoption request occurred before confirmation.
- Formal action `a7454641-f9a6-4538-8400-754e342a1805`: OPEN version 1,
  CONTACT_FAMILY, title `Synthetic Wave2 Agent Chain 20260908`, priority MEDIUM,
  due `2026-09-09T02:39:00Z`. Creator and assignee are the authenticated synthetic
  staff `20000000-0000-4000-8000-000000000010`.
- Candidate/formal provenance have identical event ID, event version ID, source
  status and snapshot hash
  `c63962cf3684960ca4717b0af4e1906f109b852d658bcc8d13de015e3b440936`.
- Five scoped outbox rows: the three Stage 1 events plus `care.event.verified.v1`
  and `care.action.created.v1`. Four completed claims: session, turn, review,
  adoption. This verifies persisted outbox records, not their delivery.

Successful VERIFY/adoption requests replayed with the same respective keys both
returned 200 with unchanged selected identity/status/version/adopted-action fields.
This was not a byte-for-byte comparison of the full responses. A pass-through
fetch observer recorded requests/results without mocking or replacing responses.

The new membership was explicitly shortened to `2026-09-08T03:03:20.427964Z`.
Replaying the same successful VERIFY/adoption requests after expiry both returned
404 / RESOURCE_NOT_FOUND. Reload showed 「沒有查看權限」 and no private action title.
Selected chain metadata before/after replay and expiry had identical SHA-256:
`32c6e2ea4115ec8bad10f115bbcc18d9214158fb8a4baaf0060aa5b2ab7f6566`.
The inspector covers selected session/run/event/version/review/candidate/provenance/
action/outbox/completed-claim fields; it is not a full-column or database-wide
zero-write proof, and intentionally excludes the changed authorization row.

## Final verification and handoff

- Core unit suite: **1176 passed** (36.50 s), including 15 new offline membership
  ownership/no-renewal tests, 19 inspector safety tests and both bug regressions.
- Final Core Ruff lint and format check passed (389 files); both new QA helpers
  also pass lint/format with the explicit Core configuration. Post-format focused
  regression suite: 49 passed. Static contract validation passed; no schema edits.
- Added `test_native_action_proposal_persists_then_http_verify_and_adopt` to the
  existing DB workflow suite. It exercises native datetime persistence, VERIFY
  response serialization/replay and adoption/provenance. **Collect-only locally**
  (35 tests in that file); execute in CI's disposable PostgreSQL, never rebuild
  the development Supabase DB. This test uses fixture auth, not a live provider.
- Following `playwright-visual-qa`, personally inspected
  `review-confirm-1440.png`, `adopt-confirm-{375,390,430,1440}.png`,
  `adopted-{375,390,430,1440}.png` and `expired-final-390.png` under
  `.visual-qa/wave2-chain-20260908/`. Requested/actual widths match Stage 1.
  Dialogs stayed inside the viewport; no document horizontal overflow; after
  adoption, zero pending candidates and one formal action title were visible.
- No frontend code changes or new English/keyboard/reduced-motion/device coverage
  this continuation. Screenshots are local artifacts, not CI browser automation.
- Staff logout returned 200 and subsequent `/me` 401. Dedicated QA Chrome and
  owned Core/frontend processes stopped; the earlier Agent process was already
  stopped. Synthetic audit rows are retained; no reset/delete or credential change.
- Original 14 contract-schema worktree changes remain untouched. No commit,
  push, PR or new CI result. Next: review/commit this slice and run its regression
  through the existing Gate 1; do not equate local completion with production or
  every Wave 2 story being complete.

## PR #32 CI follow-up

Initial run `34183483978` on `d1601bf` reached the new PostgreSQL regression but
failed during fixture setup: `policy_type="CONSENT_POLICY"` violated the baseline
`policy_registry_policy_type_check`. The canonical value is `CONSENT`, as used by
the existing integration fixtures. Result: 1 failed, 142 passed; the aggregate
correctly failed because `core-db` failed. All other workers passed.

Corrected only the fixture value; no schema, runtime policy or gate change.
Disposable PostgreSQL execution must be rechecked on the new CI run. The earlier
live development acceptance is separate from this test-fixture failure.
