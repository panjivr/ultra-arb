from arb.infra.db import AsyncSessionLocal
from arb.infra.redis_bus import get_redis


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def get_redis_client():
    return get_redis()
