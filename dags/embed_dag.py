from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "finsight",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def embed_and_upsert(**context):
    """Generate embeddings and upsert to pgvector."""
    import asyncio
    import sys

    sys.path.insert(0, "/opt/airflow")
    from finsight.database.chunk_store import ChunkStore
    from finsight.database.connection import get_pool
    from finsight.database.filing_store import FilingStore
    from finsight.domain.types import FilingStatus
    from finsight.embedding.embedder import Embedder
    from finsight.embedding.pipeline import EmbedPipeline
    from finsight.storage.object_store import MinIOStore
    from finsight.storage.parquet_store import ParquetStore

    async def run():
        pool = await get_pool()
        filing_store = FilingStore(pool)
        chunk_store = ChunkStore(pool)
        embedder = Embedder()
        objects = MinIOStore()
        parquet_store = ParquetStore(objects)

        pipeline = EmbedPipeline(embedder, chunk_store, filing_store, parquet_store)
        filings, _ = await filing_store.list_filings(status=FilingStatus.TRANSFORMED)
        embedded = 0

        for filing in filings:
            try:
                count = await pipeline.run(filing.id)
                embedded += count
                print(f"Embedded {filing.accession_number}: {count} chunks")
            except Exception as e:
                await filing_store.update_status(
                    filing.id, FilingStatus.FAILED, error_message=str(e)
                )
                print(f"Error embedding {filing.accession_number}: {e}")

        return embedded

    return asyncio.run(run())


with DAG(
    "edgar_embed",
    default_args=default_args,
    description="Generate embeddings and upsert to pgvector",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["finsight", "embedding"],
) as dag:
    embed = PythonOperator(
        task_id="embed_and_upsert",
        python_callable=embed_and_upsert,
    )
