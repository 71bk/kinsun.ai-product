"""Fail-closed Gate 1 aggregation with attempt-aware bounded metrics."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from impact import EXPECTED_JOBS, validate_plan
from telemetry import write_json

ALL_JOBS = ("changes", *EXPECTED_JOBS)


def failures(needs: object, selected: dict | None = None) -> list[str]:
    if not isinstance(needs, dict):
        return ["Invalid dependency results"]
    errors = []
    if set(needs) - set(ALL_JOBS):
        errors.append("Unexpected dependency jobs")
    for name in ALL_JOBS:
        value = needs.get(name)
        result = value.get("result") if isinstance(value, dict) else None
        expected = (
            "skipped"
            if selected is not None and selected.get(name) is False
            else "success"
        )
        if result != expected:
            status = (
                result
                if isinstance(result, str)
                and result in {"success", "failure", "cancelled", "skipped"}
                else "missing/invalid"
            )
            errors.append(f"{name}: {status}; expected {expected}")
    return errors


def select_reports(directory: Path, run_id: str, commit: str, attempt: int) -> dict:
    """Failed-jobs reruns may legitimately reuse successful jobs from an earlier attempt."""
    chosen = {}
    for path in sorted(directory.rglob("summary.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Invalid metric report")
        job = report.get("job")
        if job not in ALL_JOBS:
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
    plan = None
    selected = dict.fromkeys(ALL_JOBS, True)
    errors = []
    try:
        outputs = needs["changes"]["outputs"]
        plan = validate_plan(
            json.loads(outputs["plan"]),
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_RUN_ID"],
            os.environ["GITHUB_SHA"],
            int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
        for job, decision in plan["jobs"].items():
            if outputs.get(job) != str(decision).lower():
                raise ValueError("Worker condition differs from impact plan")
        selected.update(plan["jobs"])
    except (ValueError, KeyError, TypeError) as error:
        errors.append(f"Impact plan missing or invalid ({type(error).__name__})")
    errors.extend(failures(needs, selected))
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
    for job in ALL_JOBS:
        report = reports.get(job)
        if not selected[job]:
            if report is not None:
                errors.append(f"{job}: unexpected metrics for planned skip")
        elif report is None:
            errors.append(f"{job}: missing metrics")
        elif not report.get("checks") or report.get("missing_successful_test_reports"):
            errors.append(f"{job}: incomplete metrics")
        elif not isinstance(report["checks"], list) or any(
            not isinstance(check, dict) or check.get("status") != "success"
            for check in report["checks"]
        ):
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
                if isinstance(result, str)
                and result in {"success", "failure", "cancelled", "skipped"}
                else "missing/invalid",
                "expected": "success" if selected[job] else "skipped",
                "reasons": ["always-required"]
                if job == "changes"
                else plan["reasons"][job]
                if plan
                else ["invalid-plan"],
                "source_attempt": report.get("attempt") if report else None,
                "command_seconds": report.get("command_seconds") if report else None,
                "cache_hit": report.get("cache_hit") if report else None,
            }
        )
    outcome = "failure" if errors else "success"
    write_json(
        args.out,
        {
            "schema_version": 2,
            "result": outcome,
            "plan": plan,
            "jobs": rows,
            "errors": errors,
        },
    )
    lines = [
        "### Gate 1 aggregate",
        "",
        "| Job | Expected | Result | Reason | Metrics attempt | Command seconds |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['job']} | {row['expected']} | {row['result']} | {', '.join(row['reasons'])} | {row['source_attempt']} | {row['command_seconds']} |"
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
