"""CI failure propagation and bounded report regression tests (no services/network)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import telemetry


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.environment = patch.dict(
            os.environ, {"CI_METRICS_DIR": str(self.directory / "metrics")}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_failed_command_retains_exit_code_and_records_timing(self):
        code = telemetry.run_check(
            "expected-failure", [sys.executable, "-c", "raise SystemExit(7)"]
        )
        self.assertEqual(code, 7)
        result = json.loads(
            (self.directory / "metrics/checks/expected-failure.json").read_text()
        )
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["status"], "failure")
        self.assertGreaterEqual(result["seconds"], 0)
        self.assertNotIn("command", result)

    def test_missing_command_is_failure(self):
        self.assertEqual(
            telemetry.run_check("missing", [str(self.directory / "missing")]), 127
        )

    def test_junit_uses_leaf_suites_and_discards_payloads(self):
        report = self.directory / "test.xml"
        report.write_text(
            """<testsuites tests="4"><testsuite tests="4" failures="1" errors="1" skipped="1">
          <testcase classname="suite" name="test_ok[synthetic-secret]" time="0.1"/>
          <testcase classname="suite" name="test_failed" time="2"><failure>secret failure</failure></testcase>
          <testcase name="test_error"><error>secret error</error></testcase>
          <testcase name="test_skip"><skipped/></testcase>
          <system-out>full synthetic transcript</system-out><properties><property value="secret"/></properties>
        </testsuite></testsuites>""",
            encoding="utf-8",
        )
        result = telemetry.junit_summary(report)
        self.assertEqual(
            (result["tests"], result["failures"], result["errors"], result["skipped"]),
            (4, 1, 1, 1),
        )
        self.assertEqual(result["slowest"][0]["seconds"], 2)
        serialized = json.dumps(result)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("transcript", serialized)

    def test_missing_report_does_not_change_original_exit_but_fails_summary(self):
        code = telemetry.run_check(
            "no-report", [sys.executable, "-c", "pass"], "pytest"
        )
        self.assertEqual(code, 0)
        self.assertEqual(telemetry.summarize(), 1)

    def test_missing_report_does_not_mask_failed_test_command(self):
        code = telemetry.run_check(
            "failed-test", [sys.executable, "-c", "raise SystemExit(5)"], "pytest"
        )
        self.assertEqual(code, 5)

    def test_unknown_cache_is_not_reported_as_miss(self):
        self.assertEqual(telemetry.cache_state(None), "unknown")
        self.assertEqual(telemetry.cache_state(""), "unknown")
        self.assertEqual(telemetry.cache_state("false"), "false")


if __name__ == "__main__":
    unittest.main()
