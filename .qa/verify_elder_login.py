"""Verify the synthetic elder account through the local Frontend BFF."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_BASE_URL = "http://localhost:3000"
EXPECTED_ACTOR_TYPE = "ELDER"
EXPECTED_ELDER_ID = "40000000-0000-4000-8000-000000000001"


def _repo_env_value(key: str) -> str:
    for raw_line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        candidate, _, value = line.partition("=")
        if candidate.strip() == key:
            return value.strip().strip('"').strip("'")
    raise RuntimeError(f"{key} is required")


def authenticate_elder(client: httpx.Client) -> str:
    login = client.post(
        "/backend/auth/kinsun/login",
        headers={"Origin": FRONTEND_BASE_URL},
        data={
            "returnTo": "/onboarding/resolve",
            "email": "elder.demo@kinsun.local",
            "password": _repo_env_value("DEMO_ACCOUNT_PASSWORD"),
        },
    )
    if login.status_code != 303:
        raise RuntimeError(f"BFF login returned {login.status_code}")
    location = login.headers.get("location")
    if location != "/onboarding/resolve":
        raise RuntimeError(f"BFF login returned unexpected safe route: {location!r}")
    if not client.cookies:
        raise RuntimeError("BFF login did not establish an application session cookie")
    session_cookie = next(iter(client.cookies.jar), None)
    if session_cookie is None:
        raise RuntimeError("BFF login cookie could not be read by the smoke client")
    # httpx withholds Secure cookies over HTTP. Local browsers treat localhost
    # as a secure context, so this smoke forwards the opaque cookie explicitly
    # without logging its value.
    return f"{session_cookie.name}={session_cookie.value}"


def verify_elder_profile(client: httpx.Client, cookie_header: str) -> dict:
    me = client.get(
        "/backend/core/api/v1/me",
        headers={"Accept": "application/json", "Cookie": cookie_header},
    )
    if me.status_code != 200:
        raise RuntimeError(f"Authenticated /api/v1/me returned {me.status_code}")
    profile = me.json().get("data", {})
    if profile.get("actor_type") != EXPECTED_ACTOR_TYPE:
        raise RuntimeError("Authenticated actor is not the synthetic elder")
    if profile.get("elder_id") != EXPECTED_ELDER_ID:
        raise RuntimeError("Authenticated elder scope does not match the Demo manifest")
    return profile


def main() -> None:
    with httpx.Client(
        base_url=FRONTEND_BASE_URL,
        follow_redirects=False,
        timeout=30,
    ) as client:
        cookie_header = authenticate_elder(client)
        verify_elder_profile(client, cookie_header)

    print(
        json.dumps(
            {
                "ok": True,
                "login_status": 303,
                "session_cookie": "present",
                "me_status": 200,
                "actor_type": EXPECTED_ACTOR_TYPE,
                "elder_scope": "matched",
            }
        )
    )


if __name__ == "__main__":
    main()
