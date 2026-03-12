from __future__ import annotations

from fastapi import APIRouter, Request

from finsight.domain.types import HealthResponse, ReadyResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(request: Request) -> ReadyResponse:
    checks: dict[str, bool] = {}

    try:
        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    all_ok = all(checks.values())
    return ReadyResponse(status="ok" if all_ok else "degraded", checks=checks)
