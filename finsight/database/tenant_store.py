from __future__ import annotations

import asyncpg

from finsight.domain.types import Tenant


class TenantStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_api_key_hash(self, api_key_hash: str) -> Tenant | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM tenants WHERE api_key_hash = $1", api_key_hash
            )
            if row is None:
                return None
            return Tenant(
                id=row["id"],
                name=row["name"],
                api_key_hash=row["api_key_hash"],
                ticker_universe=list(row["ticker_universe"]),
                created_at=row["created_at"],
            )

    async def create_tenant(
        self, *, name: str, api_key_hash: str, ticker_universe: list[str]
    ) -> Tenant:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tenants (name, api_key_hash, ticker_universe)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                name,
                api_key_hash,
                ticker_universe,
            )
            return Tenant(
                id=row["id"],
                name=row["name"],
                api_key_hash=row["api_key_hash"],
                ticker_universe=list(row["ticker_universe"]),
                created_at=row["created_at"],
            )
