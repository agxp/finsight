from __future__ import annotations

import uuid

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from finsight.api.middleware.auth import get_current_tenant
from finsight.config import get_settings
from finsight.database.filing_store import FilingStore
from finsight.domain.types import Filing, FilingListResponse, FilingStatus, IngestRequest, Tenant

router = APIRouter(prefix="/v1/filings")
log = structlog.get_logger(__name__)

_BACKFILL_DAG_ID = "edgar_backfill"


@router.get("", response_model=FilingListResponse)
async def list_filings(
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
    ticker: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> FilingListResponse:
    filing_store: FilingStore = request.app.state.filing_store

    filing_status = None
    if status_filter:
        try:
            filing_status = FilingStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    if ticker and ticker.upper() not in [t.upper() for t in tenant.ticker_universe]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Ticker '{ticker}' not in your authorized universe",
        )

    filings, total = await filing_store.list_filings(
        ticker=ticker,
        status=filing_status,
        page=page,
        page_size=page_size,
    )
    return FilingListResponse(filings=filings, total=total, page=page, page_size=page_size)


@router.get("/{filing_id}", response_model=Filing)
async def get_filing(
    filing_id: uuid.UUID,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
) -> Filing:
    filing_store: FilingStore = request.app.state.filing_store
    filing = await filing_store.get_by_id(filing_id)
    if filing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing not found")

    if filing.ticker.upper() not in [t.upper() for t in tenant.ticker_universe]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return filing


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def trigger_ingest(
    body: IngestRequest,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict:
    if body.ticker.upper() not in [t.upper() for t in tenant.ticker_universe]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Ticker '{body.ticker}' not in your authorized universe",
        )

    settings = get_settings()
    dag_run_id = f"api_{body.ticker.lower()}_{body.date_from}_{body.date_to}"
    payload = {
        "dag_run_id": dag_run_id,
        "conf": {
            "tickers": [body.ticker.upper()],
            "date_from": body.date_from,
            "date_to": body.date_to,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{settings.airflow_api_url}/dags/{_BACKFILL_DAG_ID}/dagRuns",
                json=payload,
                auth=(settings.airflow_api_user, settings.airflow_api_password),
            )
        if r.status_code == 409:
            # DAG run with this ID already exists — idempotent, treat as accepted.
            log.info(
                "ingest.dag_run_already_exists",
                dag_run_id=dag_run_id,
                ticker=body.ticker,
            )
        elif r.status_code not in (200, 201):
            log.error(
                "ingest.airflow_trigger_failed",
                status=r.status_code,
                body=r.text,
                ticker=body.ticker,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Airflow returned {r.status_code}: {r.text}",
            )
        else:
            log.info(
                "ingest.dag_run_triggered",
                dag_run_id=dag_run_id,
                ticker=body.ticker,
            )
    except httpx.RequestError as exc:
        log.error("ingest.airflow_unreachable", error=str(exc), ticker=body.ticker)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Airflow is unreachable. Is it running?",
        ) from exc

    return {
        "status": "accepted",
        "dag_run_id": dag_run_id,
        "ticker": body.ticker,
        "date_from": body.date_from,
        "date_to": body.date_to,
    }
