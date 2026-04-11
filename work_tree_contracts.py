from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class TreeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class BranchStatus(str, Enum):
    READY = "ready"
    ACTIVE = "active"
    BLOCKED = "blocked"
    STALLED = "stalled"
    COMPLETE = "complete"
    ARCHIVED = "archived"


class TaskStatus(str, Enum):
    OPEN = "open"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    DROPPED = "dropped"


class ToolStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(slots=True)
class WorkTree:
    tree_id: str
    title: str
    status: TreeStatus
    root_branch_id: str
    created_at: datetime
    updated_at: datetime
    meta: dict[str, object] | None = field(default=None)


@dataclass(slots=True)
class Branch:
    branch_id: str
    tree_id: str
    parent_branch_id: str | None
    title: str
    bucket: str
    status: BranchStatus
    created_at: datetime
    updated_at: datetime
    priority: int = field(default=50)
    score: float = field(default=50.0)
    depth: int = field(default=0)
    depends_on: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    open_stem_count: int = field(default=0)
    required_tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    preferred_tool: str | None = field(default=None)
    tool_state: dict[str, ToolStatus] = field(default_factory=dict)
    notes: str | None = field(default=None)


@dataclass(slots=True)
class Task:
    task_id: str
    branch_id: str
    title: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    priority: int = field(default=50)
    score: float = field(default=50.0)
    depends_on: list[str] = field(default_factory=list)