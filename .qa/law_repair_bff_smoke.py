"""Synthetic local BFF login + Core + real Agent acceptance; no credentials in logs."""
import json
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    config = dotenv_values(ROOT / ".env")
    with httpx.Client(base_url="http://localhost:3000", timeout=120, trust_env=False,
                      headers={"Origin": "http://localhost:3000"}) as client:
        login = client.post("/backend/auth/kinsun/login", data={
            "email": "elder.demo@kinsun.local", "password": config["DEMO_ACCOUNT_PASSWORD"],
            "returnTo": "/elder/consent",
        })
        if login.status_code != 303 or login.headers.get("location") != "/elder/consent":
            location = login.headers.get("location", "")
            print(json.dumps({"stage": "login", "http_status": login.status_code, "passed": False,
                              "invalid_credentials": "error=invalid_credentials" in location,
                              "auth_unavailable": "error=auth_unavailable" in location,
                              "expected_return_path": location == "/elder/consent"}))
            return 1
        # httpx does not implement browsers' secure localhost cookie exception.
        # Send this test session only to the fixed loopback BFF; never alter app cookie flags.
        client.headers["Cookie"] = "; ".join(f"{cookie.name}={cookie.value}" for cookie in client.cookies.jar)
        try:
            me = client.get("/backend/core/api/v1/me")
            me.raise_for_status()
            elder_id = me.json()["data"]["elder_id"]
            passed = True
            for query in ("長照法", "長照法第二條"):
                session = client.post(f"/backend/core/api/v1/elders/{elder_id}/voice-sessions",
                    headers={"Idempotency-Key": "law-session-" + str(uuid.uuid4())},
                    json={"language_preference": "ZH_TW", "input_mode": "text",
                          "client_timezone": "Asia/Taipei", "purpose": "BASIC_VOICE"})
                session.raise_for_status()
                session_id = session.json()["data"]["session_id"]
                response = client.post(f"/backend/core/api/v1/voice-sessions/{session_id}/companion-turns",
                    headers={"Idempotency-Key": "law-turn-" + str(uuid.uuid4())}, json={"input_text": query})
                response.raise_for_status()
                data = response.json()["data"]
                reply = data["reply_text"]
                success = data["result_status"] == "SUCCESS" and data["safety_decision"] == "ALLOW"
                passed = passed and success
                print(json.dumps({"query": query, "http_status": response.status_code,
                    "result_status": data["result_status"], "safety_decision": data["safety_decision"],
                    "reason_codes": data["reason_codes"], "model_route": data["model_route"],
                    "reply_text": reply, "passed": success}, ensure_ascii=True), flush=True)
            return 0 if passed else 1
        finally:
            logout = client.delete("/backend/auth/session")
            print(json.dumps({"test_session_logout_http_status": logout.status_code}))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__,
                          "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None}))
        sys.exit(1)
