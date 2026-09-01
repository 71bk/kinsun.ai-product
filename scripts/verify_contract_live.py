"""Validate real Core API responses against the published contract.

Runs the app in-process and checks that what it actually returns conforms to
contracts/. A contract that has never been checked against the running service
is just prose.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "core-api"))
# This verifier is specifically a no-authenticator fail-closed check. Make it
# deterministic even when the developer's local .env enables synthetic auth.
os.environ["FAKE_AUTH_ENABLED"] = "false"
# Live contract verification never requires a real Google/LINE token or App Session.
# These probes exercise the implemented fail-closed edge.
# Include the gated direct-OIDC/App-Session routes while keeping every live
# probe synthetic and fail-closed before any provider network request.
os.environ["APP_SESSION_AUTH_ENABLED"] = "true"
os.environ["GOOGLE_OIDC_HANDOFF_ENABLED"] = "true"
os.environ["GOOGLE_OIDC_CLIENT_ID"] = "live-contract-google-client-id"
os.environ["GOOGLE_IDENTITY_HMAC_SECRET"] = (
    "live-contract-google-identity-secret-material-32-bytes"
)
os.environ["GOOGLE_OIDC_HANDOFF_SECRET"] = (
    "live-contract-google-handoff-secret-material-32-bytes"
)
os.environ["LINE_OIDC_HANDOFF_ENABLED"] = "true"
os.environ["LINE_LOGIN_CHANNEL_ID"] = "1234567890"
os.environ["LINE_IDENTITY_HMAC_SECRET"] = (
    "live-contract-line-identity-secret-material-32-bytes"
)
os.environ["LINE_OIDC_HANDOFF_SECRET"] = (
    "live-contract-line-handoff-secret-material-32-bytes"
)
os.environ["FAMILY_INVITATION_HMAC_SECRET"] = (
    "live-contract-family-invitation-secret-material-32-bytes"
)
os.environ["KINSUN_NATIVE_AUTH_ENABLED"] = "true"
os.environ["KINSUN_IDENTITY_HMAC_SECRET"] = (
    "live-contract-kinsun-identity-secret-material-32-bytes"
)
os.environ["KINSUN_EMAIL_CHALLENGE_HMAC_SECRET"] = (
    "live-contract-kinsun-challenge-secret-material-32-bytes"
)
os.environ["KINSUN_AUTH_HANDOFF_SECRET"] = (
    "live-contract-kinsun-handoff-secret-material-32-bytes"
)
os.environ["KINSUN_EMAIL_DELIVERY_MODE"] = "synthetic"
os.environ["KINSUN_SYNTHETIC_EMAIL_CODE_SECRET"] = "246810"
# Keep Voice Ticket dependencies deterministic while probing their unauthenticated
# fail-closed edge; this synthetic secret is verifier-only and not a deployment credential.
os.environ["VOICE_TICKET_ENABLED"] = "true"
os.environ["VOICE_TICKET_HMAC_SECRET"] = (
    "live-contract-voice-ticket-secret-material-32-bytes"
)
# Internal speech endpoints should exercise their authentication edge rather
# than stop at a disabled-feature 503. The verifier never creates a credential.
os.environ["SPEECH_SERVICE_IDENTITY_ENABLED"] = "true"
os.environ["SPEECH_SERVICE_IDENTITY_HMAC_SECRET"] = (
    "live-contract-speech-service-secret-material-32-bytes"
)

from app.main import create_app  # noqa: E402 - path must be installed before app import

CONTRACTS = Path(sys.argv[1]).resolve()
OPENAPI = yaml.safe_load(
    (CONTRACTS / "openapi" / "core-api.v1.yaml").read_text(encoding="utf-8")
)

failures: list[str] = []


def registry() -> Registry:
    reg = Registry()
    for path in sorted((CONTRACTS / "schemas").rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
    return reg


REG = registry()


def load(rel: str) -> dict:
    return json.loads((CONTRACTS / "schemas" / rel).read_text(encoding="utf-8"))


def inline_schema(path: str, status: str, method: str = "get") -> dict:
    """Pull the inline response schema the OpenAPI doc declares for a path."""
    node = OPENAPI["paths"][path][method]["responses"][status]
    return node["content"]["application/json"]["schema"]


def check(label: str, payload: dict, schema: dict) -> None:
    errors = list(Draft202012Validator(schema, registry=REG).iter_errors(payload))
    if errors:
        failures.append(f"{label}: {errors[0].message}")
        print(f"FAIL  {label}: {errors[0].message}")
    else:
        print(f"ok    {label}")


async def main() -> int:
    app = create_app()
    runtime_openapi = app.openapi()
    methods = {"get", "post", "patch", "delete"}
    runtime_operations = {
        (path, method)
        for path, item in runtime_openapi["paths"].items()
        for method in item
        if method in methods
    }
    contracted_operations = {
        (path, method)
        for path, item in OPENAPI["paths"].items()
        for method in item
        if method in methods
    }
    if runtime_operations != contracted_operations:
        missing = sorted(runtime_operations - contracted_operations)
        stale = sorted(contracted_operations - runtime_operations)
        failures.append(
            f"OpenAPI/runtime operation mismatch: missing={missing}, stale={stale}"
        )
        print(
            f"FAIL  OpenAPI/runtime operation mismatch: missing={missing}, stale={stale}"
        )
    else:
        print(f"ok    all {len(runtime_operations)} runtime operations are contracted")

    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.get("/health")
        check(
            "GET /health 200 vs contract",
            response.json(),
            inline_schema("/health", "200"),
        )

        response = await client.get("/ready")
        check(
            "GET /ready 200 vs contract",
            response.json(),
            inline_schema("/ready", "200"),
        )

        # No credentials configured -> must fail closed as a contract-shaped 401.
        response = await client.get(
            "/api/v1/elders/2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40"
        )
        if response.status_code != 401:
            failures.append(
                f"protected route returned {response.status_code}, expected 401"
            )
            print(f"FAIL  protected route status: {response.status_code}")
        else:
            print("ok    protected route fails closed with 401")
        check(
            "401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.get("/api/v1/me")
        check(
            "GET /api/v1/me 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/voice-sessions/2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40/companion-turns",
            headers={"Idempotency-Key": "live-contract-companion-turn"},
            json={"input_text": "這是合成的契約驗證文字。"},
        )
        if response.status_code != 401:
            failures.append(
                "POST companion turn did not fail closed with 401: "
                f"returned {response.status_code}"
            )
            print(f"FAIL  POST companion turn fails closed: {response.status_code}")
        else:
            print("ok    POST companion turn fails closed with 401")
        check(
            "POST companion turn 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/assisted-elder-sessions/current/first-use-acknowledgement",
            headers={"Idempotency-Key": "live-contract-assisted-acknowledgement"},
            json={"acknowledged": True},
        )
        if response.status_code != 401:
            failures.append(
                "POST assisted first-use acknowledgement did not fail closed with 401: "
                f"returned {response.status_code}"
            )
            print(
                "FAIL  POST assisted first-use acknowledgement fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST assisted first-use acknowledgement fails closed with 401")
        check(
            "POST assisted first-use acknowledgement 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/assisted-elder-sessions/current/first-use-acknowledgement/revoke",
            headers={"Idempotency-Key": "live-contract-assisted-acknowledgement-revoke"},
        )
        if response.status_code != 401:
            failures.append(
                "POST assisted acknowledgement revoke did not fail closed with 401: "
                f"returned {response.status_code}"
            )
            print(
                "FAIL  POST assisted acknowledgement revoke fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST assisted acknowledgement revoke fails closed with 401")
        check(
            "POST assisted acknowledgement revoke 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        sample_uuid = "2a6f9c31-8e47-4b52-9d10-3c8a7e5b1a40"

        response = await client.post(
            f"/api/v1/elders/{sample_uuid}/voice-tickets",
            headers={"Idempotency-Key": "live-contract-voice-ticket-issue"},
            json={
                "language_preference": "ZH_TW",
                "input_mode": "voice_with_text_fallback",
                "client_audio_format": "audio/webm",
                "client_timezone": "Asia/Taipei",
                "purpose": "BASIC_VOICE",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/elders/{elder_id}/voice-tickets returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/elders/{elder_id}/voice-tickets fails closed: "
                f"{response.status_code}"
            )
        else:
            print(
                "ok    POST /api/v1/elders/{elder_id}/voice-tickets "
                "fails closed with 401"
            )
        check(
            "POST /api/v1/elders/{elder_id}/voice-tickets 401 body "
            "vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/voice-tickets/consume",
            json={
                "session_id": sample_uuid,
                "voice_ticket": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/voice-tickets/consume returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/internal/voice-tickets/consume fails closed: "
                f"{response.status_code}"
            )
        else:
            print(
                "ok    POST /api/v1/internal/voice-tickets/consume "
                "fails closed with 401"
            )
        check(
            "POST /api/v1/internal/voice-tickets/consume 401 body "
            "vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            f"/api/v1/internal/elders/{sample_uuid}/memory-candidates/"
            f"{sample_uuid}/voice-confirmation",
            headers={"Idempotency-Key": "live-contract-memory-voice-confirmation"},
            json={
                "confirmation_method": "ELDER_VOICE",
                "session_id": sample_uuid,
                "expected_candidate_version": 1,
                "consent_version": 1,
                "confirmation_question_digest": "a" * 64,
                "response_intent": "AFFIRM",
                "witness_actor_id": None,
                "witness_evidence_reference": None,
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST internal Memory voice confirmation did not fail closed with 401: "
                f"returned {response.status_code}"
            )
            print(
                "FAIL  POST internal Memory voice confirmation fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST internal Memory voice confirmation fails closed with 401")
        check(
            "POST internal Memory voice confirmation 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/agent-runs",
            headers={"Idempotency-Key": "live-contract-agent-run"},
            json={
                "session_id": None,
                "elder_id": sample_uuid,
                "agent_id": "event-extractor",
                "agent_version": "1.0.0",
                "policy_version": "live-contract-v1",
                "trace_id": "trace-live-contract-agent-run",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/agent-runs returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/internal/agent-runs fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST /api/v1/internal/agent-runs fails closed with 401")
        check(
            "POST /api/v1/internal/agent-runs 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            f"/api/v1/internal/agent-runs/{sample_uuid}/complete",
            headers={"Idempotency-Key": "live-contract-agent-run-complete"},
            json={"result_status": "SUCCESS", "stop_reason": None},
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/agent-runs/{agent_run_id}/complete returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/internal/agent-runs/{agent_run_id}/complete "
                f"fails closed: {response.status_code}"
            )
        else:
            print(
                "ok    POST /api/v1/internal/agent-runs/{agent_run_id}/complete "
                "fails closed with 401"
            )
        check(
            "POST /api/v1/internal/agent-runs/{agent_run_id}/complete 401 body "
            "vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": "Bearer not-an-app-session"},
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/auth/logout returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/auth/logout rejects malformed session: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST /api/v1/auth/logout rejects malformed session with 401")
        check(
            "POST /api/v1/auth/logout 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        kinsun_auth_probes = (
            (
                "/api/v1/internal/auth/kinsun/email/start",
                {
                    "email": "synthetic.live-contract@example.test",
                    "intent": "ELDER",
                    "display_name": "Synthetic Elder",
                },
            ),
            (
                "/api/v1/internal/auth/kinsun/email/complete",
                {
                    "challenge_token": "ke1_" + "a" * 43,
                    "verification_code": "246810",
                    "password": "Synthetic-live-contract-password-1",
                },
            ),
            (
                "/api/v1/internal/auth/kinsun/password/login",
                {
                    "email": "synthetic.live-contract@example.test",
                    "password": "Synthetic-live-contract-password-1",
                },
            ),
        )
        for path, request_body in kinsun_auth_probes:
            response = await client.post(path, json=request_body)
            if response.status_code != 401:
                failures.append(
                    f"POST {path} returned {response.status_code}, expected 401"
                )
                print(
                    f"FAIL  POST {path} rejects missing BFF credential: {response.status_code}"
                )
            else:
                print(f"ok    POST {path} rejects missing BFF credential with 401")
            response_body = response.json()
            check(
                f"POST {path} 401 body vs ErrorEnvelopeV1",
                response_body,
                load("common/ErrorEnvelopeV1.json"),
            )
            serialized = json.dumps(response_body, ensure_ascii=False)
            for restricted_value in request_body.values():
                if isinstance(restricted_value, str) and restricted_value in serialized:
                    failures.append(
                        f"POST {path} reflected rejected authentication input"
                    )
                    print(f"FAIL  POST {path} reflected rejected authentication input")
                    break
            else:
                print(
                    f"ok    POST {path} does not reflect rejected authentication input"
                )

        response = await client.post(
            "/api/v1/internal/auth/google/handoff",
            json={
                "id_token": "synthetic.header.signature",
                "expected_nonce": "synthetic-nonce-value-at-least-32-characters",
                "intent": "ELDER",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/google/handoff returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST /api/v1/internal/auth/google/handoff fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST Google handoff fails closed with 401")
        check(
            "POST Google handoff 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/auth/google/onboarding",
            json={"pending_token": "kp1_" + "a" * 43, "display_name": "Synthetic"},
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/google/onboarding returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST Google onboarding fails closed: " f"{response.status_code}"
            )
        else:
            print("ok    POST Google onboarding fails closed with 401")
        check(
            "POST Google onboarding 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/auth/line/handoff",
            json={
                "id_token": "synthetic.header.signature",
                "expected_nonce": "synthetic-nonce-value-at-least-32-characters",
                "intent": "ELDER",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/line/handoff returned "
                f"{response.status_code}, expected 401"
            )
            print("FAIL  POST LINE handoff fails closed: " f"{response.status_code}")
        else:
            print("ok    POST LINE handoff fails closed with 401")
        check(
            "POST LINE handoff 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/auth/line/onboarding",
            json={"pending_token": "kp1_" + "a" * 43, "display_name": "Synthetic"},
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/line/onboarding returned "
                f"{response.status_code}, expected 401"
            )
            print("FAIL  POST LINE onboarding fails closed: " f"{response.status_code}")
        else:
            print("ok    POST LINE onboarding fails closed with 401")
        check(
            "POST LINE onboarding 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.get("/api/v1/internal/auth/line/status")
        if response.status_code != 401:
            failures.append(
                "GET /api/v1/internal/auth/line/status returned "
                f"{response.status_code}, expected 401"
            )
            print(
                f"FAIL  GET LINE identity status fails closed: {response.status_code}"
            )
        else:
            print("ok    GET LINE identity status fails closed with 401")
        check(
            "GET LINE identity status 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/auth/line/link",
            json={
                "id_token": "synthetic.header.signature",
                "expected_nonce": "synthetic-nonce-value-at-least-32-characters",
            },
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/line/link returned "
                f"{response.status_code}, expected 401"
            )
            print(f"FAIL  POST LINE identity link fails closed: {response.status_code}")
        else:
            print("ok    POST LINE identity link fails closed with 401")
        check(
            "POST LINE identity link 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            "/api/v1/internal/auth/line/merge/confirm",
            json={"merge_token": "km1_" + "a" * 43},
        )
        if response.status_code != 401:
            failures.append(
                "POST /api/v1/internal/auth/line/merge/confirm returned "
                f"{response.status_code}, expected 401"
            )
            print(f"FAIL  POST LINE account merge fails closed: {response.status_code}")
        else:
            print("ok    POST LINE account merge fails closed with 401")
        check(
            "POST LINE account merge 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        invitation_collection = f"/api/v1/elders/{sample_uuid}/family-invitations"
        response = await client.post(
            invitation_collection,
            headers={"Idempotency-Key": "live-contract-family-invitation-create"},
            json={"share_scope": ["REPORT_DAILY"], "expires_in_hours": 24},
        )
        if response.status_code != 401:
            failures.append(
                "POST family invitation create returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST family invitation create fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST family invitation create fails closed with 401")
        check(
            "POST family invitation create 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.get(invitation_collection)
        if response.status_code != 401:
            failures.append(
                "GET family invitation list returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  GET family invitation list fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    GET family invitation list fails closed with 401")
        check(
            "GET family invitation list 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        response = await client.post(
            f"{invitation_collection}/{sample_uuid}/revoke",
            headers={"Idempotency-Key": "live-contract-family-invitation-revoke"},
        )
        if response.status_code != 401:
            failures.append(
                "POST family invitation revoke returned "
                f"{response.status_code}, expected 401"
            )
            print(
                "FAIL  POST family invitation revoke fails closed: "
                f"{response.status_code}"
            )
        else:
            print("ok    POST family invitation revoke fails closed with 401")
        check(
            "POST family invitation revoke 401 body vs ErrorEnvelopeV1",
            response.json(),
            load("common/ErrorEnvelopeV1.json"),
        )

        protected_gets = sorted(
            path
            for path, item in OPENAPI["paths"].items()
            if "get" in item and path not in {"/health", "/ready"}
        )
        for path in protected_gets:
            url = re.sub(r"\{[^}]+\}", sample_uuid, path)
            if path == "/api/v1/me/authorized-elders":
                params = {"mode": "daycare"}
            elif path == "/api/v1/elders/{elder_id}/care-events":
                params = {
                    "event_type": "MEAL",
                    "date_from": "2026-08-01",
                    "date_to": "2026-08-02",
                }
            else:
                params = None
            response = await client.get(url, params=params)
            label = f"GET {path} fails closed"
            if response.status_code != 401:
                failures.append(
                    f"{label}: returned {response.status_code}, expected 401"
                )
                print(f"FAIL  {label}: {response.status_code}")
                continue
            check(
                f"{label} with ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print(
        "\nall live contract checks passed"
        if code == 0
        else f"\n{code} live contract failure(s)"
    )
    raise SystemExit(code)
