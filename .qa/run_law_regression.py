"""Freeze local inputs, collect/run offline regressions, retain machine-derived evidence."""
import hashlib
import json
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    scopes = ["contracts", "config/rag", "data/rag-v2", "data/rag-v3", "scripts/rag",
              "services/core-api/app", "services/core-api/tests",
              "services/agent-runtime/src", "services/agent-runtime/tests",
              "services/rag-ingestion/src", "services/rag-ingestion/tests"]
    files = {path for scope in scopes for path in (ROOT / scope).rglob("*")
             if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"}
    files.update(ROOT / f"services/{name}/{file}" for name in ("core-api", "agent-runtime", "rag-ingestion")
                 for file in ("uv.lock", "pyproject.toml"))
    files.add(ROOT / "docs/project/rag-law-sync-authorization-20260910.json")
    files.add(ROOT / ".gitattributes")
    files.update(ROOT / path for path in ("services/core-api/.gitattributes", "docs/project/.gitattributes", ".qa/.gitattributes"))
    files.add(Path(__file__).resolve())
    return [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "bytes": path.stat().st_size,
             "sha256": sha(path.read_bytes())} for path in sorted(files)]


def main():
    output = Path(tempfile.mkdtemp(prefix="law-regression-", dir=ROOT / ".qa"))
    frozen = inventory()
    (output / "input-inventory.json").write_bytes(json.dumps(frozen, sort_keys=True).encode() + b"\n")
    core = ["test_law_governance_preview.py", "test_law_repair_candidate.py", "test_rag_projection_importer.py",
            "test_rag_embedding_importer.py", "test_rag_embedding_reuse_preflight.py", "test_law_repair_sync.py"]
    suites = [
        ("core-api", [f"services/core-api/tests/unit/{file}" for file in core]),
        ("agent-runtime", ["services/agent-runtime/tests"]),
        ("rag-ingestion", ["services/rag-ingestion/tests"]),
    ]
    reports = []
    for project, paths in suites:
        base = ["uv", "run", "--frozen", "--project", f"services/{project}", "pytest", *paths]
        collection = subprocess.run([*base, "--collect-only", "-q"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        collection_raw = (collection.stdout + collection.stderr).replace("\r\n", "\n").encode()
        (output / f"{project}-collection.log").write_bytes(collection_raw)
        nodes = [line.strip() for line in collection.stdout.splitlines() if "::" in line and not line.startswith(" ")]
        if collection.returncode or not nodes or inventory() != frozen:
            raise RuntimeError("collection or input freeze failed")
        command = [*base, "-q", f"--junitxml={output / (project + '.xml')}"]
        start = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        elapsed = time.monotonic() - start
        raw = (result.stdout + result.stderr).replace("\r\n", "\n").encode()
        (output / f"{project}-execution.log").write_bytes(raw)
        tree = ET.parse(output / f"{project}.xml")
        cases = tree.findall(".//testcase")
        failed = sum(case.find("failure") is not None for case in cases)
        errors = sum(case.find("error") is not None for case in cases)
        skipped = sum(case.find("skipped") is not None for case in cases)
        report = dict(project=project, command=command, exit_code=result.returncode,
                      passed=len(cases)-failed-errors-skipped, failed=failed, errors=errors, skipped=skipped,
                      elapsed_seconds=round(elapsed, 3), collected=len(nodes),
                      collected_node_sha256=sha("\n".join(nodes).encode()), log_sha256=sha(raw))
        reports.append(report)
        print(json.dumps(report), flush=True)
        if result.returncode or failed or errors or len(cases) != len(nodes) or inventory() != frozen:
            raise RuntimeError("regression failed or evidence changed")
    final = dict(status="PASS", suites=reports, input_inventory_sha256=sha(json.dumps(frozen, sort_keys=True).encode()),
                 output_path=str(output), browser_e2e="NOT_EXECUTED_NO_BROWSER_AVAILABLE")
    (output / "report.json").write_bytes(json.dumps(final, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"status": "PASS", "report_path": str(output / "report.json")}), flush=True)


if __name__ == "__main__":
    main()
