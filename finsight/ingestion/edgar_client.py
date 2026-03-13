from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import date

import httpx
import structlog

from finsight.config import get_settings
from finsight.domain.errors import EDGARError

log = structlog.get_logger(__name__)

EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"


@dataclass
class EDGARFiling:
    accession_number: str
    ticker: str
    cik: str
    form_type: str
    period_of_report: date
    filed_date: date
    document_url: str


class EDGARClient:
    """Rate-limited EDGAR API client. Max 8 req/s per SEC policy."""

    def __init__(self) -> None:
        settings = get_settings()
        self._user_agent = settings.edgar_user_agent
        self._rate_limit = settings.edgar_rate_limit_rps
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    def _make_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._user_agent,
            "Accept": "application/json",
        }

    async def _throttle(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = (1.0 / self._rate_limit) - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def get_cik_for_ticker(self, ticker: str) -> str:
        """Look up CIK for a ticker symbol."""
        await self._throttle()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "company": "",
                    "CIK": ticker,
                    "type": "",
                    "dateb": "",
                    "owner": "include",
                    "count": "1",
                    "search_text": "",
                    "action": "getcompany",
                    "output": "atom",
                },
                headers=self._make_headers(),
                timeout=30,
            )
        if r.status_code != 200:
            return await self._get_cik_from_tickers_json(ticker)

        match = re.search(r"CIK=(\d+)", r.text)
        if not match:
            return await self._get_cik_from_tickers_json(ticker)
        return match.group(1).lstrip("0")

    async def _get_cik_from_tickers_json(self, ticker: str) -> str:
        """Get CIK using the company_tickers.json endpoint."""
        await self._throttle()
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=self._make_headers(),
                timeout=30,
            )
        if r.status_code != 200:
            raise EDGARError(f"Failed to fetch company tickers: HTTP {r.status_code}")

        data = r.json()
        ticker_upper = ticker.upper()
        for item in data.values():
            if item.get("ticker", "").upper() == ticker_upper:
                return str(item["cik_str"])

        raise EDGARError(f"Ticker '{ticker}' not found in EDGAR")

    async def search_filings(
        self,
        ticker: str,
        form_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[EDGARFiling]:
        """Search EDGAR for filings matching the given criteria."""
        cik = await self.get_cik_for_ticker(ticker)
        return await self.get_filings_for_cik(
            cik, ticker, form_types=form_types, date_from=date_from, date_to=date_to
        )

    async def get_filings_for_cik(
        self,
        cik: str,
        ticker: str,
        form_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[EDGARFiling]:
        """Fetch submissions for a CIK and filter by form type and date."""
        await self._throttle()
        padded_cik = cik.zfill(10)

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{EDGAR_SUBMISSIONS}/CIK{padded_cik}.json",
                headers=self._make_headers(),
                timeout=30,
            )

        if r.status_code != 200:
            raise EDGARError(f"Failed to fetch submissions for CIK {cik}: HTTP {r.status_code}")

        data = r.json()
        recent = data.get("filings", {}).get("recent", {})

        form_types_set = set(form_types or ["10-K", "10-Q"])
        filings: list[EDGARFiling] = []

        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        filed_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        primary_docs = recent.get("primaryDocument", [])

        for i, form in enumerate(forms):
            if form not in form_types_set:
                continue

            raw_accession = accessions[i]
            filed_str = filed_dates[i]
            report_str = report_dates[i] if i < len(report_dates) else filed_str
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""

            filed = date.fromisoformat(filed_str)
            try:
                period = date.fromisoformat(report_str) if report_str else filed
            except ValueError:
                period = filed

            if date_from and filed < date_from:
                continue
            if date_to and filed > date_to:
                continue

            accession_clean = raw_accession.replace("-", "")
            filing_url = (
                f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                f"{accession_clean}/{primary_doc}"
            )

            filings.append(
                EDGARFiling(
                    accession_number=raw_accession,
                    ticker=ticker,
                    cik=cik,
                    form_type=form,
                    period_of_report=period,
                    filed_date=filed,
                    document_url=filing_url,
                )
            )

        return filings

    async def fetch_filing_html(self, filing: EDGARFiling) -> bytes:
        """Download raw HTML/HTM content of a filing."""
        await self._throttle()
        cik = filing.cik
        accession_clean = filing.accession_number.replace("-", "")
        index_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_clean}/"
        urls_to_try = [filing.document_url]

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                idx_r = await client.get(
                    index_url + "index.json",
                    headers=self._make_headers(),
                    timeout=30,
                )
                if idx_r.status_code == 200:
                    idx_data = idx_r.json()
                    candidates = []
                    for item in idx_data.get("directory", {}).get("item", []):
                        name = item.get("name", "")
                        if (name.endswith(".htm") or name.endswith(".html")) and \
                                "index" not in name.lower():
                            try:
                                size = int(item.get("size", 0))
                            except (ValueError, TypeError):
                                size = 0
                            candidates.append((size, index_url + name))
                    # prefer the largest non-index htm (the actual filing document)
                    if candidates:
                        candidates.sort(reverse=True)
                        urls_to_try.insert(0, candidates[0][1])
            except Exception as exc:
                log.debug(
                    "edgar.index_json_fetch_failed",
                    accession=filing.accession_number,
                    error=str(exc),
                )

            for url in urls_to_try:
                if not url:
                    continue
                try:
                    r = await client.get(url, headers=self._make_headers(), timeout=60)
                    if r.status_code == 200 and len(r.content) > 10_000:
                        return r.content
                except Exception as exc:
                    log.debug(
                        "edgar.filing_url_fetch_failed",
                        url=url,
                        accession=filing.accession_number,
                        error=str(exc),
                    )
                    continue

        raise EDGARError(f"Failed to fetch HTML for filing {filing.accession_number}")


def _quarter_str(month: int) -> str:
    return f"QTR{(month - 1) // 3 + 1}"
