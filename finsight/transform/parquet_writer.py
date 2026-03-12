from __future__ import annotations

import uuid
from datetime import datetime, timezone

from finsight.domain.types import Filing, ParquetChunkRow
from finsight.storage.parquet_store import ParquetStore, make_parquet_key
from finsight.transform.chunker import Chunk

PIPELINE_VERSION = "0.1.0"


async def write_chunks_to_parquet(
    chunks: list[Chunk],
    filing: Filing,
    parquet_store: ParquetStore,
) -> str:
    """Convert chunks to ParquetChunkRows and write to MinIO. Returns S3 key."""
    period = filing.period_of_report
    year = period.year
    quarter = (period.month - 1) // 3 + 1
    part_id = str(uuid.uuid4())

    s3_key = make_parquet_key(filing.ticker, year, quarter, part_id)

    rows = [
        ParquetChunkRow(
            filing_id=str(filing.id),
            accession_number=filing.accession_number,
            ticker=filing.ticker,
            form_type=filing.form_type,
            period_of_report=filing.period_of_report.isoformat(),
            filed_date=filing.filed_date.isoformat(),
            section=chunk.section,
            chunk_index=chunk.chunk_index,
            content=chunk.content,
            token_count=chunk.token_count,
            char_count=len(chunk.content),
            has_tables=chunk.has_tables,
            quality_score=1.0,
            pipeline_version=PIPELINE_VERSION,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        for chunk in chunks
    ]

    return await parquet_store.write_chunks(rows, s3_key)
