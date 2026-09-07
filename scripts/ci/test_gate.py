import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gate import ALL_JOBS, EXPECTED_JOBS, failures, main, select_reports
from test_impact import ENV, plan_for


class GateTests(unittest.TestCase):
    def setUp(self):
        printer = patch("gate.print")
        printer.start()
        self.addCleanup(printer.stop)

    def test_planned_skips_need_no_metrics_but_changes_always_does(self):
        for paths in (["docs/spec/story.md"], ["packages/frontend/page.tsx"]):
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                metrics, output = root / "metrics", root / "gate.json"
                plan = plan_for(paths)
                selected = {"changes": True, **plan["jobs"]}
                needs = {
                    job: {"result": "success" if selected[job] else "skipped"}
                    for job in ALL_JOBS
                }
                needs["changes"]["outputs"] = {
                    "plan": json.dumps(plan),
                    **{job: str(value).lower() for job, value in plan["jobs"].items()},
                }
                for job in ALL_JOBS:
                    if selected[job]:
                        directory = metrics / job
                        directory.mkdir(parents=True)
                        (directory / "summary.json").write_text(
                            json.dumps(
                                {
                                    "schema_version": 1,
                                    "job": job,
                                    "run_id": "run",
                                    "commit": "a" * 40,
                                    "attempt": "1",
                                    "checks": [{"status": "success"}],
                                }
                            )
                        )
                env = {**ENV, "NEEDS_JSON": json.dumps(needs)}
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch(
                        "sys.argv",
                        ["gate.py", "--metrics", str(metrics), "--out", str(output)],
                    ),
                ):
                    self.assertEqual(main(), 0)
                    for job in ALL_JOBS:
                        previous = needs[job]["result"]
                        for status in (
                            "failure",
                            "cancelled",
                            "unknown",
                            None,
                            "skipped" if selected[job] else "success",
                        ):
                            needs[job]["result"] = status
                            os.environ["NEEDS_JSON"] = json.dumps(needs)
                            self.assertEqual(main(), 1, (job, status))
                        needs[job]["result"] = previous
                    needs["changes"]["outputs"]["core-db"] = "true"
                    os.environ["NEEDS_JSON"] = json.dumps(needs)
                    self.assertEqual(main(), 1)
                    del needs["changes"]["outputs"]["plan"]
                    os.environ["NEEDS_JSON"] = json.dumps(needs)
                    self.assertEqual(main(), 1)
                    needs["changes"]["outputs"] = {
                        "plan": json.dumps(plan),
                        **{
                            job: str(value).lower()
                            for job, value in plan["jobs"].items()
                        },
                    }
                    os.environ["NEEDS_JSON"] = json.dumps(needs)
                    (metrics / "changes" / "summary.json").unlink()
                    self.assertEqual(main(), 1)

    def test_cli_requires_successful_metrics_even_when_needs_succeed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metrics = root / "metrics"
            output = root / "aggregate.json"
            env = {
                "NEEDS_JSON": json.dumps(
                    {job: {"result": "success"} for job in ALL_JOBS}
                ),
                "GITHUB_RUN_ID": "run",
                "GITHUB_SHA": "a" * 40,
                "GITHUB_EVENT_NAME": "pull_request",
                "GITHUB_RUN_ATTEMPT": "1",
            }
            dependencies = json.loads(env["NEEDS_JSON"])
            plan = plan_for(["unknown.config"])
            dependencies["changes"]["outputs"] = {
                "plan": json.dumps(plan),
                **{job: "true" for job in EXPECTED_JOBS},
            }
            env["NEEDS_JSON"] = json.dumps(dependencies)
            argv = ["gate.py", "--metrics", str(metrics), "--out", str(output)]
            with patch.dict(os.environ, env, clear=True), patch("sys.argv", argv):
                self.assertEqual(main(), 1)
                for job in ALL_JOBS:
                    directory = metrics / job
                    directory.mkdir(parents=True)
                    report = {
                        "schema_version": 1,
                        "job": job,
                        "run_id": "run",
                        "commit": "a" * 40,
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
        needs = {job: {"result": "success"} for job in ALL_JOBS}
        self.assertEqual(failures(needs), [])
        for job in ALL_JOBS:
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
