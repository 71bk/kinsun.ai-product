# Gate 1 timing and parallelization

## Command telemetry (phase 1 merged as PR #26)

The first change keeps the serial Gate 1 topology and command order. Each dependency
install, lint/format check, test suite, audit and verifier is a separately timed step.
`scripts/ci/telemetry.py` executes argv without a shell, records a bounded JSON result,
and propagates the original exit status. Failed commands cannot become successful
because their metrics were saved. Successful test commands with missing reports fail
the summary step; an unavailable report never erases the original failed-test status.

Reports live in `$RUNNER_TEMP/ci-metrics`; raw JUnit lives in the adjacent
`ci-metrics-raw` directory and is not uploaded. Exported reports contain counts and up
to 20 slowest test identifiers, with parameter values, failure bodies, properties and
captured output excluded. Nothing is written into the checkout, preserving the
cross-service verifier's working-tree evidence. Summary/upload steps use `always()`;
hard cancellation or runner loss may prevent collection and does not imply success.

The workflow summary includes command durations, test counts, uv/npm cache restoration
outputs (unknown is distinct from false), and uncompressed JSON byte count. Cache hits
describe restoration, not successful cache saving. Native setup/cache/post-step times
remain in Actions. A complete native timing report can be fetched after a run:

```powershell
python scripts/ci/run_report.py --repository 71bk/kinsun.ai-product --run-id RUN_ID --attempt 1 --out NATIVE_REPORT_PATH
```

Use an output path outside the checkout. This read-only command requires authenticated
`gh` with Actions read access. It records the exact attempt, commit, job/step times,
initial dispatch delay and both elapsed wall time and summed runner seconds. Per-job
queue times and billing are not inferred. In-progress runs explicitly have no complete
wall/runner totals. Compare like-for-like runner/cache conditions across several runs.

## Baseline and rollout

- Pre-telemetry baseline: main `7fa7e25`, run `34075977852`, successful job 409 seconds.
  Core block 121 seconds; RAG block 168 seconds; frontend commands 59 seconds.
- Phase 1 passed the full serial pipeline: PR run `34078429651` (374 seconds), then
  main run `34079584129` at `6db3d3d` (417 seconds). The PR restored both uv and npm caches.
- Phase 1 command measurements: Core unit 30.1s, migrations 20.6s, integration 58.2s;
  RAG pytest 143.9s versus policy audit 0.7s; frontend tests 20.5s and build 13.9s.
  These are individual command times, not comparable to whole-job timing directly.
- GitHub read-only inspection on 2026-09-07 found main unprotected and no applicable
  ruleset. Publishing an aggregate check does not itself enforce branch protection.

## Phase 2: independent workers and aggregate

Phase 2 ran every PR and main push in full. PR A adds the selective policy below;
main remains full coverage.
The original 31 distinct command IDs remain covered. Dependency installs are repeated
only where a worker requires them; Core and Agent keep separate project environments.

| Worker | Checks |
| --- | --- |
| `core-fast` | CI tooling regression, Core lint/format, RAG projection dry-run, Core unit |
| `core-db` | Disposable PostgreSQL creation, migrations, integration, Core live contracts |
| `agent-quality` | Agent lint/format/tests |
| `speech-quality` | Speech lint/format/tests |
| `rag-quality` | RAG lint/format, policy audit, tests |
| `contracts` | Static contracts and Agent live contracts |
| `cross-service` | Five-run synthetic Core-to-Agent evidence |
| `frontend-quality` | npm ci, typecheck, tests, lint, production build |

Only `core-db` starts PostgreSQL. Migration lifecycle and request integration remain
separate ordered processes; Core live contracts also need the database for `/ready`.
Each Python worker caches only its installed project lockfiles, with a job-specific
uv cache suffix to avoid parallel save collisions. Caches contain downloads, not
shared virtualenvs. Cold cache and duplicate setup costs may increase runner seconds.

`synthetic-gate1` keeps the old check name and uses `if: always()` with all eight
workers in `needs`. Before PR A, `scripts/ci/gate.py` accepted only eight explicit `success` results;
failure, cancellation, skip, missing or unexpected jobs fail closed. Missing,
incomplete or unsuccessful command metrics also fail the gate. Uploading an artifact
cannot override command failure. Branch protection must separately require this check
if merge blocking is desired; this rollout does not change repository settings.

Metrics and synthetic evidence artifacts include the run attempt to permit reruns.
The aggregate selects the latest report per job from the same run and commit, allowing
earlier successful worker attempts when using **Re-run failed jobs**. Foreign/future
or conflicting reports are rejected. Aggregate summaries show worker result, source
attempt and command seconds; worker JSON retains test and cache details. Native full
wall/runner timing is collected after completion with `run_report.py`, not inferred
from a still-running aggregate job.

Workflow regression tests pin job membership, command coverage/order, DB isolation,
always-run metrics, aggregate wiring and cache separation. Gate tests cover failed,
cancelled, skipped, missing and unexpected dependencies plus report provenance/reruns.
The first parallel PR run passed; final-head and post-merge main verification follow.

### Measured rollout samples

| Topology / event | Run | Wall seconds | Runner seconds |
| --- | --- | ---: | ---: |
| Serial telemetry / PR #26 | [34078429651](https://github.com/71bk/kinsun.ai-product/actions/runs/34078429651) | 374 | 374 |
| Serial telemetry / main | [34079584129](https://github.com/71bk/kinsun.ai-product/actions/runs/34079584129) | 417 | 417 |
| Parallel / PR #27 first head `4ea276f` | [34081407110](https://github.com/71bk/kinsun.ai-product/actions/runs/34081407110) | 130 | 424 |

All are successful attempt-1 runs, measured from first job start through final job end
(including aggregate/setup/post, excluding initial dispatch). The first parallel run
restored npm cache; all seven newly scoped uv cache keys were misses. All nine jobs
passed, including the aggregate with eight valid reports and no errors. The seven
pytest/Vitest suites retained all 2,459 tests (zero failures/errors/skips): Core unit
1,103, migrations 19, integration 108, Agent 515, Speech 91, RAG 324, frontend 299.
CI helper unittests and contract/synthetic verifiers are additional checks.

Relative to the serial PR sample, wall time fell 65.2% while runner seconds rose 13.4%.
This is not a controlled benchmark: runner performance/cache state vary (RAG pytest
alone ranged from 143.9s serial to 97.5s parallel). Do not infer billed-minute savings
or promise a fixed latency reduction. First-run native jobs: Core fast 44s, DB 113s,
Agent 19s, Speech 12s, RAG 113s, contracts 21s, cross-service 17s, frontend 75s,
aggregate 10s. Job start offsets/dependency scheduling explain wall time versus the
longest worker plus aggregate. Native reports remain outside the checkout; bounded
per-command reports and aggregate results are downloadable Actions artifacts (30 days).

## Local validation

```powershell
uv run --frozen --project services/core-api --with pyyaml==6.0.2 python -m unittest discover -s scripts/ci -p 'test_*.py'
uv run --frozen --project services/core-api ruff check scripts/ci
uv run --frozen --project services/core-api ruff format --check scripts/ci
```

Use actionlint to validate workflow contexts and syntax. CI continues to own disposable
PostgreSQL lifecycle tests; never run those against the Supabase development database.

## PR A: conservative selective execution

`scripts/ci/impact.py` is the single versioned policy authority (`POLICY_VERSION=1`).
The new `changes` job always runs CI-tool tests/lint/format, then computes a PR's
merge-base-to-head Git diff and runs `git diff --check` on that range. Full checkout
history avoids file-list API pagination limits; NUL separation handles Unicode and
spaces. Rename detection is disabled so both deleted and added paths are classified.
No PR-supplied filename/ref is interpolated into a shell command. Unknown paths,
empty diffs or unavailable comparison commits select all workers. A whitespace check
failure fails `changes`; it is not converted into a successful docs-only skip.
For non-PR events, including every main push, all workers are selected.

| Changed paths | Selected workers (union for mixed changes) |
| --- | --- |
| `packages/frontend/`, `packages/shared/`, root package.json/lock/.npmrc | frontend-quality |
| `services/core-api/` | core-fast, core-db, contracts, cross-service, speech-quality |
| `services/agent-runtime/` | core-fast, core-db, contracts, cross-service, agent-quality, rag-quality |
| `services/speech-gateway/`, `evals/speech/` | core-fast, core-db, contracts, cross-service, agent-quality, speech-quality |
| `services/rag-ingestion/`, `config/rag/`, `data/rag/`, `data/rag-*`, `scripts/rag/`, public retrieval plan | core-fast, core-db, contracts, cross-service, agent-quality, rag-quality |
| `docs/spec/*.md`, `docs/adr/*.md`, this CI note, CI_PIPELINE_OPTIMIZATION_REVIEW.md | changes only; workers skipped |
| Everything else, including contracts, CI files, new services and shared controls | all workers |

The public retrieval plan is `docs/project/rag-v3-public-retrieval-plan.md`. It and
Agent implementation/test files are hashed inputs of RAG governance validators.
Their changes MUST select RAG even if the edited file is Markdown or outside the
ingestion service. A regression test scans repository `Path(...)` literals in RAG
implementation to guard this dependency. It is a supplementary guard, not a universal
dependency discovery engine; new dynamic dependencies still require policy review.
Most documentation outside the explicit whitelist deliberately falls back to full CI.

Workers depend only on `changes` and literal `true` output flags. The aggregate still
always runs and now needs `changes` plus all eight workers. It validates the plan's
schema/policy version, event, run, commit, attempt, all eight boolean decisions and
bounded reasons, and checks that each scheduling flag agrees with that plan.
`changes` and selected workers require success plus valid metrics. Only explicitly
unselected workers may be skipped and omit metrics; unexpected skips, missing results,
failed/cancelled jobs, invalid plans or metrics for skipped workers fail closed.
Even docs-only runs upload `changes` metrics, so aggregate download is never empty on
a successful run. Plan JSON is included in that artifact and the aggregate summary;
no raw changed filenames or event payloads are exported. Existing attempt-aware
artifact selection continues to support successful jobs reused by failed-job reruns.

Acceptance coverage: pure docs/frontend/Core/Agent/Speech/RAG, mixed paths, migrations,
contracts/shared tooling/unknown paths, 3,500+ paths, real Git rename/delete/Unicode,
base-only commits, unavailable diff, whitespace rejection, full non-PR events,
planned vs accidental skips, condition/plan mismatch, missing plan/metrics and reruns.
This PR changes scheduling only: no RAG performance changes, new build caches,
branch protection, provider credentials, deployment or browser E2E are included.
