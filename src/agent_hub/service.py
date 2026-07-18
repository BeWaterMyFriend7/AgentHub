from __future__ import annotations

from agent_hub.adapters.base import AgentAdapter
from agent_hub.models import (
    AgentSession,
    OpenSessionResult,
    ProbeResult,
    SessionStatus,
    Summary,
    ToolInfo,
)
from agent_hub.repository import Repository


class SessionHubService:
    def __init__(
        self,
        repository: Repository,
        adapters: dict[str, AgentAdapter],
    ) -> None:
        self.repository = repository
        self.adapters = adapters

    async def list_sessions(self) -> list[AgentSession]:
        sessions: list[AgentSession] = []
        for adapter in self.adapters.values():
            sessions.extend(await adapter.list_sessions())
        return sorted(sessions, key=lambda item: item.updated_at, reverse=True)

    async def summary(self) -> Summary:
        sessions = await self.list_sessions()
        return Summary(
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

    def list_tools(self) -> list[ToolInfo]:
        return list(self.repository.tools.values())

    async def probe_tool(self, tool_id: str) -> ProbeResult:
        adapter = self.adapters.get(tool_id)
        if adapter is None:
            return ProbeResult(
                ok=False,
                tool_id=tool_id,
                title="接入探测失败",
                message="没有找到该工具的适配器。",
                failures=["工具 ID 不存在或适配器未加载。"],
            )
        result = await adapter.probe()
        self.repository.add_event(
            title=result.title,
            detail=result.message,
            tool_id=tool_id,
        )
        return result

    async def open_session(self, session_id: str) -> OpenSessionResult:
        for tool_id, adapter in self.adapters.items():
            sessions = await adapter.list_sessions()
            if any(item.id == session_id for item in sessions):
                result = await adapter.open_session(session_id)
                self.repository.add_event(
                    title="打开内部会话" if result.ok else "打开会话失败",
                    detail=result.message,
                    tool_id=tool_id,
                    session_id=session_id,
                )
                return result

        return OpenSessionResult(
            ok=False,
            session_id=session_id,
            tool_id="unknown",
            action="none",
            message="没有找到该会话。",
        )

    async def advance_demo(self) -> list[str]:
        changes: list[str] = []
        for tool_id, adapter in self.adapters.items():
            adapter_changes = await adapter.advance_demo_state()
            changes.extend(adapter_changes)
            for change in adapter_changes:
                self.repository.add_event(
                    title="会话状态自动更新",
                    detail=change,
                    tool_id=tool_id,
                )
        return changes
