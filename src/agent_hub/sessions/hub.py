from __future__ import annotations

from agent_hub.agents.models import ProbeResult
from agent_hub.agents.registry import AgentRegistry
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.events import SessionEventLog
from agent_hub.sessions.models import (
    AgentSession,
    OpenSessionResult,
    SessionStatus,
    SessionSummary,
)


class SessionHub:
    """聚合所有 Agent 内部会话的公共 Interface。"""

    def __init__(
        self,
        agents: AgentRegistry,
        adapters: dict[str, SessionAdapter],
        events: SessionEventLog,
    ) -> None:
        self._agents = agents
        self._adapters = dict(adapters)
        self._events = events

        unknown = self._adapters.keys() - agents.profile_ids()
        if unknown:
            raise ValueError(f"未知 Agent Profile: {', '.join(sorted(unknown))}")

    async def list_sessions(self) -> list[AgentSession]:
        sessions: list[AgentSession] = []
        for adapter in self._adapters.values():
            sessions.extend(await adapter.list_sessions())
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    async def summary(self) -> SessionSummary:
        sessions = await self.list_sessions()
        return SessionSummary(
            total=len(sessions),
            executing=sum(item.status == SessionStatus.EXECUTING for item in sessions),
            waiting=sum(
                item.status
                in {SessionStatus.WAITING_PERMISSION, SessionStatus.WAITING_INPUT}
                for item in sessions
            ),
            awaiting_review=sum(
                item.status == SessionStatus.AWAITING_REVIEW for item in sessions
            ),
            interrupted=sum(
                item.status == SessionStatus.INTERRUPTED for item in sessions
            ),
            closed=sum(item.status == SessionStatus.CLOSED for item in sessions),
            attention=sum(item.attention_required for item in sessions),
        )

    async def attention_sessions(self) -> list[AgentSession]:
        return [item for item in await self.list_sessions() if item.attention_required]

    async def probe_agent(self, agent_id: str) -> ProbeResult:
        profile = self._agents.profile_for(agent_id)
        adapter = self._adapters.get(agent_id)
        if profile is None:
            result = ProbeResult(
                ok=False,
                agent_id=agent_id,
                title="接入探测失败",
                message="没有找到该 Agent Profile。",
                failures=["Agent ID 不存在。"],
            )
        elif adapter is None:
            result = ProbeResult(
                ok=False,
                agent_id=agent_id,
                title="接入探测失败",
                message="该 Agent 尚未配置 Session Adapter。",
                failures=["当前 Profile 不支持或尚未接入内部会话。"],
            )
        else:
            result = await adapter.probe()

        self._events.record(
            title=result.title,
            detail=result.message,
            agent_id=agent_id,
        )
        return result

    async def open_session(self, session_id: str) -> OpenSessionResult:
        for agent_id, adapter in self._adapters.items():
            sessions = await adapter.list_sessions()
            if any(item.id == session_id for item in sessions):
                result = await adapter.open_session(session_id)
                self._events.record(
                    title="打开内部会话" if result.ok else "打开会话失败",
                    detail=result.message,
                    agent_id=agent_id,
                    session_id=session_id,
                )
                return result

        return OpenSessionResult(
            ok=False,
            session_id=session_id,
            agent_id="unknown",
            action="none",
            message="没有找到该会话。",
        )
