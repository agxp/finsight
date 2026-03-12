from __future__ import annotations

from finsight.domain.types import AgentResponse


class ResponseEvaluator:
    """
    Evaluates agent response quality.
    Currently stubs — no ground truth dataset yet.
    """

    def compute_metrics(self, response: AgentResponse) -> dict[str, float]:
        """Return quality metrics for a response."""
        return {
            "source_count": float(len(response.sources)),
            "avg_retrieval_score": (
                sum(s.score for s in response.sources) / len(response.sources)
                if response.sources
                else 0.0
            ),
            "tool_call_count": float(len(response.tool_calls)),
            "answer_length": float(len(response.answer)),
            "tokens_per_ms": (
                (response.input_tokens + response.output_tokens) / response.latency_ms
                if response.latency_ms > 0
                else 0.0
            ),
        }
