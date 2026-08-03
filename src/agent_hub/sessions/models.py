from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SessionStatus(StrEnum):
    EXECUTING = "executing"
    WAITING_PERMISSION = "waiting_permission"
    WAITING_INPUT = "waiting_input"
    AWAITING_REVIEW = "awaiting_review"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"
    UNKNOWN = "unknown"


ATTENTION_STATUSES = {
    SessionStatus.WAITING_PERMISSION,
    SessionStatus.WAITING_INPUT,
    SessionStatus.AWAITING_REVIEW,
    SessionStatus.INTERRUPTED,
}


class PlanItem(BaseModel):
    id: str
    title: str
    status: Literal["done", "current", "pending", "cancelled"]


class AgentSession(BaseModel):
    id: str
    native_session_id: str
    agent_id: str
    agent_name: str
    title: str
    project_name: str
    working_directory: str | None = None
    status: SessionStatus
    status_reason: str
    current_goal: str
    current_step: str
    plan_items: list[PlanItem] = Field(default_factory=list)
    last_activity: str
    updated_at: datetime
    status_source: str
    confidence: Literal["high", "medium", "low"]
    resumable: bool = True
    ignored: bool = False
    follow_up: bool = False
    tags: list[str] = Field(default_factory=list)
    provider_id: str | None = None
    model_id: str | None = None
    route_source: Literal["session", "default", "unbound"] = "unbound"
    follows_default_route: bool = True

    @property
    def attention_required(self) -> bool:
        return self.status in ATTENTION_STATUSES and not self.ignored

    @property
    def completed_steps(self) -> int:
        return sum(1 for item in self.plan_items if item.status == "done")

    @property
    def total_steps(self) -> int:
        return len(self.plan_items)

class OpenSessionResult(BaseModel):
    ok: bool
    session_id: str
    agent_id: str
    action: str
    message: str
    resume_target: str | None = None

class SessionEvent(BaseModel):
    id: str
    session_id: str | None = None
    agent_id: str | None = None
    title: str
    detail: str
    created_at: datetime



class SessionSummary(BaseModel):
    total: int
    executing: int
    waiting: int
    awaiting_review: int
    interrupted: int
    closed: int
    attention: int
