from __future__ import annotations

from abc import ABC, abstractmethod

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.models import AgentSession, OpenSessionResult


class SessionAdapter(ABC):
    def __init__(self, profile: AgentProfile) -> None:
        self.profile = profile

    @abstractmethod
    async def list_sessions(self) -> list[AgentSession]:
        raise NotImplementedError

    @abstractmethod
    async def probe(self) -> ProbeResult:
        raise NotImplementedError

    @abstractmethod
    async def open_session(self, session_id: str) -> OpenSessionResult:
        raise NotImplementedError
