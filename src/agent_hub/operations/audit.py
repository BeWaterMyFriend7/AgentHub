from __future__ import annotations

from agent_hub.operations.models import AuditRecord


class InMemoryAuditLog:
    """第一阶段审计实现；后续可替换为持久化 Adapter。"""

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []
        self._write_count = 0

    @property
    def records(self) -> list[AuditRecord]:
        return [record.model_copy(deep=True) for record in self._records]

    @property
    def write_count(self) -> int:
        return self._write_count

    def append(self, record: AuditRecord) -> None:
        self._write_count += 1
        stored = record.model_copy(deep=True)
        for index, existing in enumerate(self._records):
            if existing.operation_id == record.operation_id:
                self._records[index] = stored
                return
        self._records.insert(0, stored)
