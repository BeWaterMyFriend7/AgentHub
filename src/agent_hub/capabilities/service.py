from __future__ import annotations

from pathlib import Path

from agent_hub.capabilities.inventory import CapabilityInventory
from agent_hub.capabilities.models import (
    Capability,
    CapabilityLocation,
    CapabilityMatrix,
)
from agent_hub.operations.manager import CapabilityOperationManager
from agent_hub.operations.models import (
    Confirmation,
    ConfirmationType,
    OperationPlan,
    OperationRequest,
    OperationResult,
    OperationType,
)


class SkillShareService:
    """以 Skill 为主视角，组合只读清单与安全目录链接操作。"""

    def __init__(
        self,
        inventory: CapabilityInventory,
        operations: CapabilityOperationManager,
        locations: list[CapabilityLocation],
    ) -> None:
        self._inventory = inventory
        self._operations = operations
        self._locations = locations
        self._plans: dict[str, OperationPlan] = {}

    def matrix(self) -> CapabilityMatrix:
        return self._inventory.discover(self._locations)

    def plan(
        self,
        skill_name: str,
        agent_id: str,
        *,
        share: bool,
    ) -> OperationPlan:
        matrix = self.matrix()
        capability = next(
            (
                item
                for item in matrix.capabilities
                if item.name == skill_name
                and item.source is not None
                and item.source.path is not None
            ),
            None,
        )
        if capability is None:
            raise ValueError(f"没有找到可共享的 Skill 来源：{skill_name}")
        target_root = self._location_root(agent_id)
        source = capability.source.path
        assert source is not None
        target = target_root / source.name
        request = OperationRequest(
            operation_type=(
                OperationType.ENABLE_SHARED_INSTALLATION
                if share
                else OperationType.DISABLE_SHARED_INSTALLATION
            ),
            capability_id=capability.id,
            agent_id=agent_id,
            source_path=source,
            target_path=target,
        )
        plan = self._operations.plan(request)
        self._plans[plan.id] = plan
        return plan

    def confirm(self, plan_id: str, confirmation_type: ConfirmationType) -> OperationResult:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise ValueError("没有找到可确认的操作计划。")
        return self._operations.execute(
            plan,
            Confirmation(
                plan_id=plan.id,
                confirmation_type=confirmation_type,
            ),
        )

    def _location_root(self, agent_id: str) -> Path:
        location = next(
            (item for item in self._locations if item.agent_id == agent_id),
            None,
        )
        if location is None:
            raise ValueError(f"不支持的 Agent：{agent_id}")
        return location.root
