from __future__ import annotations

"""
Integration tests for agent tool security boundaries.

Run with: pytest tests/integration/ -v -m integration
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from finsight.domain.types import Tenant


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tool_rejects_out_of_universe_ticker():
    """Tool call with ticker outside tenant universe is rejected."""
    from finsight.agent.tools import AgentTools
    from unittest.mock import MagicMock

    tenant = Tenant(
        id=uuid.uuid4(),
        name="test",
        api_key_hash="hash",
        ticker_universe=["AAPL", "MSFT"],
        created_at=datetime.now(timezone.utc),
    )

    searcher_mock = MagicMock()
    searcher_mock.search = AsyncMock(return_value=[])

    tools = AgentTools(searcher_mock, tenant)
    result, tc = await tools.execute("search_filings", {
        "query": "revenue",
        "tickers": ["TSLA"],
    })
    assert "denied" in result.lower() or "not in" in result.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tool_allows_in_universe_ticker():
    """Tool call with valid ticker proceeds without error."""
    from finsight.agent.tools import AgentTools
    from unittest.mock import MagicMock

    tenant = Tenant(
        id=uuid.uuid4(),
        name="test",
        api_key_hash="hash",
        ticker_universe=["AAPL", "MSFT"],
        created_at=datetime.now(timezone.utc),
    )

    searcher_mock = MagicMock()
    searcher_mock.search = AsyncMock(return_value=[])

    tools = AgentTools(searcher_mock, tenant)
    result, tc = await tools.execute("search_filings", {
        "query": "revenue growth",
        "tickers": ["AAPL"],
    })
    assert tc.tool_name == "search_filings"
