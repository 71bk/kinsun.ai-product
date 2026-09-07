import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gate import EXPECTED_JOBS, failures, main, select_reports


class GateTests(unittest.TestCase):
    def test_cli_requires_successful_metrics_even_when_needs_succeed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics"
            output = root / "aggregate.json"
            env = {
                "NEEDS_JSON": json.dumps(
                    {job: {"result": "success"} for job in EXPECTED_JOBS}
                ),
                "GITHUB_RUN_ID": "run",
                "GITHUB_SHA": "sha",
                "GITHUB_RUN_ATTEMPT": "1",
            }
            argv = ["gate.py", "--metrics", str(metrics), "--out", str(output)]
            with patch.dict(os.environ, env, clear=True), patch("sys.argv", argv):
                self.assertEqual(main(), 1)
                for job in EXPECTED_JOBS:
                    directory = metrics / job
                    directory.mkdir(parents=True)
                    report = {
                        "schema_version": 1,
                        "job": job,
                        "run_id": "run",
                        "commit": "sha",
                        "attempt": "1",
                        "checks": [{"status": "success"}],
                    }
                    (directory / "summary.json").write_text(json.dumps(report))
                self.assertEqual(main(), 0)
                path = metrics / "core-db" / "summary.json"
                report = json.loads(path.read_text())
                report["checks"][0]["status"] = "failure"
                path.write_text(json.dumps(report))
                self.assertEqual(main(), 1)
                self.assertEqual(json.loads(output.read_text())["result"], "failure")

    def test_only_all_expected_successes_pass(self):
        needs = {job: {"result": "success"} for job in EXPECTED_JOBS}
        self.assertEqual(failures(needs), [])
        for job in EXPECTED_JOBS:
            for result in ("failure", "cancelled", "skipped", None, "unknown"):
                with self.subTest(job=job, result=result):
                    self.assertTrue(failures({**needs, job: {"result": result}}))
            missing = dict(needs)
            del missing[job]
            self.assertTrue(failures(missing))
        self.assertTrue(failures({**needs, "extra": {"result": "success"}}))
        self.assertTrue(failures({}))
        self.assertTrue(failures(None))
        self.assertTrue(failures({**needs, "core-db": "success"}))

    def test_rerun_uses_latest_same_run_and_commit_per_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def save(job, attempt, **overrides):
                folder = root / f"{job}-{attempt}"
                folder.mkdir(exist_ok=True)
                value = dict(
                    schema_version=1,
                    job=job,
                    run_id="run",
                    commit="sha",
                    attempt=str(attempt),
                    **overrides,
                )
                (folder / "summary.json").write_text(json.dumps(value))

            save("core-fast", 1)
            save("core-db", 1)
            save("core-db", 2)
            reports = select_reports(root, "run", "sha", 2)
            self.assertEqual(reports["core-fast"]["attempt"], "1")
            self.assertEqual(reports["core-db"]["attempt"], "2")
            for run_id, sha, attempt in [
                ("other", "sha", 2),
                ("run", "other", 2),
                ("run", "sha", 1),
            ]:
                with (
                    self.subTest(run_id=run_id, sha=sha, attempt=attempt),
                    self.assertRaises(ValueError),
                ):
                    select_reports(root, run_id, sha, attempt)


if __name__ == "__main__":
    unittest.main()
