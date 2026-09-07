"""Conservative, versioned Gate 1 impact policy. No network/API file-list limits."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from telemetry import identity, write_json

POLICY_VERSION = 1
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
CORE = {"core-fast", "core-db", "contracts", "cross-service"}
AGENT = CORE | {"agent-quality"}
RAG = AGENT | {"rag-quality"}
SPEECH = CORE | {"speech-quality", "agent-quality"}
# Service prefixes include the trailing slash; RAG data additionally uses versioned names.
RULES = (
    ("core", ("services/core-api/",), CORE | {"speech-quality"}),
    # RAG governance hashes Agent implementation/tests as inputs, not just RAG files.
    ("agent", ("services/agent-runtime/",), RAG),
    ("speech", ("services/speech-gateway/", "evals/speech/"), SPEECH),
    (
        "rag",
        (
            "services/rag-ingestion/",
            "config/rag/",
            "data/rag/",
            "data/rag-",
            "scripts/rag/",
        ),
        RAG,
    ),
    ("frontend", ("packages/frontend/", "packages/shared/"), {"frontend-quality"}),
)
FRONTEND_FILES = {"package.json", "package-lock.json", ".npmrc"}
DOC_FILES = {
    "CI_PIPELINE_OPTIMIZATION_REVIEW.md",
    "docs/project/ci-pipeline-optimization.md",
}
REASONS = {item[0] for item in RULES} | {
    "full-event",
    "unknown-path",
    "empty-diff",
    "diff-unavailable",
    "invalid-path",
    "not-affected",
    "governed-rag-document",
}


def classify(paths: list[str], event: str) -> tuple[dict, dict]:
    selected = set()
    reasons = {job: set() for job in EXPECTED_JOBS}

    def include(jobs, reason):
        selected.update(jobs)
        for job in jobs:
            reasons[job].add(reason)

    if event != "pull_request":
        include(EXPECTED_JOBS, "full-event")
    elif not paths:
        include(EXPECTED_JOBS, "empty-diff")
    else:
        for path in paths:
            if (
                not isinstance(path, str)
                or not path
                or path.startswith("/")
                or "\\" in path
                or any(ord(char) < 32 for char in path)
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                include(EXPECTED_JOBS, "invalid-path")
                continue
            if path == "docs/project/rag-v3-public-retrieval-plan.md":
                include(RAG, "governed-rag-document")
            elif path in FRONTEND_FILES:
                include({"frontend-quality"}, "frontend")
            elif path in DOC_FILES or (
                path.startswith(("docs/spec/", "docs/adr/")) and path.endswith(".md")
            ):
                continue
            else:
                matched = False
                for reason, prefixes, jobs in RULES:
                    if path.startswith(prefixes):
                        include(jobs, reason)
                        matched = True
                if not matched:
                    include(EXPECTED_JOBS, "unknown-path")
    return (
        {job: job in selected for job in EXPECTED_JOBS},
        {job: sorted(value) or ["not-affected"] for job, value in reasons.items()},
    )


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False, timeout=60
    )
    if result.returncode:
        raise ValueError("Git comparison unavailable")
    return result.stdout


def changed_paths(root: Path, base: str, head: str) -> tuple[list[str], str]:
    if not all(
        isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
        for sha in (base, head)
    ):
        raise ValueError("Invalid comparison commits")
    ancestor = git(root, "merge-base", base, head).decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", ancestor):
        raise ValueError("Invalid merge base")
    # Disable rename detection so BOTH removed and added paths participate in the union.
    raw = git(
        root,
        "diff",
        "--no-ext-diff",
        "--no-renames",
        "--name-only",
        "-z",
        ancestor,
        head,
        "--",
    )
    if raw and not raw.endswith(b"\0"):
        raise ValueError("Incomplete file list")
    paths = sorted(set(raw.decode("utf-8").split("\0")[:-1])) if raw else []
    return paths, ancestor


def make_plan(root: Path, event: str, payload: dict) -> dict:
    base = head = ancestor = None
    paths = []
    fallback = False
    if event == "pull_request":
        try:
            base = payload["pull_request"]["base"]["sha"]
            head = payload["pull_request"]["head"]["sha"]
            paths, ancestor = changed_paths(root, base, head)
        except (KeyError, TypeError, ValueError, OSError, subprocess.TimeoutExpired):
            fallback = True
    jobs, reasons = classify(paths, event)
    if fallback:
        jobs = dict.fromkeys(EXPECTED_JOBS, True)
        reasons = {job: ["diff-unavailable"] for job in EXPECTED_JOBS}
        base = head = ancestor = None
    # A docs-only green still validates whitespace; this error MUST NOT become a skip.
    if ancestor:
        git(root, "diff", "--no-ext-diff", "--check", ancestor, head, "--")
    return {
        "schema_version": 1,
        "policy_version": POLICY_VERSION,
        **identity(),
        "event": event,
        "base": base,
        "head": head,
        "merge_base": ancestor,
        "path_count": len(paths),
        "paths_sha256": hashlib.sha256(
            json.dumps(paths, ensure_ascii=True).encode()
        ).hexdigest(),
        "mode": "full" if all(jobs.values()) else "selective",
        "jobs": jobs,
        "reasons": reasons,
    }


def validate_plan(
    plan: object, event: str, run_id: str, commit: str, attempt: int
) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("Missing impact plan")
    if (
        plan.get("schema_version") != 1
        or plan.get("policy_version") != POLICY_VERSION
        or plan.get("job") != "changes"
        or plan.get("run_id") != run_id
        or plan.get("commit") != commit
        or plan.get("event") != event
        or not 1 <= int(plan["attempt"]) <= attempt
    ):
        raise ValueError("Impact plan provenance mismatch")
    jobs, reasons = plan.get("jobs"), plan.get("reasons")
    if (
        not isinstance(jobs, dict)
        or set(jobs) != set(EXPECTED_JOBS)
        or any(type(value) is not bool for value in jobs.values())
        or not isinstance(reasons, dict)
        or set(reasons) != set(EXPECTED_JOBS)
    ):
        raise ValueError("Invalid impact decisions")
    for job, values in reasons.items():
        if (
            not isinstance(values, list)
            or not values
            or any(
                not isinstance(value, str) or value not in REASONS for value in values
            )
            or (jobs[job] and "not-affected" in values)
            or (not jobs[job] and values != ["not-affected"])
        ):
            raise ValueError("Invalid impact reasons")
    if event != "pull_request" and not all(jobs.values()):
        raise ValueError("Non-PR events require full coverage")
    if plan.get("mode") != ("full" if all(jobs.values()) else "selective"):
        raise ValueError("Impact mode mismatch")
    if not all(jobs.values()) and (
        not all(
            isinstance(plan.get(key), str) and re.fullmatch(r"[0-9a-f]{40}", plan[key])
            for key in ("base", "head", "merge_base")
        )
        or type(plan.get("path_count")) is not int
        or plan["path_count"] < 1
    ):
        raise ValueError("Selective plan requires a complete nonempty comparison")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        event = os.environ["GITHUB_EVENT_NAME"]
        payload = json.loads(
            Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
        )
        plan = make_plan(Path.cwd(), event, payload)
        validate_plan(
            plan,
            event,
            os.environ["GITHUB_RUN_ID"],
            os.environ["GITHUB_SHA"],
            int(os.environ["GITHUB_RUN_ATTEMPT"]),
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.TimeoutExpired,
    ) as error:
        print(
            f"Impact planning failed ({type(error).__name__}); no skip decisions published"
        )
        return 1
    write_json(args.out, plan)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write("plan=" + json.dumps(plan, separators=(",", ":")) + "\n")
        for job, selected in plan["jobs"].items():
            stream.write(f"{job}={str(selected).lower()}\n")
    summary = [
        "### Gate 1 impact plan",
        "",
        f"Mode: {plan['mode']}; changed paths: {plan['path_count']}.",
        "",
    ]
    summary.extend(
        f"- {job}: {'run' if selected else 'skip'} ({', '.join(plan['reasons'][job])})"
        for job, selected in plan["jobs"].items()
    )
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(summary) + "\n")
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
