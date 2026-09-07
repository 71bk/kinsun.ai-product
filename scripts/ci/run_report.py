"""Read GitHub's native job/step timings for one explicit workflow run attempt."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from telemetry import write_json


def seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end or end.startswith("0001-"):
        return None
    return max(
        0, (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
    )


def build_report(run: dict, jobs: list[dict]) -> dict:
    started = [job["started_at"] for job in jobs if job.get("started_at")]
    completed = [job["completed_at"] for job in jobs if job.get("completed_at")]
    all_complete = bool(jobs) and all(job["status"] == "completed" for job in jobs)
    entries = [
        {
            "job": job["name"],
            "status": job["status"],
            "conclusion": job.get("conclusion"),
            "seconds": seconds(job.get("started_at"), job.get("completed_at")),
            "steps": [
                {
                    "name": step["name"],
                    "conclusion": step.get("conclusion"),
                    "seconds": seconds(
                        step.get("started_at"), step.get("completed_at")
                    ),
                }
                for step in job.get("steps", [])
            ],
        }
        for job in jobs
    ]
    return {
        "schema_version": 1,
        "run_id": run["id"],
        "attempt": run["run_attempt"],
        "commit": run["head_sha"],
        "event": run["event"],
        "status": run["status"],
        "conclusion": run.get("conclusion"),
        "url": run["html_url"],
        "initial_dispatch_seconds": seconds(run.get("run_started_at"), min(started))
        if started
        else None,
        "wall_seconds": seconds(min(started), max(completed)) if all_complete else None,
        "runner_seconds": sum(entry["seconds"] or 0 for entry in entries)
        if all_complete
        else None,
        "complete": all_complete,
        "timing_scope": "native job start/end including setup/post; runner seconds are not billed minutes; per-job queue unavailable",
        "jobs": entries,
    }


def api(path: str, *, paginate: bool = False):
    command = ["gh", "api", path]
    if paginate:
        command.extend(["--paginate", "--slurp"])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("GitHub timing metadata could not be retrieved")
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (
        not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repository)
        or min(args.run_id, args.attempt) < 1
    ):
        parser.error("An explicit repository, run and attempt are required")
    base = f"repos/{args.repository}/actions/runs/{args.run_id}/attempts/{args.attempt}"
    try:
        run = api(base)
        jobs = [
            job
            for page in api(f"{base}/jobs?per_page=100", paginate=True)
            for job in page["jobs"]
        ]
        report = build_report(run, jobs)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"Timing metadata unavailable ({type(error).__name__})")
        return 1
    write_json(args.out, report)
    print(f"Native timing report: complete={report['complete']}; jobs={len(jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
