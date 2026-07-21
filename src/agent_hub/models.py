"""第一阶段迁移兼容层；新代码从 agents 或 sessions 模块导入。"""

from agent_hub.agents.models import (
    AgentProfile,
    ProbeResult,
    SessionIntegrationCapabilities,
)
from agent_hub.sessions.models import (
    ATTENTION_STATUSES,
    AgentSession,
    OpenSessionResult,
    PlanItem,
    SessionEvent,
    SessionStatus,
    SessionSummary,
)

ToolCapabilities = SessionIntegrationCapabilities
ToolInfo = AgentProfile
EventRecord = SessionEvent
Summary = SessionSummary

__all__ = [
    "AgentSession",
    "ATTENTION_STATUSES",
    "EventRecord",
    "OpenSessionResult",
    "PlanItem",
    "ProbeResult",
    "SessionStatus",
    "Summary",
    "ToolCapabilities",
    "ToolInfo",
]
