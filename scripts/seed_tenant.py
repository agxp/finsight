#!/usr/bin/env python3
"""Seed a dev tenant and print the API key."""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

from finsight.config import get_settings


def generate_api_key() -> tuple[str, str]:
    """Return (raw_key, sha256_hash)."""
    raw = "fs_" + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


async def main() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        raw_key, key_hash = generate_api_key()
        ticker_universe = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]

        row = await conn.fetchrow(
            """
            INSERT INTO tenants (name, api_key_hash, ticker_universe)
            VALUES ($1, $2, $3)
            ON CONFLICT (api_key_hash) DO NOTHING
            RETURNING id, name
            """,
            "dev-tenant",
            key_hash,
            ticker_universe,
        )

        if row:
            print(f"Created tenant: {row['name']} (id={row['id']})")
            print(f"\nAPI Key (save this — shown only once):\n  {raw_key}")
            print(f"\nTicker universe: {', '.join(ticker_universe)}")
        else:
            print("Tenant already exists (key hash collision — regenerate)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
