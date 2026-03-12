from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx

from finsight.domain.errors import EDGARError
from finsight.ingestion.edgar_client import EDGARClient, _quarter_str


class TestQuarterStr:
    def test_q1(self):
        assert _quarter_str(1) == "QTR1"
        assert _quarter_str(3) == "QTR1"

    def test_q2(self):
        assert _quarter_str(4) == "QTR2"
        assert _quarter_str(6) == "QTR2"

    def test_q3(self):
        assert _quarter_str(7) == "QTR3"
        assert _quarter_str(9) == "QTR3"

    def test_q4(self):
        assert _quarter_str(10) == "QTR4"
        assert _quarter_str(12) == "QTR4"


class TestEDGARClient:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_cik_from_tickers_json(self):
        tickers_data = {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        }
        respx.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=tickers_data)
        )

        client = EDGARClient()
        cik = await client._get_cik_from_tickers_json("AAPL")
        assert cik == "320193"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_cik_raises_for_unknown_ticker(self):
        tickers_data = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
        respx.get("https://www.sec.gov/files/company_tickers.json").mock(
            return_value=httpx.Response(200, json=tickers_data)
        )

        client = EDGARClient()
        with pytest.raises(EDGARError):
            await client._get_cik_from_tickers_json("UNKNOWN")

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_filings_for_cik_filters_by_form_type(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K", "10-K"],
                    "accessionNumber": ["0001-01", "0001-02", "0001-03", "0001-04"],
                    "filingDate": ["2024-10-30", "2024-08-01", "2024-07-15", "2023-11-01"],
                    "reportDate": ["2024-09-28", "2024-06-29", "2024-07-15", "2023-09-30"],
                    "primaryDocument": [
                        "aapl-10k.htm", "aapl-10q.htm", "aapl-8k.htm", "aapl-10k-2.htm"
                    ],
                }
            }
        }
        respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
            return_value=httpx.Response(200, json=submissions)
        )

        client = EDGARClient()
        filings = await client.get_filings_for_cik("320193", "AAPL", form_types=["10-K"])

        assert len(filings) == 2
        assert all(f.form_type == "10-K" for f in filings)
        assert all(f.ticker == "AAPL" for f in filings)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_filings_filters_by_date(self):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "10-K"],
                    "accessionNumber": ["0001-01", "0001-02"],
                    "filingDate": ["2024-10-30", "2022-10-30"],
                    "reportDate": ["2024-09-28", "2022-09-30"],
                    "primaryDocument": ["doc1.htm", "doc2.htm"],
                }
            }
        }
        respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
            return_value=httpx.Response(200, json=submissions)
        )

        client = EDGARClient()
        filings = await client.get_filings_for_cik(
            "320193",
            "AAPL",
            form_types=["10-K"],
            date_from=date(2024, 1, 1),
            date_to=date(2024, 12, 31),
        )

        assert len(filings) == 1
        assert filings[0].filed_date == date(2024, 10, 30)
