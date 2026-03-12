from __future__ import annotations

from fastapi import Request

from finsight.agent.planner import ReActPlanner
from finsight.agent.tools import AgentTools
from finsight.database.audit_store import AuditStore
from finsight.database.chunk_store import ChunkStore
from finsight.database.filing_store import FilingStore
from finsight.database.tenant_store import TenantStore
from finsight.domain.types import Tenant
from finsight.embedding.embedder import Embedder
from finsight.retrieval.searcher import SemanticSearcher


def get_filing_store(request: Request) -> FilingStore:
    return request.app.state.filing_store


def get_chunk_store(request: Request) -> ChunkStore:
    return request.app.state.chunk_store


def get_tenant_store(request: Request) -> TenantStore:
    return request.app.state.tenant_store


def get_audit_store(request: Request) -> AuditStore:
    return request.app.state.audit_store


def make_planner(tenant: Tenant, request: Request) -> ReActPlanner:
    embedder: Embedder = request.app.state.embedder
    chunk_store: ChunkStore = request.app.state.chunk_store
    audit_store: AuditStore = request.app.state.audit_store

    searcher = SemanticSearcher(embedder, chunk_store)
    tools = AgentTools(searcher, tenant)
    return ReActPlanner(tools, audit_store, tenant)
