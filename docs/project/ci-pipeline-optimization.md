# Gate 1 timing and parallelization

## Phase 1: command telemetry

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
- Phase 1 must pass the full serial pipeline before parallelization.
- Phase 2 will keep every existing command, isolate the Core database job, and preserve
  the `synthetic-gate1` check name as an aggregate of eight required jobs.
- GitHub read-only inspection on 2026-09-07 found main unprotected and no applicable
  ruleset. Publishing an aggregate check does not itself enforce branch protection.

## Local validation

```powershell
python -m unittest discover -s scripts/ci -p 'test_*.py'
uv run --frozen --project services/core-api ruff check scripts/ci
uv run --frozen --project services/core-api ruff format --check scripts/ci
```

Use actionlint to validate workflow contexts and syntax. CI continues to own disposable
PostgreSQL lifecycle tests; never run those against the Supabase development database.
