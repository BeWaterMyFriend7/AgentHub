from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from agent_hub.platform.links import DirectoryEntryKind


class CapabilityType(StrEnum):
    SKILL = "skill"
    MCP_SERVER = "mcp_server"
    AGENT_PLUGIN = "agent_plugin"


class InstallationState(StrEnum):
    SOURCE = "source"
    SHARED = "shared"
    LOCAL_COPY = "local_copy"
    MISSING = "missing"
    CONFLICT = "conflict"
    BROKEN_LINK = "broken_link"
    INVALID = "invalid"
    DISTRIBUTED_NOT_LOADED = "distributed_not_loaded"
    HEALTH_CHECK_FAILED = "health_check_failed"


class NativeLoadState(StrEnum):
    UNKNOWN = "unknown"
    LOADED = "loaded"
    NOT_LOADED = "not_loaded"
    NOT_SUPPORTED = "not_supported"


class CapabilityLocation(BaseModel):
    agent_id: str
    agent_name: str
    capability_type: CapabilityType
    root: Path
    ignore_patterns: list[str] = Field(default_factory=list)


class CapabilitySource(BaseModel):
    id: str
    path: Path
    fingerprint: str
    manifest_id: str | None = None


class CapabilityInstallation(BaseModel):
    agent_id: str
    agent_name: str
    path: Path | None = None
    entry_kind: DirectoryEntryKind = DirectoryEntryKind.MISSING
    resolved_source: Path | None = None
    fingerprint: str = ""
    state: InstallationState
    native_load_state: NativeLoadState = NativeLoadState.UNKNOWN
    validation_errors: list[str] = Field(default_factory=list)


class Capability(BaseModel):
    id: str
    capability_type: CapabilityType
    name: str
    description: str = ""
    source: CapabilitySource | None = None
    installations: list[CapabilityInstallation] = Field(default_factory=list)
    identity_conflict: bool = False


class CapabilityMatrix(BaseModel):
    capabilities: list[Capability]
    locations: list[CapabilityLocation]
