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


def backfill_ingest(**context):
    """Backfill ingestion for a date range and list of tickers."""
    import asyncio
    import sys
    from datetime import date

    sys.path.insert(0, "/opt/airflow")
    from finsight.database.connection import get_pool
    from finsight.database.filing_store import FilingStore
    from finsight.ingestion.downloader import FilingDownloader
    from finsight.ingestion.edgar_client import EDGARClient
    from finsight.storage.object_store import MinIOStore

    conf = context.get("dag_run", {}).conf or {}
    tickers = conf.get("tickers", ["AAPL"])
    date_from = date.fromisoformat(conf.get("date_from", "2024-01-01"))
    date_to = date.fromisoformat(conf.get("date_to", "2024-12-31"))

    async def run():
        pool = await get_pool()
        filing_store = FilingStore(pool)
        edgar = EDGARClient()
        objects = MinIOStore()
        downloader = FilingDownloader(edgar, filing_store, objects)

        downloaded = 0
        skipped = 0
        for ticker in tickers:
            filings = await edgar.search_filings(
                ticker,
                form_types=["10-K", "10-Q"],
                date_from=date_from,
                date_to=date_to,
            )
            print(f"{ticker}: found {len(filings)} filings in range")
            for filing in filings:
                _, was_downloaded = await downloader.download(filing)
                if was_downloaded:
                    downloaded += 1
                else:
                    skipped += 1

        print(f"Backfill complete: {downloaded} downloaded, {skipped} skipped (idempotent)")
        return {"downloaded": downloaded, "skipped": skipped}

    result = asyncio.run(run())
    context["task_instance"].xcom_push(key="result", value=result)


with DAG(
    "edgar_backfill",
    default_args=default_args,
    description="On-demand EDGAR backfill (idempotent)",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["finsight", "backfill"],
) as dag:
    ingest = PythonOperator(
        task_id="backfill_ingest",
        python_callable=backfill_ingest,
    )

    trigger_transform = TriggerDagRunOperator(
        task_id="trigger_transform_dag",
        trigger_dag_id="edgar_transform",
        wait_for_completion=False,
    )

    ingest >> trigger_transform
