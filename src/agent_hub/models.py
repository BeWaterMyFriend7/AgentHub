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
    status: Literal["done", "current", "pending"]


class AgentSession(BaseModel):
    id: str
    native_session_id: str
    tool_id: str
    tool_name: str
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

    @property
    def attention_required(self) -> bool:
        return self.status in ATTENTION_STATUSES

    @property
    def completed_steps(self) -> int:
        return sum(1 for item in self.plan_items if item.status == "done")

    @property
    def total_steps(self) -> int:
        return len(self.plan_items)


class ToolCapabilities(BaseModel):
    session_discovery: bool
    status_detection: bool
    plan_reading: bool
    exact_resume: bool
    event_stream: bool


class ToolInfo(BaseModel):
    id: str
    name: str
    adapter_type: str
    enabled: bool
    connected: bool
    endpoint: str
    capabilities: ToolCapabilities
    status_source: str
    last_probe_message: str = "尚未探测"


class ProbeResult(BaseModel):
    ok: bool
    tool_id: str
    title: str
    message: str
    checks: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class OpenSessionResult(BaseModel):
    ok: bool
    session_id: str
    tool_id: str
    action: str
    message: str
    resume_target: str | None = None


class EventRecord(BaseModel):
    id: str
    session_id: str | None = None
    tool_id: str | None = None
    title: str
    detail: str
    created_at: datetime


class Summary(BaseModel):
    total: int
    executing: int
    waiting: int
    awaiting_review: int
    interrupted: int
    closed: int
    attention: int
