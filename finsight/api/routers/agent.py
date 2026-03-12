from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from finsight.api.dependencies import make_planner
from finsight.api.middleware.auth import get_current_tenant
from finsight.api.middleware.rate_limit import RateLimiter
from finsight.domain.errors import GuardrailViolationError
from finsight.domain.types import AgentResponse, QueryRequest, Tenant

router = APIRouter(prefix="/v1")


@router.post("/query")
async def query_agent(
    body: QueryRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
) -> AgentResponse | StreamingResponse:
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    await rate_limiter.check(tenant.id)

    planner = make_planner(tenant, request)

    if body.stream:
        async def event_stream():
            async for chunk in planner.stream(body.query):
                yield chunk

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    try:
        response = await planner.run(body.query)
    except GuardrailViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return response
