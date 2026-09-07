"""Bounded CI timing/test reports; commands retain their original exit status."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path


def metrics_dir() -> Path:
    default = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "ci-metrics"
    return Path(os.environ.get("CI_METRICS_DIR", default))


def identity() -> dict[str, str]:
    return {
        key: os.environ.get(env, "local")
        for key, env in {
            "run_id": "GITHUB_RUN_ID",
            "attempt": "GITHUB_RUN_ATTEMPT",
            "commit": "GITHUB_SHA",
            "job": "GITHUB_JOB",
        }.items()
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )


def junit_summary(path: Path) -> dict:
    """Discard stdout, properties, failure bodies and parameter values before upload."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    suites = [node for node in root.iter("testsuite") if not node.findall("testsuite")]
    slowest = []
    for case in cases:
        name = case.get("name", "unknown").split("[", 1)[0]
        suite = case.get("classname", "unknown").split("[", 1)[0]
        # Names are identifiers only, never rendered as executable Markdown/HTML.
        label = re.sub(r"[^a-zA-Z0-9_./ :>-]", "_", f"{suite}::{name}")[:180]
        slowest.append(
            {
                "test": label,
                "id": hashlib.sha256(
                    f"{case.get('classname')}::{case.get('name')}".encode()
                ).hexdigest()[:16],
                "seconds": float(case.get("time", "0")),
            }
        )
    return {
        "tests": sum(int(suite.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.get("skipped", "0")) for suite in suites),
        "case_count": len(cases),
        "slowest": sorted(slowest, key=lambda item: item["seconds"], reverse=True)[:20],
    }


def run_check(check_id: str, command: list[str], test_format: str | None = None) -> int:
    if not re.fullmatch(r"[a-z0-9-]+", check_id) or not command:
        raise ValueError("A bounded check identifier and command are required")
    directory = metrics_dir()
    record = {
        "schema_version": 1,
        **identity(),
        "check": check_id,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "in_progress",
    }
    destination = directory / "checks" / f"{check_id}.json"
    write_json(destination, record)
    report = directory.parent / f"{directory.name}-raw" / f"{check_id}.xml"
    if test_format:
        report.parent.mkdir(parents=True, exist_ok=True)
        if report.exists():
            report.unlink()  # Only this check's stale raw report, never a directory.
        if test_format == "pytest":
            command = [*command, "--durations=20", f"--junitxml={report}"]
        else:
            command = [
                *command,
                "--reporter=default",
                "--reporter=junit",
                f"--outputFile={report}",
            ]
    started = time.monotonic()
    exit_code = 127
    try:
        exit_code = subprocess.run(command, check=False).returncode
    except OSError as error:
        record["launch_error_type"] = type(error).__name__
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        record.update(
            finished_at=datetime.now(UTC).isoformat(),
            seconds=round(time.monotonic() - started, 4),
            exit_code=exit_code,
            status="success" if exit_code == 0 else "failure",
        )
        if test_format:
            try:
                record["tests"] = junit_summary(report)
                record["test_report_status"] = "available"
            except (OSError, ET.ParseError, ValueError) as error:
                record["test_report_status"] = "unavailable"
                record["report_error_type"] = type(error).__name__
        write_json(destination, record)
    # Python's negative return code denotes a signal; use the shell convention.
    return exit_code if exit_code >= 0 else 128 - exit_code


def cache_state(value: str | None) -> str:
    return value if value in {"true", "false"} else "unknown"


def summarize() -> int:
    directory = metrics_dir()
    checks = [
        json.loads(path.read_text())
        for path in sorted((directory / "checks").glob("*.json"))
    ]
    unavailable = [
        item["check"]
        for item in checks
        if item.get("test_report_status") == "unavailable"
        and item["status"] == "success"
    ]
    report = {
        "schema_version": 1,
        **identity(),
        "command_seconds": round(sum(item.get("seconds", 0) for item in checks), 4),
        "cache_hit": {
            "uv": cache_state(os.environ.get("CI_UV_CACHE_HIT")),
            "npm": cache_state(os.environ.get("CI_NPM_CACHE_HIT")),
        },
        "checks": checks,
        "missing_successful_test_reports": unavailable,
        "timing_scope": "commands only; use Actions job/step timestamps for setup, post and queue",
    }
    write_json(directory / "summary.json", report)
    size = sum(path.stat().st_size for path in directory.rglob("*.json"))
    lines = [
        f"### CI metrics: {identity()['job']}",
        "",
        "| Check | Result | Seconds | Tests / failures / errors / skipped |",
        "| --- | --- | ---: | --- |",
    ]
    for item in checks:
        tests = item.get("tests", {})
        counts = (
            " / ".join(
                str(tests[key]) for key in ("tests", "failures", "errors", "skipped")
            )
            if tests
            else "—"
        )
        lines.append(
            f"| {item['check']} | {item['status']} | {item.get('seconds', 0):.2f} | {counts} |"
        )
    lines.extend(
        [
            "",
            f"Cache restored — uv: {report['cache_hit']['uv']}; npm: {report['cache_hit']['npm']}.",
            f"Report JSON bytes before artifact compression: {size}.",
            "Command totals exclude setup, post steps and queue time; they are not workflow wall time.",
            "Per-check JSON includes up to 20 slowest test identifiers and durations.",
        ]
    )
    if unavailable:
        lines.append(
            "Missing reports for successful test commands: " + ", ".join(unavailable)
        )
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if unavailable or not checks else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--id", required=True)
    run.add_argument("--test-format", choices=("pytest", "vitest"))
    run.add_argument("command", nargs=argparse.REMAINDER)
    subparsers.add_parser("summary")
    args = parser.parse_args()
    if args.operation == "summary":
        return summarize()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return run_check(args.id, command, args.test_format)


if __name__ == "__main__":
    sys.exit(main())
