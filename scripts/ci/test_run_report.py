import unittest

from run_report import build_report


class NativeTimingTests(unittest.TestCase):
    def test_parallel_wall_time_is_not_sum_of_runner_times(self):
        run = dict(
            id=1,
            run_attempt=2,
            head_sha="synthetic",
            event="pull_request",
            status="completed",
            conclusion="success",
            html_url="synthetic",
            run_started_at="2026-09-07T00:00:00Z",
        )
        jobs = [
            dict(
                name=name,
                status="completed",
                conclusion="success",
                started_at="2026-09-07T00:00:10Z",
                completed_at=end,
                steps=[],
            )
            for name, end in [
                ("first", "2026-09-07T00:01:10Z"),
                ("second", "2026-09-07T00:02:10Z"),
            ]
        ]
        report = build_report(run, jobs)
        self.assertEqual(report["wall_seconds"], 120)
        self.assertEqual(report["runner_seconds"], 180)
        self.assertEqual(report["initial_dispatch_seconds"], 10)
        jobs[1].update(status="in_progress", completed_at=None)
        pending = build_report(run, jobs)
        self.assertIsNone(pending["wall_seconds"])
        self.assertIsNone(pending["runner_seconds"])
        self.assertFalse(pending["complete"])


if __name__ == "__main__":
    unittest.main()
