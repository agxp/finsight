from __future__ import annotations

import uuid
from datetime import date

import asyncpg

from finsight.domain.types import FilingChunk, RetrievedChunk


class ChunkStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_chunks(self, chunks: list[FilingChunk]) -> int:
        """Insert or update chunks. Returns count inserted/updated."""
        if not chunks:
            return 0

        async with self._pool.acquire() as conn:
            rows = [
                (
                    chunk.filing_id,
                    chunk.chunk_index,
                    chunk.section,
                    chunk.content,
                    chunk.token_count,
                    chunk.embedding,
                    chunk.ticker,
                    chunk.form_type,
                    chunk.period_of_report,
                )
                for chunk in chunks
            ]
            await conn.executemany(
                """
                INSERT INTO filing_chunks
                    (filing_id, chunk_index, section, content, token_count, embedding,
                     ticker, form_type, period_of_report)
                VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, $9)
                ON CONFLICT (filing_id, chunk_index) DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    content = EXCLUDED.content,
                    token_count = EXCLUDED.token_count
                """,
                rows,
            )
            return len(chunks)

    async def count_for_filing(self, filing_id: uuid.UUID) -> int:
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM filing_chunks WHERE filing_id = $1", filing_id
            )

    async def semantic_search(
        self,
        query_embedding: list[float],
        *,
        ticker_filter: list[str] | None = None,
        form_type_filter: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        section_filter: str | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        conditions = ["embedding IS NOT NULL"]
        params: list = [query_embedding]

        if ticker_filter:
            params.append(ticker_filter)
            conditions.append(f"ticker = ANY(${len(params)})")
        if form_type_filter:
            params.append(form_type_filter)
            conditions.append(f"form_type = ANY(${len(params)})")
        if date_from:
            params.append(date_from)
            conditions.append(f"period_of_report >= ${len(params)}")
        if date_to:
            params.append(date_to)
            conditions.append(f"period_of_report <= ${len(params)}")
        if section_filter:
            params.append(section_filter)
            conditions.append(f"section = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    id, filing_id, ticker, form_type, period_of_report,
                    section, content,
                    1 - (embedding <=> $1::vector) AS score
                FROM filing_chunks
                {where}
                ORDER BY embedding <=> $1::vector
                LIMIT ${len(params)}
                """,
                *params,
            )

        return [
            RetrievedChunk(
                chunk_id=r["id"],
                filing_id=r["filing_id"],
                ticker=r["ticker"],
                form_type=r["form_type"],
                period_of_report=r["period_of_report"],
                section=r["section"],
                content=r["content"],
                score=float(r["score"]),
            )
            for r in rows
        ]

    async def check_embedding_quality(self, filing_id: uuid.UUID) -> dict:
        """Return embedding quality metrics for a filing."""
        async with self._pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM filing_chunks WHERE filing_id = $1", filing_id
            )
            with_embedding = await conn.fetchval(
                "SELECT COUNT(*) FROM filing_chunks WHERE filing_id = $1 AND embedding IS NOT NULL",
                filing_id,
            )
            zero_vectors = await conn.fetchval(
                """
                SELECT COUNT(*) FROM filing_chunks
                WHERE filing_id = $1
                AND embedding IS NOT NULL
                AND embedding = array_fill(0.0, ARRAY[1536])::vector
                """,
                filing_id,
            )
        return {
            "total": total,
            "with_embedding": with_embedding,
            "zero_vectors": zero_vectors,
        }
