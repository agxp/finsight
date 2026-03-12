#!/usr/bin/env python3
"""End-to-end smoke test for the FinSight pipeline."""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

BASE_URL = os.getenv("FINSIGHT_URL", "http://localhost:8000")
API_KEY = os.getenv("FINSIGHT_API_KEY", "")


async def main() -> None:
    if not API_KEY:
        print("ERROR: Set FINSIGHT_API_KEY environment variable")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {API_KEY}"}

    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers) as client:
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.text}"
        print("✓ Health check passed")

        r = await client.get("/ready")
        print(f"✓ Ready check: {r.json()}")

        r = await client.get("/v1/filings")
        assert r.status_code == 200
        data = r.json()
        print(f"✓ Filings list: {data['total']} filings")

        if data["total"] == 0:
            print("\nNo filings yet. Trigger ingestion:")
            print(
                '  curl -X POST http://localhost:8000/v1/filings/ingest \\\n'
                '    -H "Authorization: Bearer $FINSIGHT_API_KEY" \\\n'
                '    -H "Content-Type: application/json" \\\n'
                "    -d '{\"ticker\": \"AAPL\", \"date_from\": \"2024-01-01\", \"date_to\": \"2024-12-31\"}'"
            )
            return

        r = await client.post(
            "/v1/query",
            json={"query": "What were the main risk factors in recent AAPL filings?"},
        )
        assert r.status_code == 200
        result = r.json()
        print(f"✓ Agent query answered: {len(result.get('answer', ''))} chars")
        print(f"  Sources: {len(result.get('sources', []))} chunks retrieved")

    print("\nSmoke test passed!")


if __name__ == "__main__":
    asyncio.run(main())
