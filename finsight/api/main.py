from __future__ import annotations

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finsight.api.middleware.logging import LoggingMiddleware
from finsight.api.middleware.rate_limit import RateLimiter
from finsight.api.routers import agent, filings, health
from finsight.config import get_settings
from finsight.database.audit_store import AuditStore
from finsight.database.chunk_store import ChunkStore
from finsight.database.connection import close_pool, get_pool
from finsight.database.filing_store import FilingStore
from finsight.database.tenant_store import TenantStore
from finsight.embedding.embedder import Embedder
from finsight.storage.object_store import MinIOStore

log = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="FinSight",
        description="Financial Research Data Pipeline + RAG Agent",
        version="0.1.0",
    )

    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        pool = await get_pool()
        app.state.db_pool = pool
        app.state.filing_store = FilingStore(pool)
        app.state.chunk_store = ChunkStore(pool)
        app.state.tenant_store = TenantStore(pool)
        app.state.audit_store = AuditStore(pool)
        app.state.embedder = Embedder()
        app.state.object_store = MinIOStore()

        redis_client = await aioredis.from_url(settings.redis_url, decode_responses=True)
        app.state.redis = redis_client
        app.state.rate_limiter = RateLimiter(
            redis_client,
            limit=settings.rate_limit_agent_rpm,
            window_seconds=60,
        )
        log.info("finsight api started", env=settings.api_env)

    @app.on_event("shutdown")
    async def shutdown():
        await close_pool()
        await app.state.redis.close()
        log.info("finsight api stopped")

    app.include_router(health.router)
    app.include_router(filings.router)
    app.include_router(agent.router)

    return app


app = create_app()
