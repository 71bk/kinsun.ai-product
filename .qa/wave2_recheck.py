"""One isolated follow-up campaign; reuse all validated fixture safety gates."""

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

fixture_path = (
    Path(__file__).resolve().parents[1] / "scripts/qa/wave2_browser_fixture.py"
)
spec = importlib.util.spec_from_file_location("wave2_recheck_fixture", fixture_path)
assert spec is not None and spec.loader is not None
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
fixture.RUN = "wave2-browser-20260907-fix-recheck"
fixture.MARKER = "Synthetic Wave2 Fix Recheck 20260907"
fixture.IDS = {
    name: uuid5(NAMESPACE_URL, f"kinsun:{fixture.RUN}:{name}") for name in fixture.IDS
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("inspect", "prepare", "expire"),
        default="inspect",
        nargs="?",
    )
    parser.add_argument("--allow-synthetic-write", action="store_true")
    try:
        asyncio.run(fixture.main(parser.parse_args()))
    except Exception as exc:
        print(json.dumps({"error_type": type(exc).__name__, "ok": False}))
        raise SystemExit(1) from None
