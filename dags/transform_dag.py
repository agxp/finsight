from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

default_args = {
    "owner": "finsight",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def parse_and_chunk(**context):
    """Parse HTML filings and chunk into sections."""
    import asyncio
    import sys

    sys.path.insert(0, "/opt/airflow")
    from finsight.database.connection import get_pool
    from finsight.database.filing_store import FilingStore
    from finsight.domain.types import FilingStatus
    from finsight.quality.checks import check_transform, enforce_quality_gate
    from finsight.quality.reporter import log_report
    from finsight.storage.object_store import MinIOStore
    from finsight.storage.parquet_store import ParquetStore
    from finsight.transform.chunker import chunk_sections
    from finsight.transform.html_parser import get_section_coverage, parse_filing_html
    from finsight.transform.parquet_writer import write_chunks_to_parquet

    async def run():
        pool = await get_pool()
        filing_store = FilingStore(pool)
        objects = MinIOStore()
        parquet_store = ParquetStore(objects)

        filings, _ = await filing_store.list_filings(status=FilingStatus.INGESTED)
        processed = 0

        for filing in filings:
            try:
                if not filing.raw_s3_key:
                    continue

                html_bytes = await objects.get(filing.raw_s3_key)
                sections = parse_filing_html(html_bytes)
                sections_found = get_section_coverage(sections)
                chunks = chunk_sections(sections)

                report = check_transform(
                    filing.id,
                    sections_found=sections_found,
                    chunk_count=len(chunks),
                )
                log_report(report)
                await filing_store.save_quality_report(
                    filing.id, report.stage.value, report.passed,
                    [c.model_dump() for c in report.checks],
                )
                enforce_quality_gate(report)

                s3_key = await write_chunks_to_parquet(chunks, filing, parquet_store)
                await filing_store.update_status(
                    filing.id, FilingStatus.TRANSFORMED, parquet_s3_key=s3_key
                )
                processed += 1
                print(f"Transformed {filing.accession_number}: {len(chunks)} chunks")

            except Exception as e:
                await filing_store.update_status(
                    filing.id, FilingStatus.FAILED, error_message=str(e)
                )
                print(f"Error transforming {filing.accession_number}: {e}")

        return processed

    return asyncio.run(run())


with DAG(
    "edgar_transform",
    default_args=default_args,
    description="Transform ingested filings into Parquet chunks",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["finsight", "transform"],
) as dag:
    transform = PythonOperator(
        task_id="parse_and_chunk",
        python_callable=parse_and_chunk,
    )

    trigger_embed = TriggerDagRunOperator(
        task_id="trigger_embed_dag",
        trigger_dag_id="edgar_embed",
        wait_for_completion=False,
    )

    transform >> trigger_embed
