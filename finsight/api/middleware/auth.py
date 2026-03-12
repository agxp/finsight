from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request, status

from finsight.database.tenant_store import TenantStore
from finsight.domain.types import Tenant


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_current_tenant(request: Request) -> Tenant:
    """Extract and validate Bearer token, return tenant."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    raw_key = auth.removeprefix("Bearer ").strip()
    key_hash = hash_api_key(raw_key)

    tenant_store: TenantStore = request.app.state.tenant_store
    tenant = await tenant_store.get_by_api_key_hash(key_hash)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return tenant
