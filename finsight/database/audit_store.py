from __future__ import annotations

import json
import uuid

import asyncpg

from finsight.domain.types import ToolCall


class AuditStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def log_query(
        self,
        *,
        tenant_id: uuid.UUID,
        query_text: str,
        tool_calls: list[ToolCall],
        retrieved_chunk_ids: list[uuid.UUID],
        model_response: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        guardrail_flags: dict | None = None,
    ) -> uuid.UUID:
        tool_calls_data = [tc.model_dump() for tc in tool_calls]

        async with self._pool.acquire() as conn:
            row_id = await conn.fetchval(
                """
                INSERT INTO agent_queries (
                    tenant_id, query_text, tool_calls, retrieved_chunk_ids,
                    model_response, input_tokens, output_tokens, latency_ms, guardrail_flags
                )
                VALUES ($1, $2, $3, $4::uuid[], $5, $6, $7, $8, $9)
                RETURNING id
                """,
                tenant_id,
                query_text,
                json.dumps(tool_calls_data),
                retrieved_chunk_ids,
                model_response,
                input_tokens,
                output_tokens,
                latency_ms,
                json.dumps(guardrail_flags) if guardrail_flags else None,
            )
        return row_id
