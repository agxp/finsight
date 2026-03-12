from __future__ import annotations

import json
import uuid
from datetime import date, datetime

import asyncpg

from finsight.domain.types import Filing, FilingStatus


class FilingStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_filing(
        self,
        *,
        accession_number: str,
        ticker: str,
        cik: str,
        form_type: str,
        period_of_report: date,
        filed_date: date,
    ) -> tuple[Filing, bool]:
        """Insert filing; return (filing, created). ON CONFLICT DO NOTHING for idempotency."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO filings (accession_number, ticker, cik, form_type, period_of_report, filed_date)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (accession_number) DO NOTHING
                RETURNING *
                """,
                accession_number,
                ticker,
                cik,
                form_type,
                period_of_report,
                filed_date,
            )
            if row is None:
                existing = await conn.fetchrow(
                    "SELECT * FROM filings WHERE accession_number = $1", accession_number
                )
                return _row_to_filing(existing), False
            return _row_to_filing(row), True

    async def get_by_accession(self, accession_number: str) -> Filing | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM filings WHERE accession_number = $1", accession_number
            )
            return _row_to_filing(row) if row else None

    async def get_by_id(self, filing_id: uuid.UUID) -> Filing | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM filings WHERE id = $1", filing_id)
            return _row_to_filing(row) if row else None

    async def update_status(
        self,
        filing_id: uuid.UUID,
        status: FilingStatus,
        *,
        raw_s3_key: str | None = None,
        parquet_s3_key: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE filings
                SET status = $1,
                    raw_s3_key = COALESCE($2, raw_s3_key),
                    parquet_s3_key = COALESCE($3, parquet_s3_key),
                    error_message = $4,
                    updated_at = now()
                WHERE id = $5
                """,
                status.value,
                raw_s3_key,
                parquet_s3_key,
                error_message,
                filing_id,
            )

    async def list_filings(
        self,
        *,
        ticker: str | None = None,
        status: FilingStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Filing], int]:
        conditions = []
        params: list = []
        if ticker:
            params.append(ticker)
            conditions.append(f"ticker = ${len(params)}")
        if status:
            params.append(status.value)
            conditions.append(f"status = ${len(params)}")

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        offset = (page - 1) * page_size

        async with self._pool.acquire() as conn:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM filings {where}", *params)
            params.extend([page_size, offset])
            rows = await conn.fetch(
                f"SELECT * FROM filings {where} ORDER BY filed_date DESC LIMIT ${len(params)-1} OFFSET ${len(params)}",
                *params,
            )
        return [_row_to_filing(r) for r in rows], count

    async def save_quality_report(
        self,
        filing_id: uuid.UUID,
        stage: str,
        passed: bool,
        checks: list[dict],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO filing_quality_reports (filing_id, stage, passed, checks)
                VALUES ($1, $2, $3, $4)
                """,
                filing_id,
                stage,
                passed,
                json.dumps(checks),
            )


def _row_to_filing(row: asyncpg.Record) -> Filing:
    return Filing(
        id=row["id"],
        accession_number=row["accession_number"],
        ticker=row["ticker"],
        cik=row["cik"],
        form_type=row["form_type"],
        period_of_report=row["period_of_report"],
        filed_date=row["filed_date"],
        raw_s3_key=row["raw_s3_key"],
        parquet_s3_key=row["parquet_s3_key"],
        status=FilingStatus(row["status"]),
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
