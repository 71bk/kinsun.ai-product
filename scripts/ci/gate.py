"""Fail-closed Gate 1 aggregation with attempt-aware bounded metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from telemetry import write_json

EXPECTED_JOBS = (
    "core-fast",
    "core-db",
    "agent-quality",
    "speech-quality",
    "rag-quality",
    "contracts",
    "cross-service",
    "frontend-quality",
)


def failures(needs: object) -> list[str]:
    if not isinstance(needs, dict):
        return ["Invalid dependency results"]
    errors = []
    if set(needs) - set(EXPECTED_JOBS):
        errors.append("Unexpected dependency jobs")
    for name in EXPECTED_JOBS:
        value = needs.get(name)
        result = value.get("result") if isinstance(value, dict) else None
        if result != "success":
            status = (
                result
                if result in {"failure", "cancelled", "skipped"}
                else "missing/invalid"
            )
            errors.append(f"{name}: {status}")
    return errors


def select_reports(directory: Path, run_id: str, commit: str, attempt: int) -> dict:
    """Failed-jobs reruns may legitimately reuse successful jobs from an earlier attempt."""
    chosen = {}
    for path in sorted(directory.rglob("summary.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        job = report.get("job")
        if job not in EXPECTED_JOBS:
            raise ValueError("Unknown job in metric artifact")
        if (
            report.get("schema_version") != 1
            or report.get("run_id") != run_id
            or report.get("commit") != commit
        ):
            raise ValueError("Metric artifact provenance mismatch")
        source_attempt = int(report["attempt"])
        if source_attempt < 1 or source_attempt > attempt:
            raise ValueError("Metric artifact attempt mismatch")
        previous = chosen.get(job)
        if previous is None or source_attempt > int(previous["attempt"]):
            chosen[job] = report
        elif source_attempt == int(previous["attempt"]) and report != previous:
            raise ValueError("Conflicting metric artifacts")
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        needs = json.loads(os.environ.get("NEEDS_JSON", "null"))
    except ValueError:
        needs = None
    errors = failures(needs)
    reports = {}
    try:
        reports = select_reports(
            args.metrics,
            os.environ["GITHUB_RUN_ID"],
            os.environ["GITHUB_SHA"],
            int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"Metrics unavailable or invalid ({type(error).__name__})")
    rows = []
    for job in EXPECTED_JOBS:
        report = reports.get(job)
        if report is None:
            errors.append(f"{job}: missing metrics")
        elif not report.get("checks") or report.get("missing_successful_test_reports"):
            errors.append(f"{job}: incomplete metrics")
        elif any(check.get("status") != "success" for check in report["checks"]):
            errors.append(f"{job}: unsuccessful command metrics")
        result = (
            needs.get(job, {}).get("result")
            if isinstance(needs, dict) and isinstance(needs.get(job), dict)
            else None
        )
        rows.append(
            {
                "job": job,
                "result": result
                if result in {"success", "failure", "cancelled", "skipped"}
                else "missing/invalid",
                "source_attempt": report.get("attempt") if report else None,
                "command_seconds": report.get("command_seconds") if report else None,
                "cache_hit": report.get("cache_hit") if report else None,
            }
        )
    outcome = "failure" if errors else "success"
    write_json(
        args.out,
        {"schema_version": 1, "result": outcome, "jobs": rows, "errors": errors},
    )
    lines = [
        "### Gate 1 aggregate",
        "",
        "| Job | Result | Metrics attempt | Command seconds |",
        "| --- | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['job']} | {row['result']} | {row['source_attempt']} | {row['command_seconds']} |"
        )
    lines.extend(
        [
            "",
            f"Aggregate: {outcome}.",
            "Command times exclude setup/post and are not summed as workflow wall time.",
        ]
    )
    lines.extend(f"- {error}" for error in errors)
    summary = "\n".join(lines) + "\n"
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    print(summary)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
