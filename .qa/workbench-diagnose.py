"""Read-only synthetic dashboard probe; exception type and frame locations only."""

import asyncio
import importlib.util
import json
import traceback
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "qa_fixture", root / "scripts/qa/workbench_fixture.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
base = module.base
from app.api.identity import get_authorized_elders
from app.core.auth import ActorContext
from app.schemas.identity import ElderMode


async def main():
    settings = base.Settings(_env_file=root / ".env")
    base.validate_target(settings.app_env, settings.database_url)
    engine = base.create_async_engine(
        settings.database_url, echo=False, hide_parameters=True
    )
    try:
        async with base.async_sessionmaker(engine)() as session:
            await session.execute(base.text("SET TRANSACTION READ ONLY"))
            try:
                result = await get_authorized_elders(
                    ElderMode("home-care"),
                    None,
                    100,
                    ActorContext(
                        base.IDS["reader"], "HOME_CARE_WORKER", base.IDS["tenant"]
                    ),
                    session,
                )
                print(
                    json.dumps({"result": "ok", "items": len(result["data"]["items"])})
                )
            except Exception as error:
                print(
                    json.dumps(
                        {
                            "error_type": type(error).__name__,
                            "sqlstate": getattr(error, "sqlstate", None),
                            "frames": [
                                {
                                    "file": Path(frame.filename).name,
                                    "line": frame.lineno,
                                    "function": frame.name,
                                }
                                for frame in traceback.extract_tb(error.__traceback__)
                            ],
                        }
                    )
                )
            await session.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
