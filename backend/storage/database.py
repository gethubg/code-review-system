from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from .models import AgentType, Finding, Report, ReviewRun, RunStatus, Severity

logger = structlog.get_logger(__name__)

_engine: AsyncEngine | None = None


def _get_db_url() -> str:
    db_path = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./code_review.db")
    return db_path


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        db_url = _get_db_url()
        connect_args: dict = {}
        kwargs: dict = {}

        if "sqlite" in db_url:
            connect_args = {
                "check_same_thread": False,
                "timeout": 30,
            }
            # Use StaticPool for in-memory SQLite, NullPool for file-based
            if ":memory:" in db_url:
                kwargs["poolclass"] = StaticPool

        _engine = create_async_engine(
            db_url,
            echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
            connect_args=connect_args,
            **kwargs,
        )
    return _engine


async def create_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        # Enable WAL mode for SQLite to allow concurrent reads during writes
        if "sqlite" in str(engine.url):
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("database_tables_created")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# ReviewRun CRUD
# ---------------------------------------------------------------------------


async def create_run(git_url: str, repo_name: str) -> ReviewRun:
    run = ReviewRun(git_url=git_url, repo_name=repo_name)
    async with get_session() as session:
        session.add(run)
    logger.info("run_created", run_id=run.id, repo_name=repo_name)
    return run


async def get_run(run_id: str) -> Optional[ReviewRun]:
    async with get_session() as session:
        result = await session.get(ReviewRun, run_id)
        return result


async def update_run(run_id: str, **fields) -> Optional[ReviewRun]:
    async with get_session() as session:
        run = await session.get(ReviewRun, run_id)
        if run is None:
            logger.warning("run_not_found_for_update", run_id=run_id)
            return None
        for key, value in fields.items():
            if hasattr(run, key):
                setattr(run, key, value)
            else:
                logger.warning("unknown_run_field", field=key)
        session.add(run)
    logger.info("run_updated", run_id=run_id, fields=list(fields.keys()))
    return run


async def list_runs(
    offset: int = 0,
    limit: int = 20,
    status: Optional[RunStatus] = None,
) -> tuple[list[ReviewRun], int]:
    """Return a page of runs and the total count matching the filter."""
    async with get_session() as session:
        stmt = select(ReviewRun)
        count_stmt = select(ReviewRun)

        if status is not None:
            stmt = stmt.where(ReviewRun.status == status)
            count_stmt = count_stmt.where(ReviewRun.status == status)

        stmt = stmt.order_by(ReviewRun.created_at.desc()).offset(offset).limit(limit)

        runs_result = await session.exec(stmt)
        runs = list(runs_result.all())

        total_result = await session.exec(count_stmt)
        total = len(total_result.all())

    return runs, total


# ---------------------------------------------------------------------------
# Finding CRUD
# ---------------------------------------------------------------------------


async def create_finding(
    run_id: str,
    agent: AgentType,
    severity: Severity,
    title: str,
    description: str,
    file_path: Optional[str] = None,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    code_snippet: Optional[str] = None,
    suggestion: Optional[str] = None,
    cwe_id: Optional[str] = None,
) -> Finding:
    finding = Finding(
        run_id=run_id,
        agent=agent,
        severity=severity,
        title=title,
        description=description,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        code_snippet=code_snippet,
        suggestion=suggestion,
        cwe_id=cwe_id,
    )
    async with get_session() as session:
        session.add(finding)

        # Update counters on the parent run
        run = await session.get(ReviewRun, run_id)
        if run is not None:
            run.total_findings += 1
            if severity == Severity.CRITICAL:
                run.critical_count += 1
            elif severity == Severity.HIGH:
                run.high_count += 1
            elif severity == Severity.MEDIUM:
                run.medium_count += 1
            elif severity == Severity.LOW:
                run.low_count += 1
            session.add(run)

    logger.info(
        "finding_created",
        finding_id=finding.id,
        run_id=run_id,
        severity=severity,
        agent=agent,
    )
    return finding


async def get_findings_by_run(
    run_id: str,
    severity: Optional[Severity] = None,
    agent: Optional[AgentType] = None,
    offset: int = 0,
    limit: int = 100,
) -> list[Finding]:
    async with get_session() as session:
        stmt = select(Finding).where(Finding.run_id == run_id)

        if severity is not None:
            stmt = stmt.where(Finding.severity == severity)
        if agent is not None:
            stmt = stmt.where(Finding.agent == agent)

        stmt = stmt.order_by(Finding.created_at.asc()).offset(offset).limit(limit)
        result = await session.exec(stmt)
        return list(result.all())


# ---------------------------------------------------------------------------
# Report CRUD
# ---------------------------------------------------------------------------


async def create_report(
    run_id: str,
    markdown_path: str,
    json_path: str,
) -> Report:
    report = Report(run_id=run_id, markdown_path=markdown_path, json_path=json_path)
    async with get_session() as session:
        session.add(report)
    logger.info("report_created", report_id=report.id, run_id=run_id)
    return report


async def get_report_by_run(run_id: str) -> Optional[Report]:
    async with get_session() as session:
        stmt = select(Report).where(Report.run_id == run_id)
        result = await session.exec(stmt)
        return result.first()
