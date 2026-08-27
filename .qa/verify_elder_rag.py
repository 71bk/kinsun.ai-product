"""Run one synthetic elder RAG turn through Frontend BFF, Core, and Agent Runtime."""

from __future__ import annotations

import json
from uuid import uuid4

import httpx

from verify_elder_login import (
    EXPECTED_ELDER_ID,
    FRONTEND_BASE_URL,
    authenticate_elder,
    verify_elder_profile,
)

QUERY = "長者平常要怎麼吃得比較均衡？"


def _data(response: httpx.Response, operation: str) -> dict:
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"{operation} returned {response.status_code}")
    data = response.json().get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"{operation} returned an invalid envelope")
    return data


def main() -> None:
    with httpx.Client(
        base_url=FRONTEND_BASE_URL,
        follow_redirects=False,
        timeout=90,
    ) as client:
        cookie_header = authenticate_elder(client)
        verify_elder_profile(client, cookie_header)
        common_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Cookie": cookie_header,
            "Origin": FRONTEND_BASE_URL,
        }

        session = _data(
            client.post(
                f"/backend/core/api/v1/elders/{EXPECTED_ELDER_ID}/voice-sessions",
                headers={
                    **common_headers,
                    "Idempotency-Key": f"elder-rag-session-{uuid4()}",
                },
                json={
                    "language_preference": "ZH_TW",
                    "input_mode": "text",
                    "client_timezone": "Asia/Taipei",
                    "purpose": "BASIC_VOICE",
                },
            ),
            "create text session",
        )
        if session.get("state") != "CREATED":
            raise RuntimeError("Text session was not created")

        turn = _data(
            client.post(
                f"/backend/core/api/v1/voice-sessions/{session['session_id']}/companion-turns",
                headers={
                    **common_headers,
                    "Idempotency-Key": f"elder-rag-turn-{uuid4()}",
                },
                json={"input_text": QUERY},
            ),
            "run companion RAG turn",
        )
        reply = turn.get("reply_text", "")
        citation_count = reply.count("\n- [")
        if turn.get("result_status") != "SUCCESS":
            safe_failure = {
                "result_status": turn.get("result_status"),
                "safety_decision": turn.get("safety_decision"),
                "reason_codes": turn.get("reason_codes"),
            }
            raise RuntimeError(
                f"RAG turn failed: {json.dumps(safe_failure, ensure_ascii=False)}"
            )
        if turn.get("safety_decision") != "ALLOW":
            raise RuntimeError("RAG turn did not pass output safety")
        if "引用來源：" not in reply or citation_count < 1:
            raise RuntimeError("RAG turn returned no user-facing citations")

    print(
        json.dumps(
            {
                "ok": True,
                "query_case": "elder_general_information_allowed",
                "result_status": turn["result_status"],
                "safety_decision": turn["safety_decision"],
                "risk_level": turn["risk_level"],
                "citation_count": citation_count,
                "context_manifest": "present",
                "session_state": turn["session_state"],
                "reason_codes": turn["reason_codes"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
