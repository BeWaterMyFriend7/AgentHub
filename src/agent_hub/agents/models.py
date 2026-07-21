from __future__ import annotations

from pydantic import BaseModel, Field


class SessionIntegrationCapabilities(BaseModel):
    session_discovery: bool
    status_detection: bool
    plan_reading: bool
    exact_resume: bool
    event_stream: bool


class AgentProfile(BaseModel):
    id: str
    name: str
    adapter_type: str
    enabled: bool
    connected: bool
    endpoint: str
    capabilities: SessionIntegrationCapabilities
    status_source: str
    last_probe_message: str = "尚未探测"


class ProbeResult(BaseModel):
    ok: bool
    agent_id: str
    title: str
    message: str
    checks: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
