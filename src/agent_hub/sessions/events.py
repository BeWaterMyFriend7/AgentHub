from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from agent_hub.sessions.models import SessionEvent


class SessionEventLog:
    def __init__(self, records: Iterable[SessionEvent] = ()) -> None:
        self._records = list(records)

    @property
    def records(self) -> list[SessionEvent]:
        return [record.model_copy(deep=True) for record in self._records]

    def record(
        self,
        title: str,
        detail: str,
        agent_id: str | None = None,
        session_id: str | None = None,
    ) -> SessionEvent:
        event = SessionEvent(
            id=str(uuid4()),
            agent_id=agent_id,
            session_id=session_id,
            title=title,
            detail=detail,
            created_at=datetime.now(timezone.utc),
        )
        self._records.insert(0, event)
        self._records = self._records[:100]
        return event
