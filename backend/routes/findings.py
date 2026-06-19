from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from backend.storage import database as db
from backend.storage.models import AgentType, Finding, Severity

log = structlog.get_logger(__name__)

router = APIRouter(tags=["findings"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class FindingResponse(BaseModel):
    id: str
    run_id: str
    agent: str
    severity: str
    title: str
    description: str
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    cwe_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FindingListResponse(BaseModel):
    items: list[FindingResponse]
    total: int
    skip: int
    limit: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/findings", response_model=FindingListResponse)
async def list_findings(
    run_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    agent: Optional[str] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> FindingListResponse:
    severity_enum: Optional[Severity] = None
    agent_enum: Optional[AgentType] = None

    if severity is not None:
        try:
            severity_enum = Severity(severity.lower())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid severity {severity!r}. Valid values: {[s.value for s in Severity]}",
            )

    if agent is not None:
        try:
            agent_enum = AgentType(agent.lower())
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid agent {agent!r}. Valid values: {[a.value for a in AgentType]}",
            )

    # If run_id is provided, delegate to the targeted DB helper.
    # Otherwise do a broader query.
    async with db.get_session() as session:
        stmt = select(Finding)

        if run_id is not None:
            stmt = stmt.where(Finding.run_id == run_id)
        if severity_enum is not None:
            stmt = stmt.where(Finding.severity == severity_enum)
        if agent_enum is not None:
            stmt = stmt.where(Finding.agent == agent_enum)

        # Count total before paging
        count_result = await session.exec(stmt)
        total = len(count_result.all())

        paged_stmt = stmt.order_by(Finding.created_at.asc()).offset(skip).limit(limit)
        paged_result = await session.exec(paged_stmt)
        findings = list(paged_result.all())

    return FindingListResponse(
        items=[FindingResponse.from_orm(f) for f in findings],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/findings/{finding_id}", response_model=FindingResponse)
async def get_finding(finding_id: str) -> Finding:
    async with db.get_session() as session:
        finding = await session.get(Finding, finding_id)

    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id!r} not found")

    return finding
