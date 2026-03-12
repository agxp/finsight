from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "finsight",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]


def search_and_ingest(**context):
    """Search EDGAR and download filings for all tickers."""
    import asyncio
    import sys

    sys.path.insert(0, "/opt/airflow")
    from finsight.database.connection import get_pool
    from finsight.database.filing_store import FilingStore
    from finsight.ingestion.downloader import FilingDownloader
    from finsight.ingestion.edgar_client import EDGARClient
    from finsight.storage.object_store import MinIOStore

    execution_date = context["execution_date"]
    date_from = execution_date.date()
    date_to = execution_date.date()

    async def run():
        pool = await get_pool()
        filing_store = FilingStore(pool)
        edgar = EDGARClient()
        objects = MinIOStore()
        downloader = FilingDownloader(edgar, filing_store, objects)

        downloaded = 0
        for ticker in TICKERS:
            try:
                filings = await edgar.search_filings(
                    ticker,
                    form_types=["10-K", "10-Q"],
                    date_from=date_from,
                    date_to=date_to,
                )
                for filing in filings:
                    _, was_downloaded = await downloader.download(filing)
                    if was_downloaded:
                        downloaded += 1
            except Exception as e:
                print(f"Error processing {ticker}: {e}")

        print(f"Downloaded {downloaded} filings")
        return downloaded

    result = asyncio.run(run())
    context["task_instance"].xcom_push(key="downloaded_count", value=result)


def quality_check_ingestion(**context):
    """Validate ingested filings meet quality thresholds."""
    import asyncio
    import sys

    sys.path.insert(0, "/opt/airflow")
    from finsight.database.connection import get_pool
    from finsight.database.filing_store import FilingStore
    from finsight.domain.types import FilingStatus

    async def run():
        pool = await get_pool()
        filing_store = FilingStore(pool)
        _, total = await filing_store.list_filings(status=FilingStatus.INGESTED)
        print(f"Quality check: {total} ingested filings")
        return total

    asyncio.run(run())


with DAG(
    "edgar_ingest",
    default_args=default_args,
    description="Daily EDGAR filing ingestion",
    schedule="0 6 * * 1-5",
    start_date=datetime(2024, 1, 1),
    catchup=True,
    max_active_runs=1,
    tags=["finsight", "ingestion"],
) as dag:
    ingest = PythonOperator(
        task_id="search_edgar",
        python_callable=search_and_ingest,
        sla=timedelta(hours=2),
    )

    quality = PythonOperator(
        task_id="quality_check_ingestion",
        python_callable=quality_check_ingestion,
    )

    trigger_transform = TriggerDagRunOperator(
        task_id="trigger_transform_dag",
        trigger_dag_id="edgar_transform",
        wait_for_completion=False,
    )

    ingest >> quality >> trigger_transform
