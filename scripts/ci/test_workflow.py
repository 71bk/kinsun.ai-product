"""Protect Gate 1 coverage, isolation and fail-closed aggregation topology."""

import re
import unittest
from pathlib import Path

import yaml

from gate import EXPECTED_JOBS


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/gate1.yml"
        cls.workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls.jobs = cls.workflow["jobs"]

    def test_independent_workers_and_strict_aggregate(self):
        self.assertEqual(set(self.jobs), {*EXPECTED_JOBS, "changes", "synthetic-gate1"})
        gate = self.jobs["synthetic-gate1"]
        self.assertEqual(gate["name"], "synthetic-gate1")
        self.assertEqual(gate["if"], "always()")
        self.assertCountEqual(gate["needs"], ["changes", *EXPECTED_JOBS])
        for name, job in self.jobs.items():
            self.assertNotIn("continue-on-error", job)
            if name in EXPECTED_JOBS:
                self.assertEqual(job["needs"], "changes")
                self.assertEqual(job["if"], f"needs.changes.outputs.{name} == 'true'")
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)
        downloads = [
            step
            for step in gate["steps"]
            if "download-artifact" in step.get("uses", "")
        ]
        self.assertEqual(downloads[0]["with"]["pattern"], "ci-metrics-*")
        check = next(step for step in gate["steps"] if "gate.py" in step.get("run", ""))
        self.assertEqual(check["if"], "always()")
        self.assertEqual(check["env"]["NEEDS_JSON"], "${{ toJSON(needs) }}")
        changes = self.jobs["changes"]
        self.assertNotIn("if", changes)
        self.assertNotIn("needs", changes)
        self.assertEqual(changes["steps"][0]["with"]["fetch-depth"], 0)
        self.assertEqual(set(changes["outputs"]), {"plan", *EXPECTED_JOBS})
        for key, expression in changes["outputs"].items():
            self.assertEqual(expression, "${{ steps.plan.outputs." + key + " }}")
        # PyYAML 1.1 treats the workflow's unquoted `on` key as True.
        triggers = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual(set(triggers), {"pull_request", "push"})
        for trigger in triggers.values():
            self.assertEqual(trigger, {"branches": ["main"]})

    def test_all_command_coverage_and_db_order(self):
        expected = {
            "changes": ["ci-tools", "ci-policy-lint", "ci-policy-format", "impact"],
            "core-fast": [
                "install-core",
                "core-lint",
                "core-format",
                "core-rag-dry-run",
                "core-unit",
            ],
            "core-db": [
                "install-core",
                "database-create",
                "core-migrations",
                "core-integration",
                "contracts-core",
            ],
            "agent-quality": [
                "install-agent",
                "agent-lint",
                "agent-format",
                "agent-tests",
            ],
            "speech-quality": [
                "install-speech",
                "speech-lint",
                "speech-format",
                "speech-tests",
            ],
            "rag-quality": [
                "install-rag",
                "rag-lint",
                "rag-format",
                "rag-policy-audit",
                "rag-tests",
            ],
            "contracts": [
                "install-core",
                "install-agent",
                "contracts-static",
                "contracts-agent",
            ],
            "cross-service": ["install-core", "install-agent", "cross-service"],
            "frontend-quality": [
                "frontend-install",
                "frontend-typecheck",
                "frontend-tests",
                "frontend-lint",
                "frontend-build",
            ],
        }
        for name, ids in expected.items():
            commands = "\n".join(
                step.get("run", "") for step in self.jobs[name]["steps"]
            )
            self.assertEqual(re.findall(r"--id ([a-z-]+) --", commands), ids, name)
        db_jobs = [name for name, job in self.jobs.items() if "services" in job]
        self.assertEqual(db_jobs, ["core-db"])
        postgres = self.jobs["core-db"]["services"]["postgres"]
        self.assertIn("@sha256:", postgres["image"])
        self.assertIn("--health-cmd", postgres["options"])
        steps = self.jobs["core-db"]["steps"]
        integration = next(
            step["run"]
            for step in steps
            if "--id core-integration " in step.get("run", "")
        )
        self.assertIn(
            "--ignore=services/core-api/tests/integration/test_migrations.py",
            integration,
        )

    def test_worker_metrics_and_isolated_caches(self):
        for name in EXPECTED_JOBS:
            steps = self.jobs[name]["steps"]
            summary = next(
                step
                for step in steps
                if step.get("run") == "python scripts/ci/telemetry.py summary"
            )
            self.assertEqual(summary["if"], "always()")
            upload = next(
                step
                for step in steps
                if step.get("name") == "Upload bounded CI metrics"
            )
            self.assertEqual(upload["if"], "always()")
            self.assertEqual(
                upload["with"]["name"],
                "ci-metrics-${{ github.job }}-${{ github.run_attempt }}",
            )
            self.assertEqual(upload["with"]["path"], "${{ runner.temp }}/ci-metrics/")
            if name != "frontend-quality":
                setup = next(
                    step for step in steps if "setup-uv@" in step.get("uses", "")
                )
                self.assertEqual(setup["with"]["cache-suffix"], name)
                self.assertNotIn("**", setup["with"]["cache-dependency-glob"])


if __name__ == "__main__":
    unittest.main()
