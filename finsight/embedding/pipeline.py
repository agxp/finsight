from __future__ import annotations

import uuid
from datetime import date

import structlog

from finsight.database.chunk_store import ChunkStore
from finsight.database.filing_store import FilingStore
from finsight.domain.types import FilingChunk, FilingStatus
from finsight.embedding.embedder import Embedder
from finsight.quality.checks import check_embedding, enforce_quality_gate
from finsight.quality.reporter import log_report
from finsight.storage.parquet_store import ParquetStore

log = structlog.get_logger(__name__)


class EmbedPipeline:
    """Reads Parquet, generates embeddings, upserts to pgvector."""

    def __init__(
        self,
        embedder: Embedder,
        chunk_store: ChunkStore,
        filing_store: FilingStore,
        parquet_store: ParquetStore,
    ) -> None:
        self._embedder = embedder
        self._chunks = chunk_store
        self._filings = filing_store
        self._parquet = parquet_store

    async def run(self, filing_id: uuid.UUID) -> int:
        """Embed all chunks for a filing. Returns number of chunks embedded."""
        filing = await self._filings.get_by_id(filing_id)
        if filing is None:
            raise ValueError(f"Filing {filing_id} not found")

        if filing.parquet_s3_key is None:
            raise ValueError(f"Filing {filing_id} has no Parquet key — run transform first")

        parquet_rows = await self._parquet.read_chunks(filing.parquet_s3_key)
        if not parquet_rows:
            log.warning("no parquet rows found", filing_id=str(filing_id))
            return 0

        parquet_count = len(parquet_rows)
        log.info("embedding chunks", filing_id=str(filing_id), count=parquet_count)

        texts = [row.content for row in parquet_rows]
        embeddings = await self._embedder.embed_texts(texts)

        chunks: list[FilingChunk] = []
        for row, embedding in zip(parquet_rows, embeddings):
            chunks.append(
                FilingChunk(
                    filing_id=filing_id,
                    chunk_index=row.chunk_index,
                    section=row.section,
                    content=row.content,
                    token_count=row.token_count,
                    embedding=embedding,
                    ticker=row.ticker,
                    form_type=row.form_type,
                    period_of_report=date.fromisoformat(row.period_of_report),
                )
            )

        inserted = await self._chunks.upsert_chunks(chunks)
        log.info("chunks upserted", filing_id=str(filing_id), count=inserted)

        quality = await self._chunks.check_embedding_quality(filing_id)
        report = check_embedding(
            filing_id,
            parquet_count=parquet_count,
            pgvector_count=quality["with_embedding"],
            zero_vectors=quality["zero_vectors"],
            embedding_dim=1536,
        )
        log_report(report)
        await self._filings.save_quality_report(
            filing_id,
            report.stage.value,
            report.passed,
            [c.model_dump() for c in report.checks],
        )
        enforce_quality_gate(report)

        await self._filings.update_status(filing_id, FilingStatus.EMBEDDED)
        return inserted
