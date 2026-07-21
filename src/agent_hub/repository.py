"""第一阶段迁移兼容层；新代码使用 AgentRegistry 与 SessionEventLog。"""

from agent_hub.agents.models import AgentProfile
from agent_hub.demo.seed import events as seed_events
from agent_hub.sessions.events import SessionEventLog
from agent_hub.sessions.models import SessionEvent


class Repository(SessionEventLog):
    def __init__(self, tools: list[AgentProfile]) -> None:
        super().__init__(seed_events())
        self.tools = {item.id: item for item in tools}

    @property
    def events(self) -> list[SessionEvent]:
        return self.records

    def add_event(
        self,
        title: str,
        detail: str,
        tool_id: str | None = None,
        session_id: str | None = None,
    ) -> SessionEvent:
        return self.record(title, detail, agent_id=tool_id, session_id=session_id)
