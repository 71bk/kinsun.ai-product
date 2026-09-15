"""Report only safety booleans; never echo environment values or diff content."""

import json
import subprocess
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / ".env")
result = subprocess.run(
    [
        "git",
        "-c",
        f"safe.directory={root.as_posix()}",
        "diff",
        "--cached",
        "--no-ext-diff",
    ],
    cwd=root,
    capture_output=True,
    check=True,
)
diff = result.stdout.decode("utf-8")
keys = [
    "KINSUN_IDENTITY_HMAC_SECRET",
    "KINSUN_EMAIL_CHALLENGE_HMAC_SECRET",
    "KINSUN_AUTH_HANDOFF_SECRET",
    "KINSUN_SYNTHETIC_EMAIL_CODE_SECRET",
    "DATABASE_URL",
]
matches = [key for key in keys if values.get(key) and values[key] in diff]
private = json.loads((root / ".qa/.env.previous-record-real-auth").read_text())
scrubbed = private.get("retired") is True and "accounts" not in private
print(
    json.dumps(
        {
            "secret_matches_by_setting_name": matches,
            "bootstrap_passwords_scrubbed": scrubbed,
        }
    )
)
raise SystemExit(1 if matches or not scrubbed else 0)
