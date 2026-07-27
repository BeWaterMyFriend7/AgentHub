from __future__ import annotations

import asyncio

from agent_hub.agents.models import ProbeResult
from agent_hub.agents.registry import AgentRegistry
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.annotations import SessionAnnotationStore
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
        annotations: SessionAnnotationStore | None = None,
    ) -> None:
        self._agents = agents
        self._adapters = dict(adapters)
        self._events = events
        self._annotations = annotations or SessionAnnotationStore()

        unknown = self._adapters.keys() - agents.profile_ids()
        if unknown:
            raise ValueError(f"未知 Agent Profile: {', '.join(sorted(unknown))}")

    async def list_sessions(self) -> list[AgentSession]:
        sessions: list[AgentSession] = []
        items = list(self._adapters.items())
        results = await asyncio.gather(
            *(adapter.list_sessions() for _, adapter in items),
            return_exceptions=True,
        )
        for (agent_id, _), result in zip(items, results, strict=True):
            if isinstance(result, BaseException):
                message = f"会话读取失败：{result}"
                self._agents.set_connection(agent_id, False, message)
                self._events.record(title="会话读取失败", detail=message, agent_id=agent_id)
                continue
            # 应用注释信息到会话
            for session in result:
                annotation = self._annotations.get(session.id)
                session.ignored = annotation.ignored
                session.follow_up = annotation.follow_up
                session.tags = annotation.tags
            sessions.extend(result)
            profile = self._agents.profile_for(agent_id)
            message = (
                profile.last_probe_message
                if profile is not None and profile.last_probe_message != "尚未探测"
                else f"成功读取 {len(result)} 个会话"
            )
            self._agents.set_connection(agent_id, True, message)
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    async def summary(self) -> SessionSummary:
        sessions = await self.list_sessions()
        return self.summarize(sessions)

    @staticmethod
    def summarize(sessions: list[AgentSession]) -> SessionSummary:
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

    async def dashboard(self) -> dict[str, object]:
        sessions = await self.list_sessions()
        return {
            "summary": self.summarize(sessions),
            "sessions": sessions,
            "attention": [item for item in sessions if item.attention_required],
        }

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
            configuration_failure = profile.last_probe_message
            if configuration_failure == "尚未探测":
                configuration_failure = "当前 Profile 不支持或尚未接入内部会话。"
            result = ProbeResult(
                ok=False,
                agent_id=agent_id,
                title="接入探测失败",
                message=(
                    "Agent Profile 已停用。"
                    if not profile.enabled
                    else "该 Agent 尚未配置 Session Adapter；请检查 Profile 配置。"
                ),
                failures=[configuration_failure],
            )
        else:
            result = await adapter.probe()

        self._agents.set_connection(agent_id, result.ok, result.message if result.ok else "; ".join(result.failures))

        self._events.record(
            title=result.title,
            detail=result.message,
            agent_id=agent_id,
        )
        return result

    async def open_session(self, session_id: str) -> OpenSessionResult:
        preferred = sorted(
            (
                (agent_id, adapter)
                for agent_id, adapter in self._adapters.items()
                if session_id.startswith(f"{agent_id}:")
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        remaining = [
            (agent_id, adapter)
            for agent_id, adapter in self._adapters.items()
            if all(agent_id != preferred_id for preferred_id, _ in preferred)
        ]
        for agent_id, adapter in [*preferred, *remaining]:
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

    def set_session_ignored(self, session_id: str, ignored: bool) -> None:
        """设置会话的忽略状态。"""
        self._annotations.set_ignored(session_id, ignored)

    def set_session_follow_up(self, session_id: str, follow_up: bool) -> None:
        """设置会话的跟进标记。"""
        self._annotations.set_follow_up(session_id, follow_up)
