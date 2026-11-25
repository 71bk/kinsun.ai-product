"""Run one explicit daily schedule through Core; dry-run unless --execute is set."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import signal
import time
import uuid
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config/line/daily-family-report-notification-v1.json"
)
MAX_ATTEMPTS = 3
HTTP_TIMEOUT = 10
MAX_RESPONSE_BYTES = 1_048_576
MAX_RETRY_WAIT = 30
SERVICE_HEADER = "X-Kinsun-Service-Credential"
_COUNT_KEYS = {"eligible", "sent", "replayed", "skipped", "failed"}
_DATA_KEYS = {
    "schema_version",
    "job_name",
    "status",
    "scheduled_for",
    "timezone",
    "source_period",
    "counts",
    "deliveries",
}


class WorkerError(Exception):
    """Only fixed, non-sensitive reason codes may cross the CLI boundary."""


@dataclass(frozen=True)
class Job:
    name: str
    timezone: str
    path: str


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    retry_after: str | None = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_job(path: Path = CONFIG_PATH) -> Job:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
        schedule = config["schedule"]
        target = config["target"]
        template = target["request_template"]
        if (
            set(config) != {"schema_version", "job_name", "schedule", "target"}
            or config["schema_version"] != "1.0"
            or config["job_name"] != "line-daily-family-report"
            or schedule
            != {
                "timezone": "Asia/Taipei",
                "local_time": "08:00",
                "frequency": "DAILY",
                "source_period": "PREVIOUS_LOCAL_CALENDAR_DAY",
                "misfire_policy": "RETRY_SAME_SCHEDULED_FOR",
            }
            or set(target) != {"method", "path", "authentication", "request_template"}
            or target["method"] != "POST"
            or target["path"] != "/api/v1/internal/notification-jobs/line-daily"
            or target["authentication"] != "SYSTEM_SERVICE"
            or template
            != {
                "schema_version": "1.0",
                "job_name": config["job_name"],
                "scheduled_for": "${scheduled_time_with_offset}",
                "timezone": schedule["timezone"],
            }
        ):
            raise ValueError
        return Job(config["job_name"], schedule["timezone"], target["path"])
    except (OSError, KeyError, TypeError, ValueError):
        raise WorkerError("SCHEDULE_CONFIG_INVALID") from None


def parse_schedule(value: str, job: Job) -> datetime:
    try:
        scheduled = datetime.fromisoformat(value)
        if scheduled.tzinfo is None or scheduled.utcoffset() is None:
            raise ValueError
        local = scheduled.astimezone(ZoneInfo(job.timezone))
        if (local.hour, local.minute, local.second, local.microsecond) != (8, 0, 0, 0):
            raise ValueError
        return scheduled.astimezone(UTC)
    except ZoneInfoNotFoundError:
        raise WorkerError("TIMEZONE_DATA_UNAVAILABLE") from None
    except (TypeError, ValueError, OverflowError):
        raise WorkerError("SCHEDULE_TIME_INVALID") from None


def core_endpoint(origin: str, job: Job) -> str:
    try:
        if not origin or any(char.isspace() or ord(char) < 32 for char in origin):
            raise ValueError
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "?" in origin
            or "#" in origin
            or "\\" in origin
        ):
            raise ValueError
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
        if parsed.scheme == "http" and parsed.hostname != "localhost":
            if not ipaddress.ip_address(parsed.hostname).is_loopback:
                raise ValueError
        return origin.rstrip("/") + job.path
    except ValueError:
        raise WorkerError("CORE_ORIGIN_INVALID") from None


def validate_identity(secret: str, issuer: str) -> None:
    if len(secret.encode("utf-8")) < 32:
        raise WorkerError("WORKER_IDENTITY_REQUIRED")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", issuer):
        raise WorkerError("WORKER_ISSUER_INVALID")


def sign_request(
    secret: str, issuer: str, path: str, body: bytes, correlation: str, now: datetime
) -> str:
    # Same ksvc1 wire contract as Core/Speech; never import Core settings or secrets.
    claims = {
        "aud": "core-api",
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "correlation_id": correlation,
        "exp": int(now.timestamp()) + 30,
        "iat": int(now.timestamp()),
        "iss": issuer,
        "jti": str(uuid.uuid4()),
        "method": "POST",
        "path": path,
        "sub": "notification-worker",
        "v": 1,
    }
    encoded = (
        base64.urlsafe_b64encode(
            json.dumps(claims, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        )
        .rstrip(b"=")
        .decode("ascii")
    )
    message = f"ksvc1.{encoded}".encode("ascii")
    signature = (
        base64.urlsafe_b64encode(hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return f"{message.decode('ascii')}.{signature}"


def post(url: str, payload: bytes, headers: Mapping[str, str]) -> HttpResponse:
    request = Request(url, data=payload, headers=dict(headers), method="POST")
    try:
        response = build_opener(NoRedirect()).open(request, timeout=HTTP_TIMEOUT)
    except HTTPError as error:
        # Never read or retain rejection bodies, URLs, cookies, or provider text.
        with error:
            return HttpResponse(error.code, b"", error.headers.get("Retry-After"))
    with response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise WorkerError("CORE_RESPONSE_INVALID")
        return HttpResponse(response.status, body, response.headers.get("Retry-After"))


def read_result(body: bytes, scheduled: datetime, job: Job) -> tuple[str, dict]:
    try:
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError
        envelope = json.loads(body)
        if set(envelope) != {"data", "meta"} or not isinstance(envelope["meta"], dict):
            raise ValueError
        data = envelope["data"]
        counts = data["counts"]
        deliveries = data["deliveries"]
        source_date = scheduled.astimezone(ZoneInfo(job.timezone)).date() - timedelta(days=1)
        status = data["status"]
        if (
            set(data) != _DATA_KEYS
            or data["schema_version"] != "1.0"
            or data["job_name"] != job.name
            or data["timezone"] != job.timezone
            or parse_schedule(data["scheduled_for"], job) != scheduled
            or data["source_period"]
            != {"start": source_date.isoformat(), "end": source_date.isoformat()}
            or set(counts) != _COUNT_KEYS
            or any(type(value) is not int or not 0 <= value <= 500 for value in counts.values())
            or sum(counts[key] for key in _COUNT_KEYS - {"eligible"}) != counts["eligible"]
            or not isinstance(deliveries, list)
            or len(deliveries) != counts["eligible"]
            or status not in {"COMPLETED", "PARTIAL_FAILURE", "NO_ELIGIBLE_REPORTS"}
            or (status == "NO_ELIGIBLE_REPORTS") != (counts["eligible"] == 0)
            or (status == "PARTIAL_FAILURE") != (counts["failed"] > 0)
        ):
            raise ValueError
        actual = Counter()
        for delivery in deliveries:
            if (
                set(delivery)
                != {"notification_id", "report_id", "report_version", "status", "reason_code"}
                or delivery["status"] not in {"SENT", "REPLAYED", "SKIPPED", "FAILED"}
                or type(delivery["report_version"]) is not int
                or delivery["report_version"] < 1
                or (
                    delivery["reason_code"] is not None
                    and (
                        not isinstance(delivery["reason_code"], str)
                        or len(delivery["reason_code"]) > 80
                    )
                )
            ):
                raise ValueError
            uuid.UUID(delivery["notification_id"])
            uuid.UUID(delivery["report_id"])
            actual[delivery["status"].lower()] += 1
        if any(actual[key] != counts[key] for key in _COUNT_KEYS - {"eligible"}):
            raise ValueError
        return status, {key: counts[key] for key in sorted(_COUNT_KEYS)}
    except (KeyError, TypeError, ValueError, AttributeError, WorkerError, OverflowError):
        raise WorkerError("CORE_RESPONSE_INVALID") from None


def retry_wait(value: str | None, attempt: int, now: datetime) -> float:
    wait = float(2 ** (attempt - 1))
    if value is not None:
        try:
            if value.isdecimal():
                delay = float(value)
            else:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    raise ValueError
                delay = (retry_at.astimezone(UTC) - now).total_seconds()
            wait = max(wait, delay)
        except (TypeError, ValueError, OverflowError):
            pass
    return wait


def run_job(
    scheduled_for: str,
    *,
    execute: bool = False,
    environment: Mapping[str, str] | None = None,
    transport: Callable = post,
    sleep: Callable = time.sleep,
    clock: Callable = lambda: datetime.now(UTC),
    job: Job | None = None,
) -> tuple[int, dict]:
    job = job or load_job()
    scheduled = parse_schedule(scheduled_for, job)
    payload = {
        "schema_version": "1.0",
        "job_name": job.name,
        "scheduled_for": scheduled.isoformat(),
        "timezone": job.timezone,
    }
    summary = {
        "schema_version": "1.0",
        "job_name": job.name,
        "scheduled_for": payload["scheduled_for"],
        "timezone": job.timezone,
        "correlation_id": str(uuid.uuid4()),
        "outcome": "DRY_RUN",
        "attempts": 0,
        "reason_code": None,
        "retryable": False,
        "counts": None,
    }
    if not execute:
        return 0, summary
    if scheduled > clock():
        raise WorkerError("SCHEDULE_NOT_DUE")
    environment = os.environ if environment is None else environment
    endpoint = core_endpoint(environment.get("NOTIFICATION_CORE_URL", ""), job)
    secret = environment.get("NOTIFICATION_WORKER_HMAC_SECRET", "")
    issuer = environment.get("NOTIFICATION_WORKER_ISSUER", "kinsun-local")
    validate_identity(secret, issuer)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Correlation-ID": summary["correlation_id"],
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    summary["outcome"] = "ERROR"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        summary["attempts"] = attempt
        # Credentials are single-use and short-lived. Keep the logical job unchanged,
        # but issue a fresh nonce/signature for each retry, including a deferred retry.
        headers[SERVICE_HEADER] = sign_request(
            secret, issuer, job.path, body, summary["correlation_id"], clock()
        )
        retry_after = None
        try:
            response = transport(endpoint, body, headers)
            if 200 <= response.status < 300:
                outcome, counts = read_result(response.body, scheduled, job)
                summary.update(outcome=outcome, counts=counts, reason_code=None, retryable=False)
                if outcome == "PARTIAL_FAILURE":
                    summary.update(reason_code="DELIVERY_PARTIAL_FAILURE")
                    return 2, summary
                return 0, summary
            retry_after = response.retry_after
            retryable = response.status in {408, 429} or 500 <= response.status <= 599
            reason = "CORE_HTTP_TRANSIENT" if retryable else "CORE_HTTP_REJECTED"
        except (URLError, OSError, HTTPException):
            reason, retryable = "CORE_NETWORK_UNAVAILABLE", True
        except WorkerError:
            summary.update(reason_code="CORE_RESPONSE_INVALID")
            return 1, summary
        summary.update(reason_code=reason, retryable=retryable)
        if not retryable or attempt == MAX_ATTEMPTS:
            return 1, summary
        wait = retry_wait(retry_after, attempt, clock())
        if not math.isfinite(wait) or wait > MAX_RETRY_WAIT:
            summary["reason_code"] = "RETRY_DEFERRED"
            return 1, summary
        sleep(wait)
    raise AssertionError("unreachable")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise WorkerError("ARGUMENTS_INVALID")


def main(argv: list[str] | None = None) -> int:
    summary = {
        "schema_version": "1.0",
        "job_name": None,
        "scheduled_for": None,
        "timezone": None,
        "correlation_id": str(uuid.uuid4()),
        "outcome": "ERROR",
        "attempts": None,
        "reason_code": None,
        "retryable": False,
        "counts": None,
    }
    try:
        parser = Parser(description=__doc__)
        parser.add_argument(
            "--scheduled-for", required=True, help="Original ISO 8601 schedule with offset"
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument(
            "--execute", action="store_true", help="Call Core using injected environment"
        )
        mode.add_argument("--dry-run", action="store_true", help="Validate only (the default)")
        args = parser.parse_args(argv)
        code, summary = run_job(args.scheduled_for, execute=args.execute)
    except WorkerError as error:
        code = 64
        summary.update(reason_code=str(error))
    except KeyboardInterrupt:
        code = 130
        summary.update(outcome="INTERRUPTED", reason_code="WORKER_STOPPED")
    except Exception:
        code = 1
        summary.update(reason_code="WORKER_FAILED")
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")), flush=True)
    return code


def _stop(signum, frame):
    raise KeyboardInterrupt


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    raise SystemExit(main())
