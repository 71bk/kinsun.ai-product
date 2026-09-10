import ast
import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from impact import (
    EXPECTED_JOBS,
    changed_paths,
    classify,
    main,
    make_plan,
    validate_plan,
)

ENV = {
    "GITHUB_RUN_ID": "run",
    "GITHUB_SHA": "a" * 40,
    "GITHUB_RUN_ATTEMPT": "1",
    "GITHUB_JOB": "changes",
    "GITHUB_EVENT_NAME": "pull_request",
}


def plan_for(paths, event="pull_request"):
    payload = {"pull_request": {"base": {"sha": "b" * 40}, "head": {"sha": "c" * 40}}}
    with (
        patch.dict(os.environ, ENV, clear=True),
        patch("impact.changed_paths", return_value=(paths, "d" * 40)),
        patch("impact.git", return_value=b""),
    ):
        return make_plan(Path("."), event, payload)


class ImpactTests(unittest.TestCase):
    def test_governed_repository_path_literals_cannot_skip_rag(self):
        root = Path(__file__).resolve().parents[2]
        for source in (root / "services/rag-ingestion/src").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Path"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    path = node.args[0].value
                    if path.startswith(
                        (
                            "services/",
                            "scripts/",
                            "contracts/",
                            "config/",
                            "docs/",
                            "data/",
                            "packages/",
                        )
                    ):
                        self.assertIn(
                            "rag-quality", self.selected(path), (str(source), path)
                        )

    def selected(self, *paths, event="pull_request"):
        return {job for job, value in classify(list(paths), event)[0].items() if value}

    def test_frontend_and_workspace_inputs(self):
        for path in (
            "packages/frontend/src/page.tsx",
            "packages/shared/src/index.ts",
            "package.json",
            "package-lock.json",
            ".npmrc",
        ):
            self.assertEqual(self.selected(path), {"frontend-quality"}, path)

    def test_service_boundaries_are_conservative(self):
        self.assertEqual(
            self.selected("services/core-api/app/main.py"),
            {"core-fast", "core-db", "contracts", "cross-service", "speech-quality"},
        )
        self.assertEqual(
            self.selected("services/agent-runtime/src/agent_runtime/settings.py"),
            {
                "core-fast",
                "core-db",
                "contracts",
                "cross-service",
                "agent-quality",
                "rag-quality",
            },
        )
        self.assertEqual(
            self.selected("services/speech-gateway/src/speech_gateway/tts.py"),
            {
                "core-fast",
                "core-db",
                "contracts",
                "cross-service",
                "agent-quality",
                "speech-quality",
            },
        )
        for path in (
            "services/rag-ingestion/README.md",
            "config/rag/policy.json",
            "data/rag-v3/README.md",
            "scripts/rag/project_postgres.py",
            "docs/project/rag-v3-public-retrieval-plan.md",
        ):
            self.assertEqual(
                self.selected(path),
                {
                    "core-fast",
                    "core-db",
                    "contracts",
                    "cross-service",
                    "agent-quality",
                    "rag-quality",
                },
                path,
            )

    def test_unknown_and_shared_controls_run_everything(self):
        for path in (
            "contracts/schema.json",
            "scripts/verify_contract_live.py",
            "scripts/ci/impact.py",
            ".github/workflows/gate1.yml",
            ".github/actions/check/action.yml",
            ".gitattributes",
            ".env.example",
            "AGENTS.md",
            "CLAUDE.md",
            "services/new-worker/job.py",
            "new.config",
            "data/seed.json",
            "packages/new-package/a.ts",
        ):
            self.assertEqual(self.selected(path), set(EXPECTED_JOBS), path)

    def test_core_rag_audit_inputs_include_rag_and_agent_without_frontend(self):
        for path in (
            "services/core-api/app/rag_projection_importer.py",
            "services/core-api/app/rag_embedding_importer.py",
            "services/core-api/app/rag_embedding_reuse_preflight.py",
            "services/core-api/tests/unit/test_law_governance_preview.py",
            "services/core-api/tests/unit/test_law_repair_candidate.py",
            "services/core-api/tests/unit/test_law_repair_sync.py",
            "services/core-api/tests/unit/test_rag_embedding_reuse_preflight.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(
                    self.selected(path), set(EXPECTED_JOBS) - {"frontend-quality"}
                )
                plan = plan_for([path])
                self.assertIn("core-rag", plan["reasons"]["rag-quality"])
                validate_plan(plan, "pull_request", "run", "a" * 40, 1)

    def test_docs_allowlist_is_narrow_and_union_never_suppresses_code(self):
        for path in (
            "docs/spec/故事.md",
            "docs/adr/0022-example.md",
            "CI_PIPELINE_OPTIMIZATION_REVIEW.md",
            "docs/project/ci-pipeline-optimization.md",
        ):
            self.assertEqual(self.selected(path), set(), path)
        self.assertEqual(self.selected("docs/project/other.md"), set(EXPECTED_JOBS))
        self.assertEqual(self.selected("docs/spec/fixture.json"), set(EXPECTED_JOBS))
        self.assertEqual(
            self.selected("docs/spec/story.md", "packages/frontend/a.tsx"),
            {"frontend-quality"},
        )
        self.assertIn(
            "core-db",
            self.selected(
                "packages/frontend/a.tsx", "services/core-api/alembic/versions/new.py"
            ),
        )

    def test_empty_invalid_or_non_pr_always_full(self):
        for paths in (
            [],
            [""],
            ["../README.md"],
            ["/docs/spec/a.md"],
            ["docs\\spec\\a.md"],
            ["docs/spec/a\nb.md"],
            ["docs//spec/a.md"],
        ):
            self.assertTrue(all(classify(paths, "pull_request")[0].values()))
        for event in ("push", "workflow_dispatch", "schedule", "unknown"):
            self.assertEqual(
                self.selected("docs/spec/a.md", event=event), set(EXPECTED_JOBS)
            )

    def test_no_file_list_truncation(self):
        paths = [f"docs/spec/file-{i}.md" for i in range(3500)] + [
            "services/core-api/app/main.py"
        ]
        self.assertIn("core-db", self.selected(*paths))

    def test_valid_plan_and_rerun_provenance(self):
        plan = plan_for(["packages/frontend/a.tsx"])
        self.assertIs(validate_plan(plan, "pull_request", "run", "a" * 40, 2), plan)
        for key, value in (
            ("run_id", "other"),
            ("commit", "b" * 40),
            ("attempt", "3"),
            ("policy_version", 0),
            ("event", "push"),
            ("head", None),
            ("mode", "full"),
            ("path_count", 0),
        ):
            invalid = {**plan, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_plan(invalid, "pull_request", "run", "a" * 40, 2)
        invalid = copy.deepcopy(plan)
        invalid["jobs"]["frontend-quality"] = "false"
        with self.assertRaises(ValueError):
            validate_plan(invalid, "pull_request", "run", "a" * 40, 2)
        del invalid["jobs"]["core-db"]
        with self.assertRaises(ValueError):
            validate_plan(invalid, "pull_request", "run", "a" * 40, 2)
        invalid = {**plan, "event": "push"}
        with self.assertRaises(ValueError):
            validate_plan(invalid, "push", "run", "a" * 40, 2)

    def test_diff_failure_falls_back_full_but_whitespace_failure_does_not(self):
        with patch.dict(os.environ, ENV, clear=True):
            fallback = make_plan(Path("."), "pull_request", {})
            self.assertTrue(all(fallback["jobs"].values()))
            self.assertEqual(fallback["reasons"]["core-db"], ["diff-unavailable"])
            with (
                patch(
                    "impact.changed_paths", return_value=(["docs/spec/a.md"], "d" * 40)
                ),
                patch("impact.git", side_effect=ValueError("whitespace")),
            ):
                with self.assertRaises(ValueError):
                    make_plan(
                        Path("."),
                        "pull_request",
                        {
                            "pull_request": {
                                "base": {"sha": "b" * 40},
                                "head": {"sha": "c" * 40},
                            }
                        },
                    )

    def test_cli_publishes_plan_and_literal_boolean_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            event = root / "event.json"
            event.write_text("{}")
            output, artifact = root / "outputs", root / "plan.json"
            env = {**ENV, "GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output)}
            with (
                patch.dict(os.environ, env, clear=True),
                patch("sys.argv", ["impact.py", "--out", str(artifact)]),
                patch("impact.make_plan", return_value=plan_for(["docs/spec/a.md"])),
            ):
                self.assertEqual(main(), 0)
            self.assertIn("core-db=false\n", output.read_text())
            self.assertFalse(any(json.loads(artifact.read_text())["jobs"].values()))


class GitImpactTests(unittest.TestCase):
    def test_merge_base_rename_delete_unicode_and_base_only_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def git(*args):
                return (
                    subprocess.check_output(
                        [
                            "git",
                            "-C",
                            str(root),
                            "-c",
                            "user.name=CI Test",
                            "-c",
                            "user.email=ci@example.invalid",
                            *args,
                        ],
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )

            git("init", "-b", "main")
            source = root / "services/core-api/old.py"
            source.parent.mkdir(parents=True)
            source.write_text("original\n")
            deleted = root / "services/core-api/deleted.py"
            deleted.write_text("deleted\n")
            git("add", ".")
            git("commit", "-m", "base")
            ancestor = git("rev-parse", "HEAD")
            git("checkout", "-b", "feature")
            target = root / "docs/spec/改名 file.md"
            target.parent.mkdir(parents=True)
            source.rename(target)
            deleted.unlink()
            git("add", "-A")
            git("commit", "-m", "rename and delete")
            head = git("rev-parse", "HEAD")
            git("checkout", "main")
            (root / "base-only.config").write_text("base only\n")
            git("add", ".")
            git("commit", "-m", "base moved")
            base = git("rev-parse", "HEAD")
            paths, actual = changed_paths(root, base, head)
            self.assertEqual(actual, ancestor)
            self.assertCountEqual(
                paths,
                [
                    "services/core-api/old.py",
                    "services/core-api/deleted.py",
                    "docs/spec/改名 file.md",
                ],
            )
            self.assertTrue(classify(paths, "pull_request")[0]["core-db"])
            for invalid in ("HEAD", "--help", "a" * 39):
                with self.assertRaises(ValueError):
                    changed_paths(root, invalid, head)


if __name__ == "__main__":
    unittest.main()
