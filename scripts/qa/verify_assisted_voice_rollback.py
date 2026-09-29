"""Run the isolated synthetic SQL/HTTP workflow, always rolling back its data.

No reset, truncate, schema change, existing account reuse, or provider requests.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))

from pytest import MonkeyPatch  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from app.core.config import get_settings  # noqa: E402


async def main():
    settings = get_settings()
    if settings.app_env != "development":
        raise ValueError("Development required")
    spec = importlib.util.spec_from_file_location(
        "assisted_voice_sql",
        ROOT / "services/core-api/tests/integration/test_assisted_voice_workflow.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_async_engine(
        settings.database_url,
        hide_parameters=True,
        connect_args={
            "server_settings": {"lock_timeout": "5000", "statement_timeout": "15000"},
        },
    )
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            try:
                with MonkeyPatch.context() as patch:
                    await module.test_assisted_voice_http_lifecycle(db, patch)
            finally:
                await db.rollback()
    finally:
        await engine.dispose()
    print(
        json.dumps(
            {
                "assisted_voice_sql_http": "PASS",
                "all_fixture_writes_rolled_back": True,
                "actor_and_speech_auth": "synthetic",
                "agent": "synthetic",
            }
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(
            json.dumps(
                {
                    "error_type": type(error).__name__,
                    "sqlstate": getattr(getattr(error, "orig", error), "sqlstate", None),
                }
            )
        )
        if type(error).__name__ == "ValidationError":
            print(
                json.dumps(
                    [{"field": item["loc"], "type": item["type"]} for item in error.errors()]
                )
            )
        # Only local file/line locations; never exception values, parameters or DSNs.
        tb = error.__traceback__
        while tb:
            filename = Path(tb.tb_frame.f_code.co_filename)
            if filename.is_relative_to(ROOT) and ".venv" not in filename.parts:
                print(f"{filename.relative_to(ROOT)}:{tb.tb_lineno}")
            tb = tb.tb_next
        raise SystemExit(1) from None
