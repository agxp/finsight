from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from finsight.domain.types import Tenant


@pytest.fixture
def sample_tenant() -> Tenant:
    return Tenant(
        id=uuid.uuid4(),
        name="test-tenant",
        api_key_hash="abc123",
        ticker_universe=["AAPL", "MSFT", "GOOGL"],
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_filing_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Integration test fixtures
# These require live Postgres + MinIO. Skipped automatically in CI
# (CI only runs `pytest tests/unit/`).
# ---------------------------------------------------------------------------


@pytest.fixture
def edgar_client_mock():
    """Mock EDGAR client for integration tests."""
    mock = MagicMock()
    mock.fetch_filing_html = AsyncMock(return_value=b"<html>" + b"x" * 20_000 + b"</html>")
    mock.search_filings = AsyncMock(return_value=[])
    mock.get_cik_for_ticker = AsyncMock(return_value="320193")
    return mock


@pytest.fixture
def searcher_mock():
    """Mock SemanticSearcher for integration tests."""
    mock = MagicMock()
    mock.search = AsyncMock(return_value=[])
    return mock


# filing_store, minio_store, chunk_store etc. are left as undefined fixtures
# so integration tests fail with a clear "fixture not found" message when
# run without a live environment rather than an import error.
