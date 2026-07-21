from __future__ import annotations

from agent_hub.operations.models import AuditRecord


class InMemoryAuditLog:
    """第一阶段审计实现；后续可替换为持久化 Adapter。"""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> list[AuditRecord]:
        return [record.model_copy(deep=True) for record in self._records]

    def append(self, record: AuditRecord) -> None:
        self._records.insert(0, record.model_copy(deep=True))
