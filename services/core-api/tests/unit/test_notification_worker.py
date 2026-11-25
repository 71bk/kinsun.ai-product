"""Exercise the standalone scheduler client without DB or external providers."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from email.utils import format_datetime
from http.client import RemoteDisconnected
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from uuid import UUID

import pytest

from app.adapters.service_identity import ServiceCredentialVerifier
from app.adapters.service_identity_replay import InMemoryReplayStore
from app.core.exceptions import AuthenticationError
from app.schemas.notification import DailyLineNotificationJobRequest

WORKER_PATH = Path(__file__).resolve().parents[4] / "services/notification-worker/run_daily.py"
_spec = importlib.util.spec_from_file_location("kinsun_daily_worker_test", WORKER_PATH)
assert _spec is not None and _spec.loader is not None
worker = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = worker
_spec.loader.exec_module(worker)

SCHEDULE = "2026-10-15T08:00:00+08:00"
UTC_SCHEDULE = "2026-10-15T00:00:00+00:00"
NOW = datetime(2026, 10, 15, 1, tzinfo=UTC)
TOKEN = "synthetic-notification-worker-secret-at-least-32-bytes"
ENV = {
    "NOTIFICATION_CORE_URL": "https://core.example.test",
    "NOTIFICATION_WORKER_HMAC_SECRET": TOKEN,
}
REPORT_ID = "30000000-0000-4000-8000-000000000001"
NOTIFICATION_ID = "30000000-0000-4000-8000-000000000002"


def result(status="COMPLETED", delivery_status="SENT"):
    deliveries = (
        []
        if status == "NO_ELIGIBLE_REPORTS"
        else [
            {
                "notification_id": NOTIFICATION_ID,
                "report_id": REPORT_ID,
                "report_version": 1,
                "status": delivery_status,
                "reason_code": None,
            }
        ]
    )
    counts = {key: 0 for key in ("eligible", "sent", "replayed", "failed", "skipped")}
    counts["eligible"] = len(deliveries)
    if deliveries:
        counts[delivery_status.lower()] = 1
    return {
        "data": {
            "schema_version": "1.0",
            "job_name": "line-daily-family-report",
            "status": status,
            "scheduled_for": UTC_SCHEDULE,
            "timezone": "Asia/Taipei",
            "source_period": {"start": "2026-10-14", "end": "2026-10-14"},
            "counts": counts,
            "deliveries": deliveries,
        },
        "meta": {
            "schema_version": "1.0",
            "correlation_id": "synthetic",
            "timestamp": NOW.isoformat(),
        },
    }


def response(body=None, status=200, retry_after=None):
    return worker.HttpResponse(status, json.dumps(body or result()).encode(), retry_after)


def invoke(responses, **kwargs):
    calls, sleeps = [], []

    def transport(url, body, headers):
        calls.append({"url": url, "body": body, "headers": dict(headers)})
        value = responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    code, summary = worker.run_job(
        SCHEDULE,
        execute=True,
        environment=ENV,
        transport=transport,
        sleep=sleeps.append,
        clock=lambda: NOW,
        **kwargs,
    )
    return code, summary, calls, sleeps


def test_dry_run_has_no_environment_or_network_access():
    class ForbiddenEnvironment(dict):
        def get(self, *args):
            pytest.fail("dry-run read credentials")

    code, summary = worker.run_job(
        SCHEDULE,
        environment=ForbiddenEnvironment(),
        transport=lambda *args: pytest.fail("dry-run made a request"),
    )
    assert code == 0 and summary["outcome"] == "DRY_RUN" and summary["attempts"] == 0
    assert summary["scheduled_for"] == UTC_SCHEDULE
    UUID(summary["correlation_id"])


@pytest.mark.asyncio
async def test_worker_signature_interoperates_with_core_and_each_retry_has_fresh_nonce():
    _, summary, calls, _ = invoke([response(status=503), response()])
    verifier = ServiceCredentialVerifier(
        secret=TOKEN,
        issuer="kinsun-local",
        expected_subject="notification-worker",
        audience="core-api",
        replay_store=InMemoryReplayStore(),
        max_ttl_seconds=30,
    )
    for call in calls:
        await verifier.verify(
            call["headers"][worker.SERVICE_HEADER],
            method="POST",
            path=worker.load_job().path,
            body=call["body"],
            correlation_id=summary["correlation_id"],
            now=int(NOW.timestamp()),
        )
    with pytest.raises(AuthenticationError):
        await verifier.verify(
            calls[0]["headers"][worker.SERVICE_HEADER],
            method="POST",
            path=worker.load_job().path,
            body=calls[0]["body"],
            correlation_id=summary["correlation_id"],
            now=int(NOW.timestamp()),
        )


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-15T08:00:00",
        "2026-10-15T08:01:00+08:00",
        "2026-10-15T08:00:01+08:00",
        "2026-10-15T08:00:00.1+08:00",
        "private-invalid-value",
    ],
)
def test_schedule_rejects_naive_or_non_exact_time(value):
    with pytest.raises(worker.WorkerError, match="^SCHEDULE_TIME_INVALID$"):
        worker.run_job(value)


def test_equivalent_utc_input_and_source_config_are_accepted_by_core_schema():
    _, summary, calls, _ = invoke([response()])
    body = json.loads(calls[0]["body"])
    request = DailyLineNotificationJobRequest.model_validate(body)
    assert set(body) == {"schema_version", "job_name", "scheduled_for", "timezone"}
    assert request.scheduled_for == datetime(2026, 10, 15, tzinfo=UTC)
    assert worker.parse_schedule("2026-10-15T00:00:00Z", worker.load_job()) == request.scheduled_for
    assert "Authorization" not in calls[0]["headers"]
    assert calls[0]["headers"][worker.SERVICE_HEADER].startswith("ksvc1.")
    assert calls[0]["headers"]["X-Correlation-ID"] == summary["correlation_id"]
    assert calls[0]["url"].endswith("/api/v1/internal/notification-jobs/line-daily")
    assert TOKEN not in json.dumps(summary) and REPORT_ID not in json.dumps(summary)


def test_future_execution_is_blocked_before_credentials_or_transport():
    with pytest.raises(worker.WorkerError, match="^SCHEDULE_NOT_DUE$"):
        worker.run_job(
            SCHEDULE, execute=True, environment={}, clock=lambda: datetime(2026, 10, 14, tzinfo=UTC)
        )


@pytest.mark.parametrize(
    "origin",
    [
        "http://core.example.test",
        "http://localhost.example.test",
        "http://192.168.1.1",
        "https://user:private@core.example.test",
        "https://core.example.test/path",
        "https://core.example.test?token=private",
        "https://core.example.test#private",
        "https://core.example.test?",
        "https://core.example.test#",
        "https://core.example.test:0",
        "https://core.example.test:99999",
        " https://core.example.test",
        "https://core.example.test\\path",
        "file:///private",
        "https://core.example.test\nAuthorization:private",
        "",
    ],
)
def test_unsafe_core_origin_is_rejected(origin):
    with pytest.raises(worker.WorkerError, match="^CORE_ORIGIN_INVALID$"):
        worker.core_endpoint(origin, worker.load_job())


@pytest.mark.parametrize(
    "origin",
    [
        "https://core.example.test",
        "http://127.0.0.1:8110/",
        "http://[::1]:8110",
        "http://localhost:8110",
    ],
)
def test_trusted_https_and_literal_loopback_origins(origin):
    assert worker.core_endpoint(origin, worker.load_job()).startswith(origin.rstrip("/"))


@pytest.mark.parametrize(
    "token",
    ["", "short", "ks1_private", "ep1_private", "es1_private"],
)
def test_invalid_credentials_fail_before_network(token):
    with pytest.raises(worker.WorkerError, match="^WORKER_IDENTITY_REQUIRED$"):
        worker.run_job(
            SCHEDULE,
            execute=True,
            clock=lambda: NOW,
            environment={**ENV, "NOTIFICATION_WORKER_HMAC_SECRET": token},
            transport=lambda *args: pytest.fail("invalid credential sent"),
        )


@pytest.mark.parametrize(
    "failure",
    [
        URLError("private-target"),
        TimeoutError("private-target"),
        RemoteDisconnected("private-target"),
        worker.HttpResponse(503, b"private-provider-body"),
        worker.HttpResponse(429, b"private"),
        worker.HttpResponse(408, b"private"),
    ],
)
def test_transient_retry_keeps_original_payload_and_correlation_then_clears_error(failure):
    code, summary, calls, sleeps = invoke([failure, response()])
    assert code == 0 and summary["outcome"] == "COMPLETED"
    assert summary["reason_code"] is None and summary["retryable"] is False
    assert summary["attempts"] == 2 and sleeps == [1]
    assert calls[0]["body"] == calls[1]["body"]
    assert calls[0]["headers"]["X-Correlation-ID"] == calls[1]["headers"]["X-Correlation-ID"]
    assert calls[0]["headers"][worker.SERVICE_HEADER] != calls[1]["headers"][worker.SERVICE_HEADER]


def test_network_retry_is_bounded_without_leaking_exception():
    code, summary, calls, sleeps = invoke([TimeoutError("private-secret")] * 3)
    assert code == 1 and len(calls) == 3 and sleeps == [1, 2]
    assert summary["reason_code"] == "CORE_NETWORK_UNAVAILABLE" and summary["retryable"]
    assert "private" not in json.dumps(summary)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 400, 401, 403, 404, 422])
def test_redirect_and_permanent_errors_are_not_retried(status):
    code, summary, calls, sleeps = invoke([worker.HttpResponse(status, b"private-body")])
    assert code == 1 and len(calls) == 1 and sleeps == []
    assert summary["reason_code"] == "CORE_HTTP_REJECTED" and not summary["retryable"]


def test_retry_after_is_honored_and_long_retry_is_deferred():
    code, _, _, sleeps = invoke([response(status=429, retry_after="5"), response()])
    assert code == 0 and sleeps == [5]
    code, summary, calls, sleeps = invoke([response(status=503, retry_after="3600")])
    assert code == 1 and len(calls) == 1 and sleeps == []
    assert summary["reason_code"] == "RETRY_DEFERRED" and summary["retryable"]
    retry_date = format_datetime(NOW.replace(second=7), usegmt=True)
    assert worker.retry_wait(retry_date, 1, NOW) == 7
    assert worker.retry_wait("invalid", 2, NOW) == 2
    assert worker.retry_wait("9" * 5000, 1, NOW) == float("inf")


@pytest.mark.parametrize(
    ("status", "delivery_status", "code"),
    [
        ("COMPLETED", "SENT", 0),
        ("COMPLETED", "REPLAYED", 0),
        ("COMPLETED", "SKIPPED", 0),
        ("NO_ELIGIBLE_REPORTS", "SENT", 0),
        ("PARTIAL_FAILURE", "FAILED", 2),
    ],
)
def test_core_status_controls_exit_and_partial_failure_is_not_immediately_retried(
    status, delivery_status, code
):
    actual_code, summary, calls, sleeps = invoke([response(result(status, delivery_status))])
    assert actual_code == code and summary["outcome"] == status
    assert len(calls) == 1 and sleeps == []
    if code == 2:
        assert summary["reason_code"] == "DELIVERY_PARTIAL_FAILURE"
        assert not summary["retryable"]  # delivery-level investigation, not HTTP retry


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("schema_version",), "2.0"),
        (("job_name",), "other"),
        (("timezone",), "UTC"),
        (("scheduled_for",), "2026-10-14T00:00:00Z"),
        (("scheduled_for",), "private"),
        (("source_period", "start"), "2026-10-13"),
        (("counts", "eligible"), True),
        (("counts", "eligible"), 501),
        (("counts", "sent"), 0),
        (("status",), "PARTIAL_FAILURE"),
        (("status",), "NO_ELIGIBLE_REPORTS"),
        (("deliveries",), []),
        (("deliveries", 0, "status"), "REPLAYED"),
        (("deliveries", 0, "report_id"), "private"),
        (("deliveries", 0, "notification_id"), None),
        (("deliveries", 0, "report_version"), True),
        (("deliveries", 0, "reason_code"), "x" * 81),
        (("private_field",), "private"),
    ],
)
def test_malformed_success_is_nonzero_without_raw_body(path, value):
    body = copy.deepcopy(result())
    target = body["data"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    code, summary, calls, sleeps = invoke([response(body)])
    assert code == 1 and len(calls) == 1 and sleeps == []
    assert summary["reason_code"] == "CORE_RESPONSE_INVALID"
    assert "private" not in json.dumps(summary)


@pytest.mark.parametrize(
    "body",
    [
        b"not-json-private",
        b"null",
        b"[]",
        b"{}",
        b"{" * 1000,
        b"a" * (worker.MAX_RESPONSE_BYTES + 1),
    ],
    ids=["not-json", "null", "array", "empty", "broken-json", "oversized"],
)
def test_invalid_or_oversized_success_body_fails_closed(body):
    code, summary, _, _ = invoke([worker.HttpResponse(200, body)])
    assert code == 1 and summary["reason_code"] == "CORE_RESPONSE_INVALID"


def test_config_drift_or_missing_file_is_rejected(tmp_path):
    config = json.loads(worker.CONFIG_PATH.read_text(encoding="utf-8"))
    config["target"]["path"] = "/some-other-operation"
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(worker.WorkerError, match="^SCHEDULE_CONFIG_INVALID$"):
        worker.load_job(path)
    with pytest.raises(worker.WorkerError, match="^SCHEDULE_CONFIG_INVALID$"):
        worker.load_job(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "args", [[], ["--scheduled-for", "private-invalid"], ["--unknown", "private-credential"]]
)
def test_cli_errors_do_not_echo_arguments(args, capsys):
    assert worker.main(args) == 64
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
    assert json.loads(output.out)["outcome"] == "ERROR"


def test_interruption_stops_before_retry(monkeypatch, capsys):
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "run_job", interrupted)
    assert worker.main(["--scheduled-for", SCHEDULE, "--execute"]) == 130
    assert json.loads(capsys.readouterr().out)["outcome"] == "INTERRUPTED"
    with pytest.raises(KeyboardInterrupt):
        invoke([KeyboardInterrupt(), response()])


def test_cli_default_and_explicit_dry_run_work_from_another_directory(tmp_path):
    for mode in ([], ["--dry-run"]):
        completed = subprocess.run(
            [sys.executable, str(WORKER_PATH), "--scheduled-for", SCHEDULE, *mode],
            cwd=tmp_path,
            env={**os.environ, **ENV},
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert completed.returncode == 0 and completed.stderr == ""
        summary = json.loads(completed.stdout)
        assert summary["outcome"] == "DRY_RUN" and summary["attempts"] == 0
        assert TOKEN not in completed.stdout


@pytest.fixture
def http_core():
    calls, replies = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "credential": self.headers.get(worker.SERVICE_HEADER),
                    "correlation": self.headers.get("X-Correlation-ID"),
                    "body": self.rfile.read(int(self.headers["Content-Length"])),
                }
            )
            status, headers, body = replies.pop(0)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append({"method": "GET", "path": self.path})
            self.send_response(500)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls, replies
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_http_retry_and_minimal_summary(http_core):
    origin, calls, replies = http_core
    replies.extend([(503, {}, b"private-error"), (200, {}, json.dumps(result()).encode())])
    code, summary = worker.run_job(
        SCHEDULE,
        execute=True,
        environment={**ENV, "NOTIFICATION_CORE_URL": origin},
        sleep=lambda value: None,
        clock=lambda: NOW,
    )
    assert code == 0 and summary["attempts"] == 2 and len(calls) == 2
    assert calls[0]["body"] == calls[1]["body"]
    assert calls[0]["credential"] != calls[1]["credential"]
    assert calls[0]["authorization"] is None
    assert calls[0]["correlation"] == summary["correlation_id"]
    assert REPORT_ID not in json.dumps(summary) and TOKEN not in json.dumps(summary)


def test_real_http_redirect_never_receives_a_second_request(http_core):
    origin, calls, replies = http_core
    replies.extend([(302, {"Location": origin + "/credential-trap"}, b"private")])
    code, summary = worker.run_job(
        SCHEDULE,
        execute=True,
        environment={**ENV, "NOTIFICATION_CORE_URL": origin},
        sleep=lambda value: pytest.fail("redirect retry"),
        clock=lambda: NOW,
    )
    assert code == 1 and len(calls) == 1
    assert summary["reason_code"] == "CORE_HTTP_REJECTED"


def test_real_cli_execute_against_synthetic_core(http_core):
    origin, calls, replies = http_core
    body = result("PARTIAL_FAILURE", "FAILED")
    body["data"]["scheduled_for"] = "2000-01-02T00:00:00+00:00"
    body["data"]["source_period"] = {"start": "2000-01-01", "end": "2000-01-01"}
    replies.extend([(200, {}, json.dumps(body).encode())])
    completed = subprocess.run(
        [sys.executable, str(WORKER_PATH), "--scheduled-for", "2000-01-02T00:00:00Z", "--execute"],
        env={**os.environ, **ENV, "NOTIFICATION_CORE_URL": origin},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 2 and completed.stderr == "" and len(calls) == 1
    assert json.loads(completed.stdout)["outcome"] == "PARTIAL_FAILURE"
    assert TOKEN not in completed.stdout + completed.stderr
