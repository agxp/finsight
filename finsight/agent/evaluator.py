from __future__ import annotations

import re

from finsight.domain.types import AgentResponse

# Tokenise to lowercase words for overlap calculations.
_WORD_RE = re.compile(r"[a-z0-9]+")
# Financial figures: integers, decimals, percentages, $-prefixed values.
_NUMERIC_RE = re.compile(r"(\$[\d,.]+|\d[\d,.]*%?)")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


class ResponseEvaluator:
    """
    Evaluates agent response quality using deterministic heuristics.
    No ground-truth dataset required.
    """

    def compute_metrics(self, response: AgentResponse) -> dict[str, float]:
        """Return quality metrics for a response."""
        sources = response.sources
        answer = response.answer
        tool_calls = response.tool_calls

        # ------------------------------------------------------------------
        # Retrieval metrics
        # ------------------------------------------------------------------
        source_count = float(len(sources))
        scores = [s.score for s in sources]
        avg_retrieval_score = sum(scores) / len(scores) if scores else 0.0
        min_retrieval_score = min(scores) if scores else 0.0
        max_retrieval_score = max(scores) if scores else 0.0

        # ------------------------------------------------------------------
        # Citation coverage — fraction of retrieved (ticker, period) pairs
        # that appear verbatim in the answer.
        # ------------------------------------------------------------------
        if sources:
            cited = sum(
                1
                for s in sources
                if s.ticker.upper() in answer.upper()
                and str(s.period_of_report.year) in answer
            )
            citation_coverage = cited / len(sources)
        else:
            citation_coverage = 0.0

        # ------------------------------------------------------------------
        # Source diversity — unique (ticker, form_type, period) combos.
        # Normalised to [0, 1] relative to source count.
        # ------------------------------------------------------------------
        if sources:
            unique_sources = len({(s.ticker, s.form_type, s.period_of_report) for s in sources})
            source_diversity = unique_sources / len(sources)
        else:
            source_diversity = 0.0

        # ------------------------------------------------------------------
        # Grounding score — Jaccard overlap between answer words and the
        # union of all retrieved chunk content words.
        # ------------------------------------------------------------------
        if sources:
            corpus_words = set()
            for s in sources:
                corpus_words |= _words(s.content)
            answer_words = _words(answer)
            intersection = answer_words & corpus_words
            union = answer_words | corpus_words
            grounding_score = len(intersection) / len(union) if union else 0.0
        else:
            grounding_score = 0.0

        # ------------------------------------------------------------------
        # Numeric presence — financial answers should contain figures.
        # ------------------------------------------------------------------
        has_numeric_data = 1.0 if _NUMERIC_RE.search(answer) else 0.0

        # ------------------------------------------------------------------
        # Tool efficiency — sources retrieved per tool call.
        # Rewards finding relevant content without excessive calls.
        # ------------------------------------------------------------------
        tool_efficiency = source_count / len(tool_calls) if tool_calls else 0.0

        # ------------------------------------------------------------------
        # Throughput
        # ------------------------------------------------------------------
        throughput_tokens_per_ms = (
            (response.input_tokens + response.output_tokens) / response.latency_ms
            if response.latency_ms > 0
            else 0.0
        )

        return {
            # Retrieval
            "source_count": source_count,
            "avg_retrieval_score": avg_retrieval_score,
            "min_retrieval_score": min_retrieval_score,
            "max_retrieval_score": max_retrieval_score,
            # Grounding & citation
            "citation_coverage": citation_coverage,
            "source_diversity": source_diversity,
            "grounding_score": grounding_score,
            # Answer quality
            "has_numeric_data": has_numeric_data,
            "answer_chars": float(len(answer)),
            # Efficiency
            "tool_call_count": float(len(tool_calls)),
            "tool_efficiency": tool_efficiency,
            "throughput_tokens_per_ms": throughput_tokens_per_ms,
        }
