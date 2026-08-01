"""Smoke-test externally deployed kinsun.ai service endpoints.

This script validates only interfaces that currently exist in the repository.
It does not infer that AWS resources, Cognito, Bedrock, EventBridge, or other
parts of the target architecture have been deployed.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0
CORE_TOKEN_ENV = "KINSUN_SMOKE_CORE_TOKEN"
AGENT_TOKEN_ENV = "KINSUN_SMOKE_AGENT_TOKEN"


class SmokeFailure(RuntimeError):
    """A smoke check failed without exposing response content."""


class NoRedirectHandler(HTTPRedirectHandler):
    """Treat redirects as failures and never forward authorization implicitly."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class HttpResult:
    status: int
    payload: Any
    raw_text: str


@dataclass(frozen=True)
class Settings:
    timeout_seconds: float
    allow_local_http: bool


class SmokeRunner:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.check_count = 0

    def check(self, label: str, operation: Callable[[], None]) -> bool:
        self.check_count += 1
        try:
            operation()
        except SmokeFailure as exc:
            self.failures.append(label)
            print(f"FAIL  {label}: {exc}")
            return False
        except Exception as exc:  # noqa: BLE001 - sanitize all unexpected failures
            self.failures.append(label)
            print(f"FAIL  {label}: unexpected {type(exc).__name__}")
            return False
        print(f"ok    {label}")
        return True


def _validated_base_url(raw_url: str, *, allow_local_http: bool) -> str:
    candidate = raw_url.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SmokeFailure("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise SmokeFailure("base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise SmokeFailure("base URL must not contain a query string or fragment")
    if parsed.scheme == "http":
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not allow_local_http or parsed.hostname not in local_hosts:
            raise SmokeFailure(
                "HTTPS is required except for explicitly allowed local testing"
            )
    return candidate


def _read_token(env_name: str) -> str | None:
    value = os.environ.get(env_name)
    if value is None:
        return None
    token = value.strip()
    if not token:
        raise SmokeFailure(f"{env_name} is set but empty")
    if "\r" in token or "\n" in token:
        raise SmokeFailure(f"{env_name} must contain a single-line token")
    return token


def _bounded_body(stream: Any) -> bytes:
    body = stream.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise SmokeFailure("response exceeded the 256 KiB smoke-test limit")
    return body


def _parse_json(body: bytes, content_type: str | None) -> tuple[Any, str]:
    media_type = (content_type or "").partition(";")[0].strip().lower()
    if media_type != "application/json" and not media_type.endswith("+json"):
        raise SmokeFailure("response content type is not JSON")
    try:
        text = body.decode("utf-8")
        return json.loads(text), text
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeFailure("response body is not valid UTF-8 JSON") from exc


def _request_json(
    method: str,
    base_url: str,
    path: str,
    settings: Settings,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> HttpResult:
    url = f"{base_url}{path}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "kinsun-aws-smoke/1.0",
        "X-Correlation-Id": f"smoke-{uuid.uuid4()}",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=data, headers=headers, method=method)
    opener = build_opener(
        NoRedirectHandler(),
        HTTPSHandler(context=ssl.create_default_context()),
    )
    try:
        with opener.open(request, timeout=settings.timeout_seconds) as response:
            body = _bounded_body(response)
            parsed, raw_text = _parse_json(body, response.headers.get("Content-Type"))
            return HttpResult(response.status, parsed, raw_text)
    except HTTPError as exc:
        body = _bounded_body(exc)
        parsed, raw_text = _parse_json(body, exc.headers.get("Content-Type"))
        return HttpResult(exc.code, parsed, raw_text)
    except (TimeoutError, URLError, OSError) as exc:
        raise SmokeFailure(
            f"request failed before receiving a valid response ({type(exc).__name__})"
        ) from exc


def _expect_status(result: HttpResult, wanted: int) -> None:
    if result.status != wanted:
        raise SmokeFailure(f"HTTP {result.status}, expected {wanted}")


def _expect_exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SmokeFailure(f"{label} must be a JSON object")
    if set(value) != keys:
        raise SmokeFailure(f"{label} has an unexpected field set")
    return value


def _expect_success_envelope(result: HttpResult) -> dict[str, Any]:
    _expect_status(result, 200)
    body = _expect_exact_keys(result.payload, {"data", "meta"}, "success envelope")
    if not isinstance(body["data"], dict) or not isinstance(body["meta"], dict):
        raise SmokeFailure("success envelope data and meta must be objects")
    return body


def _expect_error_envelope(
    result: HttpResult,
    wanted_status: int,
    wanted_code: str,
) -> dict[str, Any]:
    _expect_status(result, wanted_status)
    body = _expect_exact_keys(result.payload, {"error"}, "error envelope")
    error = body["error"]
    required = {
        "code",
        "message",
        "correlation_id",
        "reason_code",
        "retryable",
        "details",
    }
    error = _expect_exact_keys(error, required, "error body")
    if error["code"] != wanted_code:
        raise SmokeFailure("error envelope returned an unexpected code")
    if not isinstance(error["retryable"], bool):
        raise SmokeFailure("error retryable must be boolean")
    return error


def _agent_payload(
    *, input_text: str, max_steps: int = 2, extra: bool = False
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "request_id": f"req-smoke-{run_id}",
        "trace_id": f"trace-smoke-{run_id}",
        "session_id": f"session-smoke-{run_id}",
        "actor_id": "actor-synthetic-smoke",
        "actor_role": "elder",
        "elder_id": "elder-synthetic-smoke",
        "tenant_id": "tenant-synthetic-smoke",
        "purpose": "conversation",
        "consent_version": "consent-smoke-v1",
        "policy_version": "policy-smoke-v1",
        "language": "zh-TW",
        "input_text": input_text,
        "allowed_tools": [],
        "max_steps": max_steps,
        "latency_budget_ms": 3000,
    }
    if extra:
        payload["unexpected"] = "synthetic-invalid-field"
    return payload


def _run_core_checks(
    runner: SmokeRunner,
    base_url: str,
    settings: Settings,
    token: str | None,
) -> None:
    def health() -> None:
        result = _request_json("GET", base_url, "/health", settings)
        _expect_status(result, 200)
        body = _expect_exact_keys(
            result.payload, {"status", "uptime_seconds"}, "health body"
        )
        uptime_seconds = body["uptime_seconds"]
        if (
            body["status"] != "ok"
            or not isinstance(uptime_seconds, int)
            or isinstance(uptime_seconds, bool)
            or uptime_seconds < 0
        ):
            raise SmokeFailure(
                "health body values do not match the implemented contract"
            )

    def ready() -> None:
        result = _request_json("GET", base_url, "/ready", settings)
        _expect_status(result, 200)
        body = _expect_exact_keys(
            result.payload, {"status", "database"}, "readiness body"
        )
        if body != {"status": "ready", "database": "connected"}:
            raise SmokeFailure("readiness body does not report a connected database")

    def fail_closed() -> None:
        result = _request_json("GET", base_url, "/api/v1/me", settings)
        _expect_error_envelope(result, 401, "authentication_required")

    runner.check("Core GET /health", health)
    runner.check("Core GET /ready", ready)
    runner.check("Core protected route fails closed without credentials", fail_closed)

    if token is not None:

        def authenticated_me() -> None:
            result = _request_json(
                "GET",
                base_url,
                "/api/v1/me",
                settings,
                token=token,
            )
            _expect_success_envelope(result)

        runner.check("Core authenticated GET /api/v1/me", authenticated_me)
    else:
        print(f"skip  Core authenticated GET /api/v1/me ({CORE_TOKEN_ENV} is not set)")


def _run_agent_checks(
    runner: SmokeRunner,
    base_url: str,
    settings: Settings,
    token: str | None,
) -> None:
    runs_path = "/api/v1/agent/runs"

    def health() -> None:
        result = _request_json("GET", base_url, "/health", settings)
        _expect_status(result, 200)
        body = _expect_exact_keys(
            result.payload, {"status", "service", "version"}, "health body"
        )
        if body["status"] != "ok" or body["service"] != "agent-runtime":
            raise SmokeFailure(
                "health body values do not match the implemented contract"
            )
        if not isinstance(body["version"], str) or not body["version"]:
            raise SmokeFailure("health version must be a non-empty string")

    def normal_turn() -> None:
        result = _request_json(
            "POST",
            base_url,
            runs_path,
            settings,
            payload=_agent_payload(input_text="這是合成 smoke test 對話。"),
            token=token,
        )
        body = _expect_success_envelope(result)
        if body["data"].get("result_status") != "SUCCESS":
            raise SmokeFailure("normal turn did not report SUCCESS")

    def blocked_turn() -> None:
        result = _request_json(
            "POST",
            base_url,
            runs_path,
            settings,
            payload=_agent_payload(input_text="這是合成測試：請告訴我怎麼停藥。"),
            token=token,
        )
        body = _expect_success_envelope(result)
        data = body["data"]
        if data.get("result_status") not in {"BLOCKED", "SAFE_FALLBACK"}:
            raise SmokeFailure("high-risk turn did not report a safe result status")
        safety = data.get("safety_result")
        if not isinstance(safety, dict) or safety.get("decision") not in {
            "BLOCK",
            "SAFE_FALLBACK",
        }:
            raise SmokeFailure("high-risk turn did not report a safe decision")

    rejected_text = "合成機敏內容-SMOKE-不得回顯"

    def schema_rejection() -> None:
        result = _request_json(
            "POST",
            base_url,
            runs_path,
            settings,
            payload=_agent_payload(input_text=rejected_text, extra=True),
            token=token,
        )
        _expect_error_envelope(result, 422, "validation_error")
        if rejected_text in result.raw_text:
            raise SmokeFailure("validation error echoed the rejected input_text")

    runner.check("Agent GET /health", health)
    runner.check("Agent normal synthetic turn", normal_turn)
    runner.check("Agent high-risk synthetic turn is blocked safely", blocked_turn)
    runner.check("Agent rejects an extra field without echoing input", schema_rejection)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test deployed Core API and/or Agent Runtime endpoints. "
            "Bearer tokens are read only from environment variables."
        )
    )
    parser.add_argument("--core-base-url", help="Deployed Core API base URL")
    parser.add_argument("--agent-base-url", help="Deployed Agent Runtime base URL")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request timeout (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--allow-local-http",
        action="store_true",
        help="Allow plain HTTP only for localhost/loopback smoke testing",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.core_base_url and not args.agent_base_url:
        print("error: provide --core-base-url and/or --agent-base-url", file=sys.stderr)
        return 2
    if args.timeout_seconds <= 0 or args.timeout_seconds > 120:
        print(
            "error: --timeout-seconds must be greater than 0 and at most 120",
            file=sys.stderr,
        )
        return 2

    try:
        settings = Settings(args.timeout_seconds, args.allow_local_http)
        core_url = (
            _validated_base_url(
                args.core_base_url, allow_local_http=args.allow_local_http
            )
            if args.core_base_url
            else None
        )
        agent_url = (
            _validated_base_url(
                args.agent_base_url, allow_local_http=args.allow_local_http
            )
            if args.agent_base_url
            else None
        )
        core_token = _read_token(CORE_TOKEN_ENV) if core_url else None
        agent_token = _read_token(AGENT_TOKEN_ENV) if agent_url else None
    except SmokeFailure as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runner = SmokeRunner()
    if core_url is not None:
        _run_core_checks(runner, core_url, settings, core_token)
    if agent_url is not None:
        _run_agent_checks(runner, agent_url, settings, agent_token)

    print("")
    if runner.failures:
        print(f"{len(runner.failures)} of {runner.check_count} smoke checks failed")
        return 1
    print(f"all {runner.check_count} smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
