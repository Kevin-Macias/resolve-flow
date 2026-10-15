"""Read and reconcile a saved run in a separate interpreter."""

import asyncio
import json
import sys
from uuid import UUID

from conftest import CountingProvider
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.intake.runtime import IntakeRuntime
from api.intake.service import IntakeService


async def main() -> None:
    url, schema, run_id, revision = sys.argv[1:]
    engine = create_async_engine(
        url.replace("postgresql://", "postgresql+psycopg://"),
        connect_args={"options": f"-csearch_path={schema},public"},
    )
    try:
        provider = CountingProvider()
        runtime = IntakeRuntime(
            async_sessionmaker(engine, expire_on_commit=False),
            url,
            provider=provider,
            checkpoint_schema=f"{schema}_cp",
        )
        service = IntakeService(runtime, "customer-a")
        before = await service.get(UUID(run_id))
        assert before.revision == int(revision)
        view = await service.recover(before.run_id, before.revision)
        print(
            json.dumps({"view": view.model_dump(mode="json"), "calls": provider.calls})
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
