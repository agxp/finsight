from __future__ import annotations

import structlog

from finsight.database.filing_store import FilingStore
from finsight.domain.errors import EDGARError
from finsight.domain.types import FilingStatus
from finsight.ingestion.edgar_client import EDGARClient, EDGARFiling
from finsight.storage.object_store import MinIOStore

log = structlog.get_logger(__name__)


class FilingDownloader:
    """Downloads raw filings from EDGAR with idempotency guard."""

    def __init__(
        self,
        edgar_client: EDGARClient,
        filing_store: FilingStore,
        object_store: MinIOStore,
    ) -> None:
        self._edgar = edgar_client
        self._store = filing_store
        self._objects = object_store

    async def download(self, filing: EDGARFiling) -> tuple[str, bool]:
        """
        Download and store a filing. Returns (filing_id, was_downloaded).
        Idempotent: if already ingested or beyond, skip.
        """
        db_filing, created = await self._store.upsert_filing(
            accession_number=filing.accession_number,
            ticker=filing.ticker,
            cik=filing.cik,
            form_type=filing.form_type,
            period_of_report=filing.period_of_report,
            filed_date=filing.filed_date,
        )

        # Idempotency: skip if already processed past ingestion
        if not created and db_filing.status not in (
            FilingStatus.PENDING,
            FilingStatus.FAILED,
        ):
            log.info(
                "skipping already-processed filing",
                accession=filing.accession_number,
                status=db_filing.status,
            )
            return str(db_filing.id), False

        filing_id = db_filing.id
        s3_key = f"raw/{filing.cik}/{filing.accession_number.replace('-', '')}/filing.html"

        try:
            if not await self._objects.exists(s3_key):
                log.info("fetching filing from EDGAR", accession=filing.accession_number)
                html_bytes = await self._edgar.fetch_filing_html(filing)

                if len(html_bytes) < 10_000:
                    raise EDGARError(
                        f"Filing content too small: {len(html_bytes)} bytes "
                        f"(accession={filing.accession_number})"
                    )

                await self._objects.put(s3_key, html_bytes, content_type="text/html")
                log.info(
                    "filing stored",
                    accession=filing.accession_number,
                    bytes=len(html_bytes),
                    s3_key=s3_key,
                )

            await self._store.update_status(
                filing_id, FilingStatus.INGESTED, raw_s3_key=s3_key
            )
            return str(filing_id), True

        except Exception as e:
            await self._store.update_status(
                filing_id, FilingStatus.FAILED, error_message=str(e)
            )
            log.error(
                "filing download failed",
                accession=filing.accession_number,
                error=str(e),
            )
            raise
