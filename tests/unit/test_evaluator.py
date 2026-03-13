from __future__ import annotations

import uuid
from datetime import date

from finsight.agent.evaluator import ResponseEvaluator
from finsight.domain.types import AgentResponse, RetrievedChunk, ToolCall


def make_chunk(ticker: str, period: date, content: str, score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        filing_id=uuid.uuid4(),
        ticker=ticker,
        form_type="10-K",
        period_of_report=period,
        section="mda",
        content=content,
        score=score,
    )


def make_tool_call(name: str = "search_filings") -> ToolCall:
    return ToolCall(tool_name=name, inputs={}, outputs={}, latency_ms=100)


def make_response(**kwargs) -> AgentResponse:
    defaults = dict(
        query="What was Apple's revenue?",
        answer="AAPL reported revenue of $383 billion in 2023.",
        sources=[],
        tool_calls=[make_tool_call()],
        input_tokens=500,
        output_tokens=100,
        latency_ms=1000,
    )
    return AgentResponse(**(defaults | kwargs))


evaluator = ResponseEvaluator()


def test_basic_metrics_present():
    r = make_response()
    m = evaluator.compute_metrics(r)
    expected = {
        "source_count", "avg_retrieval_score", "min_retrieval_score", "max_retrieval_score",
        "citation_coverage", "source_diversity", "grounding_score",
        "has_numeric_data", "answer_chars", "tool_call_count",
        "tool_efficiency", "throughput_tokens_per_ms",
    }
    assert expected == m.keys()


def test_no_sources_returns_zero_retrieval_metrics():
    m = evaluator.compute_metrics(make_response(sources=[]))
    assert m["source_count"] == 0.0
    assert m["avg_retrieval_score"] == 0.0
    assert m["citation_coverage"] == 0.0
    assert m["grounding_score"] == 0.0


def test_citation_coverage_full():
    period = date(2023, 9, 30)
    chunk = make_chunk("AAPL", period, "Revenue grew significantly.", score=0.85)
    answer = "AAPL's revenue in 2023 was $383 billion."
    m = evaluator.compute_metrics(make_response(answer=answer, sources=[chunk]))
    assert m["citation_coverage"] == 1.0


def test_citation_coverage_partial():
    chunks = [
        make_chunk("AAPL", date(2023, 9, 30), "Apple revenue data."),
        make_chunk("MSFT", date(2023, 6, 30), "Microsoft cloud revenue."),
    ]
    # Only mentions AAPL/2023, not MSFT
    answer = "AAPL had strong earnings in 2023."
    m = evaluator.compute_metrics(make_response(answer=answer, sources=chunks))
    assert m["citation_coverage"] == 0.5


def test_has_numeric_data_detected():
    m = evaluator.compute_metrics(make_response(answer="Revenue was $10.5 billion, up 12%."))
    assert m["has_numeric_data"] == 1.0


def test_no_numeric_data():
    answer = "Revenue grew significantly year over year."
    m = evaluator.compute_metrics(make_response(answer=answer))
    assert m["has_numeric_data"] == 0.0


def test_grounding_score_nonzero_with_sources():
    chunk = make_chunk("AAPL", date(2023, 9, 30), "Apple revenue grew to record levels.")
    answer = "AAPL revenue grew strongly."
    m = evaluator.compute_metrics(make_response(answer=answer, sources=[chunk]))
    assert m["grounding_score"] > 0.0


def test_tool_efficiency():
    chunks = [
        make_chunk("AAPL", date(2023, 9, 30), "content"),
        make_chunk("AAPL", date(2023, 9, 30), "content"),
    ]
    r = make_response(sources=chunks, tool_calls=[make_tool_call()])
    m = evaluator.compute_metrics(r)
    assert m["tool_efficiency"] == 2.0  # 2 sources / 1 tool call


def test_throughput():
    r = make_response(input_tokens=400, output_tokens=100, latency_ms=500)
    m = evaluator.compute_metrics(r)
    assert m["throughput_tokens_per_ms"] == 1.0  # 500 tokens / 500 ms


def test_source_diversity_all_unique():
    chunks = [
        make_chunk("AAPL", date(2023, 9, 30), "a"),
        make_chunk("MSFT", date(2023, 6, 30), "b"),
    ]
    m = evaluator.compute_metrics(make_response(sources=chunks))
    assert m["source_diversity"] == 1.0


def test_source_diversity_all_same():
    period = date(2023, 9, 30)
    chunks = [make_chunk("AAPL", period, "a"), make_chunk("AAPL", period, "b")]
    m = evaluator.compute_metrics(make_response(sources=chunks))
    assert m["source_diversity"] == 0.5  # 1 unique / 2 total
