from __future__ import annotations

from datetime import date

from finsight.database.chunk_store import ChunkStore
from finsight.domain.errors import TickerNotInUniverseError
from finsight.domain.types import RetrievedChunk, Tenant
from finsight.embedding.embedder import Embedder


class SemanticSearcher:
    """Semantic search over pgvector with tenant-scoped filtering."""

    def __init__(self, embedder: Embedder, chunk_store: ChunkStore) -> None:
        self._embedder = embedder
        self._chunks = chunk_store

    async def search(
        self,
        query: str,
        tenant: Tenant,
        *,
        tickers: list[str] | None = None,
        form_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        section: str | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        if tickers:
            for ticker in tickers:
                if ticker.upper() not in [t.upper() for t in tenant.ticker_universe]:
                    raise TickerNotInUniverseError(ticker)
            tickers = [t.upper() for t in tickers]
        else:
            tickers = [t.upper() for t in tenant.ticker_universe]

        query_embedding = await self._embedder.embed_single(query)

        return await self._chunks.semantic_search(
            query_embedding,
            ticker_filter=tickers,
            form_type_filter=form_types,
            date_from=date_from,
            date_to=date_to,
            section_filter=section,
            limit=limit,
        )
