"""Run the ADR-0009 synthetic Core-to-Agent boundary five times.

The verifier starts the real Agent Runtime HTTP process with its deterministic
mock provider, calls it through Core's production adapter and signed service
credential, exercises a blocked failure path, and writes bounded evidence.
It never connects to AWS and never stores the synthetic turn text in evidence.

Scope, because a passing run is narrower than "Gate 1 works": this exercises the
``AgentRuntimeClient`` -> Agent Runtime HTTP boundary only. The request payload
below is built here, ``requested_outputs`` included, so ``CompanionService``
never runs and Core's authorization, consent, ASR Gate and speaker-evidence
decisions are outside what these five runs can fail on. Every turn is text.
Those Core seams are covered by
``services/core-api/tests/integration/test_companion_voice_memory_path.py``;
keep both in mind before reading a green run as end-to-end coverage.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
CORE_API = ROOT / "services" / "core-api"
sys.path.insert(0, str(CORE_API))

from app.adapters.agent_runtime import AgentRuntimeClient  # noqa: E402
from app.adapters.service_identity import ServiceCredentialSigner  # noqa: E402

SYNTHETIC_SECRET = "synthetic-gate1-service-identity-secret-32-bytes"
FIXTURE_PATH = (
    ROOT
    / ".kiro"
    / "specs"
    / "gate-1-agent-vertical-slice"
    / "fixtures"
    / "gate1-synthetic-v1.json"
)
RESTRICTED_RESPONSE_KEYS = {
    "audio",
    "audio_base64",
    "full_prompt",
    "input_text",
    "prompt",
    "secret",
    "token",
    "transcript",
    "transcript_text",
    "voice_ticket",
}


def _agent_python() -> Path:
    candidates = (
        ROOT / "services" / "agent-runtime" / ".venv" / "Scripts" / "python.exe",
        ROOT / "services" / "agent-runtime" / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Agent Runtime virtual environment is unavailable")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _contains_restricted_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in RESTRICTED_RESPONSE_KEYS
            or _contains_restricted_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_restricted_key(item) for item in value)
    return False


def _load_fixture() -> dict[str, object]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if fixture.get("schema_version") != "1.0.0":
        raise RuntimeError("Gate 1 synthetic fixture has an unsupported version")
    journey = fixture.get("five_run_journey")
    if not isinstance(journey, dict):
        raise RuntimeError("Gate 1 synthetic fixture has no five-run journey")
    return fixture


def _request_payload(
    run_number: int,
    fixture: dict[str, object],
    *,
    blocked: bool = False,
) -> dict[str, object]:
    suffix = f"{run_number:02d}-{uuid4()}"
    journey = fixture["five_run_journey"]
    if not isinstance(journey, dict):
        raise RuntimeError("Gate 1 synthetic fixture journey is invalid")
    input_key = "blocked_input" if blocked else "allowed_input"
    input_text = journey.get(input_key)
    if not isinstance(input_text, str) or not input_text:
        raise RuntimeError(f"Gate 1 synthetic fixture is missing {input_key}")
    return {
        "schema_version": "1.0.0",
        "request_id": f"gate1-request-{suffix}",
        "trace_id": f"gate1-trace-{suffix}",
        "agent_run_id": f"gate1-run-{suffix}",
        "session_id": f"gate1-session-{suffix}",
        "actor_id": f"gate1-actor-{suffix}",
        "actor_role": "elder",
        "elder_id": f"gate1-elder-{suffix}",
        "tenant_id": f"gate1-tenant-{suffix}",
        "purpose": "conversation",
        "consent_version": "synthetic-consent-v1",
        "policy_version": "adr-0009+memory-policy-v1",
        "language": "zh-TW",
        "input_text": input_text,
        "allowed_tools": [],
        "requested_outputs": ["event_candidate", "memory_candidate"],
        "confirmed_memories": [],
        "verified_care_events": [],
        "max_steps": 2,
        "latency_budget_ms": 3000,
    }


async def _wait_until_ready(base_url: str, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 20
    async with httpx.AsyncClient(base_url=base_url, trust_env=False) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"Agent Runtime exited during startup with code {process.returncode}"
                )
            try:
                response = await client.get("/health", timeout=1)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError("Agent Runtime did not become healthy within 20 seconds")


async def _run_five(
    base_url: str,
    fixture: dict[str, object],
) -> list[dict[str, object]]:
    signer = ServiceCredentialSigner(secret=SYNTHETIC_SECRET)
    adapter = AgentRuntimeClient(
        base_url=base_url,
        timeout_seconds=5,
        credential_signer=signer,
    )
    results: list[dict[str, object]] = []
    for run_number in range(1, 6):
        started = time.perf_counter()
        allowed_request = _request_payload(run_number, fixture)
        allowed = await adapter.run(
            request_payload=allowed_request,
            correlation_id=str(uuid.uuid4()),
        )
        blocked_request = _request_payload(run_number, fixture, blocked=True)
        blocked = await adapter.run(
            request_payload=blocked_request,
            correlation_id=str(uuid.uuid4()),
        )
        if allowed.agent_run_id != allowed_request["agent_run_id"]:
            raise AssertionError(
                "Agent Runtime did not preserve Core-owned agent_run_id"
            )
        if allowed.safety_result.decision != "ALLOW":
            raise AssertionError("Synthetic main journey was not allowed")
        if (
            allowed.event_candidate_proposal is None
            or allowed.memory_candidate_proposal is None
        ):
            raise AssertionError(
                "Synthetic main journey did not return both bounded proposals"
            )
        if blocked.safety_result.decision not in {"BLOCK", "SAFE_FALLBACK"}:
            raise AssertionError("Synthetic medical failure path was not blocked")
        if (
            blocked.event_candidate_proposal is not None
            or blocked.memory_candidate_proposal is not None
        ):
            raise AssertionError("Blocked turn returned a candidate proposal")
        serialized = {
            "allowed": asdict(allowed),
            "blocked": asdict(blocked),
        }
        if _contains_restricted_key(serialized):
            raise AssertionError("Agent response contains a Restricted Data key")
        results.append(
            {
                "run": run_number,
                "passed": True,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "agent_run_authority_preserved": True,
                "bounded_event_proposal": True,
                "bounded_memory_proposal": True,
                "blocked_path_zero_candidates": True,
                "restricted_response_keys_absent": True,
            }
        )

    async with httpx.AsyncClient(base_url=base_url, trust_env=False) as client:
        direct = await client.post(
            "/api/v1/agent/runs",
            json=_request_payload(99, fixture),
            headers={"X-Correlation-ID": "gate1-browser-direct-denial"},
        )
    if direct.status_code != 401:
        raise AssertionError("Browser-direct Agent Runtime request was not denied")
    return results


def _git_revision() -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_working_tree_dirty() -> bool:
    completed = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={ROOT.as_posix()}",
            "status",
            "--porcelain",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(completed.stdout.strip())


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-out",
        type=Path,
        default=(
            ROOT
            / ".kiro"
            / "specs"
            / "gate-1-agent-vertical-slice"
            / "evidence"
            / "gate1-synthetic-five-run.json"
        ),
    )
    args = parser.parse_args()
    fixture = _load_fixture()
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "test",
            "MODEL_PROVIDER": "mock",
            "RAG_MODE": "disabled",
            "AWS_EC2_METADATA_DISABLED": "true",
            "SERVICE_IDENTITY_ENABLED": "true",
            "SERVICE_IDENTITY_HMAC_SECRET": SYNTHETIC_SECRET,
        }
    )
    command = [
        str(_agent_python()),
        "-m",
        "uvicorn",
        "agent_runtime.app:app",
        "--app-dir",
        str(ROOT / "services" / "agent-runtime" / "src"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        await _wait_until_ready(base_url, process)
        runs = await _run_five(base_url, fixture)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    evidence = {
        "schema_version": "1.0.0",
        "profile": "ADR-0009-synthetic",
        "provider": "synthetic",
        "production_approved": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "revision": _git_revision(),
        "working_tree_dirty": _git_working_tree_dirty(),
        "fixture": {
            "path": str(FIXTURE_PATH.relative_to(ROOT)).replace("\\", "/"),
            "schema_version": fixture["schema_version"],
            "sha256": hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
        },
        "adapters": {
            "core_agent_adapter": "AgentRuntimeClient",
            "agent_provider": "mock",
            "agent_version": "0.0.1",
            "policy_version": "adr-0009+memory-policy-v1",
            "contract_version": "1.0.0",
        },
        "claims_excluded": [
            "production latency",
            "production availability",
            "production model quality",
            "production data region",
            "production cost",
            "Core authorization and consent gating",
            "Core speaker evidence and requested_outputs derivation",
            "Voice Ticket, ASR Gate and any voice input mode",
            "Core database state and Domain writes",
        ],
        "scope": {
            "covers": (
                "Core AgentRuntimeClient adapter to Agent Runtime HTTP boundary"
            ),
            "input_mode": "text",
            "core_side_note": (
                "This harness builds the request payload itself, including "
                "requested_outputs, so CompanionService never runs. Core's "
                "authorization, consent, ASR Gate and speaker-evidence "
                "decisions cannot fail these runs. They are covered by "
                "services/core-api/tests/integration/"
                "test_companion_voice_memory_path.py."
            ),
        },
        "browser_direct_denied": True,
        "runs": runs,
    }
    output = args.evidence_out
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Gate 1 synthetic cross-service evidence: 5/5 passed -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
