from __future__ import annotations

import time
from datetime import date

import structlog

from finsight.domain.errors import TickerNotInUniverseError
from finsight.domain.types import RetrievedChunk, Tenant, ToolCall
from finsight.retrieval.searcher import SemanticSearcher

log = structlog.get_logger(__name__)

TOOL_DEFINITIONS = [
    {
        "name": "search_filings",
        "description": (
            "Semantic search over SEC filing content (10-K, 10-Q). "
            "Returns relevant text chunks with metadata. "
            "Use this to find qualitative information, risk factors, management discussion, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by ticker symbols. Optional.",
                },
                "form_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["10-K", "10-Q"]},
                    "description": "Filter by form type. Optional.",
                },
                "date_from": {
                    "type": "string",
                    "description": "Filter filings from this date (YYYY-MM-DD). Optional.",
                },
                "date_to": {
                    "type": "string",
                    "description": "Filter filings to this date (YYYY-MM-DD). Optional.",
                },
                "section": {
                    "type": "string",
                    "description": "Filter by section (risk_factors, mda, financials, etc.).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 8, max 20).",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_financial_metrics",
        "description": (
            "Extract structured financial metrics from a specific filing's"
            " MDA or financials section."
            " Use for revenue, net income, EPS, margins, guidance, and similar quantitative data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Company ticker symbol (e.g. 'AAPL')"},
                "form_type": {
                    "type": "string",
                    "enum": ["10-K", "10-Q"],
                    "description": "Filing type",
                },
                "period_of_report": {
                    "type": "string",
                    "description": "Period end date (YYYY-MM-DD)",
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Metric names to extract (e.g. ['revenue', 'net_income', 'eps'])"
                    ),
                },
            },
            "required": ["ticker", "form_type", "period_of_report", "metrics"],
        },
    },
    {
        "name": "compare_periods",
        "description": (
            "Compare a financial metric across two reporting periods for a given company. "
            "Returns delta, percent change, and supporting narrative excerpts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Company ticker symbol"},
                "metric": {"type": "string", "description": "Metric to compare"},
                "period_a": {"type": "string", "description": "Earlier period (YYYY-MM-DD)"},
                "period_b": {"type": "string", "description": "Later period (YYYY-MM-DD)"},
            },
            "required": ["ticker", "metric", "period_a", "period_b"],
        },
    },
]


class AgentTools:
    """Implements tool execution for the ReAct agent."""

    def __init__(self, searcher: SemanticSearcher, tenant: Tenant) -> None:
        self._searcher = searcher
        self._tenant = tenant
        self._retrieved_chunks: list[RetrievedChunk] = []

    def get_retrieved_chunks(self) -> list[RetrievedChunk]:
        return self._retrieved_chunks

    async def execute(self, tool_name: str, tool_input: dict) -> tuple[str, ToolCall]:
        start = time.monotonic()
        try:
            if tool_name == "search_filings":
                result, output = await self._search_filings(tool_input)
            elif tool_name == "get_financial_metrics":
                result, output = await self._get_financial_metrics(tool_input)
            elif tool_name == "compare_periods":
                result, output = await self._compare_periods(tool_input)
            else:
                result = f"Unknown tool: {tool_name}"
                output = {"error": result}
        except TickerNotInUniverseError as e:
            result = f"Access denied: {e}"
            output = {"error": result}
        except Exception as e:
            result = f"Tool execution failed: {e}"
            output = {"error": result}

        latency_ms = int((time.monotonic() - start) * 1000)
        tool_call = ToolCall(
            tool_name=tool_name,
            inputs=tool_input,
            outputs=output,
            latency_ms=latency_ms,
        )
        return result, tool_call

    async def _search_filings(self, inputs: dict) -> tuple[str, dict]:
        query = inputs["query"]
        tickers = inputs.get("tickers")
        form_types = inputs.get("form_types")
        date_from = date.fromisoformat(inputs["date_from"]) if inputs.get("date_from") else None
        date_to = date.fromisoformat(inputs["date_to"]) if inputs.get("date_to") else None
        section = inputs.get("section")
        limit = min(int(inputs.get("limit", 8)), 20)

        chunks = await self._searcher.search(
            query,
            self._tenant,
            tickers=tickers,
            form_types=form_types,
            date_from=date_from,
            date_to=date_to,
            section=section,
            limit=limit,
        )
        self._retrieved_chunks.extend(chunks)

        if not chunks:
            return "No relevant filing content found.", {"chunks": []}

        formatted = []
        for i, chunk in enumerate(chunks):
            formatted.append(
                f"[{i+1}] {chunk.ticker} {chunk.form_type} "
                f"({chunk.period_of_report}) — {chunk.section}\n"
                f"Score: {chunk.score:.3f}\n"
                f"{chunk.content[:500]}{'...' if len(chunk.content) > 500 else ''}"
            )

        result_text = "\n\n---\n\n".join(formatted)
        output = {
            "chunks": [
                {
                    "chunk_id": str(c.chunk_id),
                    "ticker": c.ticker,
                    "form_type": c.form_type,
                    "period": str(c.period_of_report),
                    "section": c.section,
                    "score": c.score,
                    "content_preview": c.content[:200],
                }
                for c in chunks
            ]
        }
        return result_text, output

    async def _get_financial_metrics(self, inputs: dict) -> tuple[str, dict]:
        ticker = inputs["ticker"].upper()
        if ticker not in [t.upper() for t in self._tenant.ticker_universe]:
            raise TickerNotInUniverseError(ticker)

        metrics_str = ", ".join(inputs["metrics"])
        query = f"{metrics_str} for {ticker} {inputs['form_type']} {inputs['period_of_report']}"
        chunks = await self._searcher.search(
            query,
            self._tenant,
            tickers=[ticker],
            form_types=[inputs["form_type"]],
            date_from=date.fromisoformat(inputs["period_of_report"]),
            date_to=date.fromisoformat(inputs["period_of_report"]),
            section="financials",
            limit=5,
        )
        self._retrieved_chunks.extend(chunks)

        if not chunks:
            chunks = await self._searcher.search(
                query,
                self._tenant,
                tickers=[ticker],
                form_types=[inputs["form_type"]],
                section="mda",
                limit=5,
            )
            self._retrieved_chunks.extend(chunks)

        if not chunks:
            period = inputs["period_of_report"]
            return f"No financial data found for {ticker} {inputs['form_type']} {period}", {}

        combined = "\n\n".join(c.content for c in chunks[:3])
        return combined[:2000], {
            "ticker": ticker,
            "form_type": inputs["form_type"],
            "period_of_report": inputs["period_of_report"],
            "content": combined[:2000],
        }

    async def _compare_periods(self, inputs: dict) -> tuple[str, dict]:
        ticker = inputs["ticker"].upper()
        if ticker not in [t.upper() for t in self._tenant.ticker_universe]:
            raise TickerNotInUniverseError(ticker)

        metric = inputs["metric"]
        period_a = inputs["period_a"]
        period_b = inputs["period_b"]

        chunks_a = await self._searcher.search(
            f"{metric} {ticker}", self._tenant, tickers=[ticker],
            date_from=date.fromisoformat(period_a), date_to=date.fromisoformat(period_a),
            section="mda", limit=3,
        )
        chunks_b = await self._searcher.search(
            f"{metric} {ticker}", self._tenant, tickers=[ticker],
            date_from=date.fromisoformat(period_b), date_to=date.fromisoformat(period_b),
            section="mda", limit=3,
        )
        self._retrieved_chunks.extend(chunks_a + chunks_b)

        result = (
            f"Comparison of '{metric}' for {ticker}:\n\n"
            f"Period A ({period_a}):\n{chunks_a[0].content[:500] if chunks_a else 'No data'}\n\n"
            f"Period B ({period_b}):\n{chunks_b[0].content[:500] if chunks_b else 'No data'}"
        )
        return result, {
            "ticker": ticker,
            "metric": metric,
            "period_a": period_a,
            "period_b": period_b,
            "period_a_content": chunks_a[0].content[:500] if chunks_a else None,
            "period_b_content": chunks_b[0].content[:500] if chunks_b else None,
        }
