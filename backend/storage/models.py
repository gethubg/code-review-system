from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel
import uuid


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AgentType(str, Enum):
    BUG = "bug"
    SECURITY = "security"
    COVERAGE = "coverage"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReviewRun(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    git_url: str
    repo_name: str
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    production_score: Optional[float] = None
    production_verdict: Optional[str] = None
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    error_message: Optional[str] = None


class Finding(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    run_id: str = Field(foreign_key="reviewrun.id", index=True)
    agent: AgentType
    severity: Severity
    title: str
    description: str
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    cwe_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Report(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    run_id: str = Field(foreign_key="reviewrun.id", unique=True, index=True)
    markdown_path: str
    json_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
