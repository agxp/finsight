from __future__ import annotations

import structlog
from openai import AsyncOpenAI

from finsight.config import get_settings
from finsight.domain.errors import EmbeddingError

log = structlog.get_logger(__name__)


class Embedder:
    """Batch embedder using OpenAI text-embedding-3-small."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._batch_size = settings.embedding_batch_size

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts in batches. Returns list of embedding vectors."""
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            log.debug("embedding batch", batch_size=len(batch), offset=i)
            embeddings = await self._embed_batch(batch)
            all_embeddings.extend(embeddings)

        return all_embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        results = await self.embed_texts([text])
        return results[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model,
                dimensions=self._dimensions,
            )
            sorted_data = sorted(response.data, key=lambda d: d.index)
            embeddings = [d.embedding for d in sorted_data]

            for emb in embeddings:
                if len(emb) != self._dimensions:
                    raise EmbeddingError(
                        f"Unexpected embedding dimension: {len(emb)} (expected {self._dimensions})"
                    )

            return embeddings
        except EmbeddingError:
            raise
        except Exception as e:
            raise EmbeddingError("Embedding API call failed") from e
