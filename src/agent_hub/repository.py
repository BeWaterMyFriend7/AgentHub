from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agent_hub.models import EventRecord, ToolInfo


class Repository:
    def __init__(self, tools: list[ToolInfo]) -> None:
        self.tools = {item.id: item for item in tools}
        self.events: list[EventRecord] = [
            EventRecord(
                id=str(uuid4()),
                tool_id="codex",
                session_id="codex-kafka",
                title="Codex 等待授权",
                detail="Kafka 多 Topic 疲劳压测需要授权执行命令。",
                created_at=datetime.now(timezone.utc),
            ),
            EventRecord(
                id=str(uuid4()),
                tool_id="claude-code",
                session_id="claude-skill-doc",
                title="Claude Code 等待验收",
                detail="Skill 文档结构整理已输出结果。",
                created_at=datetime.now(timezone.utc),
            ),
        ]

    def add_event(
        self,
        title: str,
        detail: str,
        tool_id: str | None = None,
        session_id: str | None = None,
    ) -> EventRecord:
        event = EventRecord(
            id=str(uuid4()),
            tool_id=tool_id,
            session_id=session_id,
            title=title,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
        self.events.insert(0, event)
        self.events = self.events[:100]
        return event
