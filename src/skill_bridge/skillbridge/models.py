from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class EntryType(str, Enum):
    REAL_DIR = "REAL_DIR"
    JUNCTION = "JUNCTION"
    BROKEN_LINK = "BROKEN_LINK"


class InstanceState(str, Enum):
    SOURCE_LOCAL = "SOURCE_LOCAL"
    SHARED_LINK = "SHARED_LINK"
    MISSING = "MISSING"
    LOCAL_COPY = "LOCAL_COPY"
    CONFLICT = "CONFLICT"
    BROKEN_LINK = "BROKEN_LINK"
    INVALID = "INVALID"


class AgentConfig(BaseModel):
    id: str
    name: str
    skill_root: str
    icon: str = ""
    enabled: bool = True
    ignore_patterns: list[str] = Field(default_factory=list)


class AgentCreate(BaseModel):
    id: str
    name: str
    skill_root: str
    icon: str = ""
    enabled: bool = True
    ignore_patterns: list[str] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    skill_root: Optional[str] = None
    icon: Optional[str] = None
    enabled: Optional[bool] = None
    ignore_patterns: Optional[list[str]] = None


class AgentSkillInstance(BaseModel):
    agent_id: str
    agent_name: str
    skill_name: str
    path: str = ""
    entry_type: EntryType = EntryType.REAL_DIR
    resolved_target: str = ""
    fingerprint: str = ""
    state: InstanceState
    has_skill_md: bool = False
    description: str = ""
    validation_errors: list[str] = Field(default_factory=list)


class SkillRow(BaseModel):
    skill_name: str
    description: str = ""
    source_agent_id: Optional[str] = None
    instances: list[AgentSkillInstance] = Field(default_factory=list)
    instances_by_agent: dict[str, AgentSkillInstance] = Field(default_factory=dict)


class SkillMatrix(BaseModel):
    skills: list[SkillRow]
    agents: list[AgentConfig]
