from __future__ import annotations

import time
import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, status

log = structlog.get_logger(__name__)


class RateLimiter:
    """Redis sliding window rate limiter."""

    def __init__(self, redis_client: aioredis.Redis, limit: int, window_seconds: int = 60) -> None:
        self._redis = redis_client
        self._limit = limit
        self._window = window_seconds

    async def check(self, tenant_id: uuid.UUID) -> None:
        """Raises HTTP 429 if rate limit exceeded."""
        key = f"rate_limit:agent:{tenant_id}"
        now = time.time()
        window_start = now - self._window

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.zcard(key)
        pipe.expire(key, self._window)
        results = await pipe.execute()

        count = results[2]
        if count > self._limit:
            log.warning("rate limit exceeded", tenant_id=str(tenant_id), count=count)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: {self._limit} requests per {self._window}s",
                headers={"Retry-After": str(self._window)},
            )
