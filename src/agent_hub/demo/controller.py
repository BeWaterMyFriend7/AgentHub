from __future__ import annotations

from agent_hub.sessions.adapters.mock import MockSessionAdapter
from agent_hub.sessions.events import SessionEventLog


class DemoSessionController:
    """只编排演示数据状态变化，不进入生产 Session Adapter 契约。"""

    def __init__(
        self,
        adapters: dict[str, MockSessionAdapter],
        events: SessionEventLog,
    ) -> None:
        self._adapters = dict(adapters)
        self._events = events

    async def tick(self) -> list[str]:
        changes: list[str] = []
        for agent_id, adapter in self._adapters.items():
            adapter_changes = await adapter.advance_demo_state()
            changes.extend(adapter_changes)
            for change in adapter_changes:
                self._events.record(
                    title="会话状态自动更新",
                    detail=change,
                    agent_id=agent_id,
                )
        return changes
