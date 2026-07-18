from __future__ import annotations

from abc import ABC, abstractmethod

from agent_hub.models import AgentSession, OpenSessionResult, ProbeResult, ToolInfo


class AgentAdapter(ABC):
    def __init__(self, tool: ToolInfo) -> None:
        self.tool = tool

    @abstractmethod
    async def list_sessions(self) -> list[AgentSession]:
        raise NotImplementedError

    @abstractmethod
    async def probe(self) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    async def open_session(self, session_id: str) -> OpenSessionResult:
        raise NotImplementedError

    async def advance_demo_state(self) -> list[str]:
        """Demo-only hook. Real adapters should update from API/hooks/events."""
        return []
