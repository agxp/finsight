"""
Integration tests for the ingestion pipeline.
Requires: real PostgreSQL with pgvector, real MinIO.
LLM/EDGAR calls are mocked.

Run with: pytest tests/integration/ -v -m integration
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from finsight.domain.types import FilingStatus


@pytest.mark.asyncio
@pytest.mark.integration
async def test_idempotency_second_ingest_skips(filing_store, minio_store, edgar_client_mock):
    """Re-ingesting the same accession number is a no-op."""
    from finsight.ingestion.downloader import FilingDownloader
    from finsight.ingestion.edgar_client import EDGARFiling

    filing = EDGARFiling(
        accession_number="0000320193-24-000123",
        ticker="AAPL",
        cik="320193",
        form_type="10-K",
        period_of_report=date(2024, 9, 28),
        filed_date=date(2024, 10, 30),
        document_url="https://example.com/filing.htm",
    )

    edgar_client_mock.fetch_filing_html = AsyncMock(
        return_value=b"<html>" + b"x" * 20_000 + b"</html>"
    )

    downloader = FilingDownloader(edgar_client_mock, filing_store, minio_store)

    filing_id_1, was_downloaded_1 = await downloader.download(filing)
    assert was_downloaded_1

    filing_id_2, was_downloaded_2 = await downloader.download(filing)
    assert not was_downloaded_2
    assert filing_id_1 == filing_id_2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_failed_filing_can_be_retried(filing_store, minio_store, edgar_client_mock):
    """A filing with status=failed can be re-downloaded."""
    from finsight.ingestion.downloader import FilingDownloader
    from finsight.ingestion.edgar_client import EDGARFiling

    filing = EDGARFiling(
        accession_number="0000320193-24-000456",
        ticker="AAPL",
        cik="320193",
        form_type="10-Q",
        period_of_report=date(2024, 6, 29),
        filed_date=date(2024, 8, 1),
        document_url="https://example.com/filing2.htm",
    )

    edgar_client_mock.fetch_filing_html = AsyncMock(side_effect=Exception("Network error"))
    downloader = FilingDownloader(edgar_client_mock, filing_store, minio_store)

    with pytest.raises(Exception):
        await downloader.download(filing)

    db_filing = await filing_store.get_by_accession(filing.accession_number)
    assert db_filing.status == FilingStatus.FAILED

    edgar_client_mock.fetch_filing_html = AsyncMock(
        return_value=b"<html>" + b"x" * 20_000 + b"</html>"
    )
    _, was_downloaded = await downloader.download(filing)
    assert was_downloaded
