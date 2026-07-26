from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionIntegrationCapabilities(BaseModel):
    session_discovery: bool
    status_detection: bool
    plan_reading: bool
    exact_resume: bool
    event_stream: bool
    resume_launch: bool = False


class AgentProfile(BaseModel):
    id: str
    name: str
    agent_type: str = "custom"
    adapter_kind: str = "unsupported"
    adapter_type: str
    enabled: bool
    connected: bool
    endpoint: str
    data_path: str | None = None
    executable: str | None = None
    username: str | None = None
    secret_env: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    capabilities: SessionIntegrationCapabilities
    status_source: str
    last_probe_message: str = "尚未探测"


class AgentProfileInput(BaseModel):
    id: str | None = None
    name: str
    agent_type: str
    adapter_kind: str
    enabled: bool = True
    endpoint: str = ""
    data_path: str | None = None
    executable: str | None = None
    username: str | None = None
    secret_env: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class AgentProfilePatch(BaseModel):
    name: str | None = None
    agent_type: str | None = None
    adapter_kind: str | None = None
    enabled: bool | None = None
    endpoint: str | None = None
    data_path: str | None = None
    executable: str | None = None
    username: str | None = None
    secret_env: str | None = None
    settings: dict[str, Any] | None = None


class AgentAdapterDefinition(BaseModel):
    kind: str
    agent_type: str
    name: str
    description: str
    fields: list[str] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ProbeResult(BaseModel):
    ok: bool
    agent_id: str
    title: str
    message: str
    checks: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
