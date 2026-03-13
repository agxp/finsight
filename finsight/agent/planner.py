from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any, cast

import anthropic
import structlog

from finsight.agent.guardrails import validate_input, validate_output
from finsight.agent.tools import TOOL_DEFINITIONS, AgentTools
from finsight.config import get_settings
from finsight.database.audit_store import AuditStore
from finsight.domain.errors import GuardrailViolationError
from finsight.domain.types import AgentResponse, Tenant

log = structlog.get_logger(__name__)

SYSTEM_PROMPT = """\
You are FinSight, a financial research assistant specializing in SEC filings analysis.

You have access to a database of SEC 10-K and 10-Q filings. Use the provided tools to search \
for relevant information before answering.

Guidelines:
- Always search for relevant filings before answering — do not answer from memory alone
- Cite your sources: reference the ticker, form type, and period when quoting content
- Be precise with financial figures — only state numbers you found in the filings
- If information is not available in the filing database, say so clearly
- Current date: {current_date}
- Your authorized ticker universe: {ticker_universe}

You can only discuss companies in your authorized ticker universe."""


class ReActPlanner:
    """Stateless ReAct loop using Claude tool use."""

    def __init__(
        self,
        agent_tools: AgentTools,
        audit_store: AuditStore,
        tenant: Tenant,
    ) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.agent_model
        self._max_iterations = settings.agent_max_iterations
        self._tools = agent_tools
        self._audit = audit_store
        self._tenant = tenant

    async def run(self, query: str) -> AgentResponse:
        """Execute the full ReAct loop and return a final AgentResponse."""
        start = time.monotonic()
        guardrail_flags = validate_input(query)

        system = SYSTEM_PROMPT.format(
            current_date=date.today().isoformat(),
            ticker_universe=", ".join(self._tenant.ticker_universe),
        )

        messages: list[Any] = [{"role": "user", "content": query}]
        from finsight.domain.types import ToolCall
        tool_calls: list[ToolCall] = []
        total_input_tokens = 0
        total_output_tokens = 0

        for iteration in range(self._max_iterations):
            log.debug("react iteration", iteration=iteration)

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                tools=cast(Any, TOOL_DEFINITIONS),
                messages=cast(Any, messages),
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": cast(Any, response.content)})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result_text, tc = await self._tools.execute(block.name, block.input)
                        tool_calls.append(tc)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            answer = ""
            for block in response.content:
                if hasattr(block, "text"):
                    answer += block.text

            retrieved = self._tools.get_retrieved_chunks()
            output_flags = validate_output(answer, retrieved, self._tenant)
            if output_flags:
                guardrail_flags = {**(guardrail_flags or {}), **output_flags}

            latency_ms = int((time.monotonic() - start) * 1000)
            chunk_ids = [c.chunk_id for c in retrieved if c.chunk_id]

            await self._audit.log_query(
                tenant_id=self._tenant.id,
                query_text=query,
                tool_calls=tool_calls,
                retrieved_chunk_ids=chunk_ids,
                model_response=answer,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                latency_ms=latency_ms,
                guardrail_flags=guardrail_flags,
            )

            return AgentResponse(
                query=query,
                answer=answer,
                sources=retrieved,
                tool_calls=tool_calls,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                latency_ms=latency_ms,
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        failure_msg = (
            "I was unable to complete the analysis within the allowed number of steps. "
            "Please try a more specific question."
        )

        await self._audit.log_query(
            tenant_id=self._tenant.id,
            query_text=query,
            tool_calls=tool_calls,
            retrieved_chunk_ids=[],
            model_response=failure_msg,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            latency_ms=latency_ms,
        )

        return AgentResponse(
            query=query,
            answer=failure_msg,
            sources=[],
            tool_calls=tool_calls,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            latency_ms=latency_ms,
        )

    async def stream(self, query: str) -> AsyncGenerator[str, None]:
        """Stream the agent response as SSE-compatible events."""
        try:
            validate_input(query)
        except GuardrailViolationError as e:
            yield f"event: error\ndata: {e}\n\n"
            return

        system = SYSTEM_PROMPT.format(
            current_date=date.today().isoformat(),
            ticker_universe=", ".join(self._tenant.ticker_universe),
        )

        messages: list[Any] = [{"role": "user", "content": query}]
        from finsight.domain.types import ToolCall
        tool_calls: list[ToolCall] = []
        total_input_tokens = 0
        total_output_tokens = 0
        start = time.monotonic()

        for iteration in range(self._max_iterations):
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                tools=cast(Any, TOOL_DEFINITIONS),
                messages=cast(Any, messages),
            )

            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": cast(Any, response.content)})
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        payload = json.dumps({"tool": block.name, "inputs": block.input})
                        yield f"event: tool_call\ndata: {payload}\n\n"
                        result_text, tc = await self._tools.execute(block.name, block.input)
                        tool_calls.append(tc)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        })
                messages.append({"role": "user", "content": tool_results})
                continue

            answer_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    for word in block.text.split(" "):
                        yield f"data: {word} \n\n"
                        answer_parts.append(word)

            answer = " ".join(answer_parts)
            retrieved = self._tools.get_retrieved_chunks()
            latency_ms = int((time.monotonic() - start) * 1000)

            final_data = AgentResponse(
                query=query,
                answer=answer,
                sources=retrieved,
                tool_calls=tool_calls,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                latency_ms=latency_ms,
            )
            yield f"event: done\ndata: {final_data.model_dump_json()}\n\n"

            await self._audit.log_query(
                tenant_id=self._tenant.id,
                query_text=query,
                tool_calls=tool_calls,
                retrieved_chunk_ids=[c.chunk_id for c in retrieved if c.chunk_id],
                model_response=answer,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                latency_ms=latency_ms,
            )
            return

        yield "event: error\ndata: Max iterations exceeded\n\n"
