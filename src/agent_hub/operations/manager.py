from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent_hub.operations.audit import InMemoryAuditLog
from agent_hub.operations.models import (
    AuditRecord,
    Confirmation,
    IssueSeverity,
    OperationPlan,
    OperationRequest,
    OperationResult,
    OperationStatus,
    OperationStep,
    OperationStepType,
    OperationType,
    PreflightIssue,
)
from agent_hub.platform.links import (
    DirectoryEntryKind,
    DirectoryLinkAdapter,
    normalized_path,
)


@dataclass
class _ExecutedOperation:
    plan: OperationPlan
    backup_path: Path | None
    status: OperationStatus


class CapabilityOperationManager:
    """把路径安全、备份、目录链接、验证、回滚和审计隐藏在统一 Interface 后。"""

    def __init__(
        self,
        link_adapter: DirectoryLinkAdapter,
        audit_log: InMemoryAuditLog,
        allowed_roots: list[Path],
        protected_roots: list[Path],
        backup_root: Path,
    ) -> None:
        self._link_adapter = link_adapter
        self._audit_log = audit_log
        self._allowed_roots = [normalized_path(path) for path in allowed_roots]
        self._protected_roots = {normalized_path(path) for path in protected_roots}
        self._backup_root = normalized_path(backup_root)
        self._executed: dict[str, _ExecutedOperation] = {}

    def plan(self, request: OperationRequest) -> OperationPlan:
        plan_id = str(uuid4())
        normalized_request = request.model_copy(
            update={
                "source_path": normalized_path(request.source_path),
                "target_path": normalized_path(request.target_path),
            }
        )
        issues = self._preflight(normalized_request)
        steps: list[OperationStep] = []
        if not any(issue.severity == IssueSeverity.ERROR for issue in issues):
            steps, step_issues = self._build_steps(plan_id, normalized_request)
            issues.extend(step_issues)
        return OperationPlan(
            id=plan_id,
            request=normalized_request,
            steps=steps,
            issues=issues,
        )

    def execute(
        self,
        plan: OperationPlan,
        confirmation: Confirmation,
    ) -> OperationResult:
        if not plan.ready:
            return self._finish(
                plan,
                OperationStatus.REJECTED,
                "预检未通过，未执行任何修改。",
                error="；".join(issue.message for issue in plan.issues),
            )
        if (
            confirmation.plan_id != plan.id
            or confirmation.confirmation_type != plan.confirmation_type
        ):
            return self._finish(
                plan,
                OperationStatus.REJECTED,
                "确认类型或操作计划不匹配。",
                error="INVALID_CONFIRMATION",
            )

        current_issues = self._preflight(plan.request)
        current_steps: list[OperationStep] = []
        if not any(
            issue.severity == IssueSeverity.ERROR for issue in current_issues
        ):
            current_steps, step_issues = self._build_steps(plan.id, plan.request)
            current_issues.extend(step_issues)
        if (
            any(issue.severity == IssueSeverity.ERROR for issue in current_issues)
            or current_steps != plan.steps
        ):
            return self._finish(
                plan,
                OperationStatus.REJECTED,
                "确认后目标状态发生变化，请重新生成操作计划。",
                error="PLAN_STALE",
            )

        completed: list[OperationStep] = []
        backup_path: Path | None = None
        try:
            for step in plan.steps:
                if step.step_type == OperationStepType.BACKUP_DIRECTORY:
                    backup_path = step.target
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(step.source), str(backup_path))
                elif step.step_type == OperationStepType.CREATE_DIRECTORY_LINK:
                    self._link_adapter.create(step.target, step.source)
                elif step.step_type == OperationStepType.VERIFY_DIRECTORY_LINK:
                    info = self._link_adapter.inspect(step.target)
                    if (
                        info.kind != DirectoryEntryKind.DIRECTORY_LINK
                        or info.resolved_target is None
                        or normalized_path(info.resolved_target)
                        != normalized_path(step.source)
                    ):
                        raise OSError("目录链接创建后验证失败")
                elif step.step_type == OperationStepType.REMOVE_DIRECTORY_LINK:
                    self._link_adapter.remove(step.target, step.source)
                completed.append(step)
        except Exception as error:
            rollback_error = self._reverse_steps(completed, backup_path)
            status = (
                OperationStatus.ROLLED_BACK
                if rollback_error is None
                else OperationStatus.MANUAL_RECOVERY_REQUIRED
            )
            return self._finish(
                plan,
                status,
                "操作失败，已回滚。"
                if rollback_error is None
                else "操作失败，自动回滚不完整，需要人工恢复。",
                backup_path=backup_path,
                error=str(error) if rollback_error is None else f"{error}; {rollback_error}",
                completed=completed,
            )

        return self._finish(
            plan,
            OperationStatus.SUCCEEDED,
            "能力安装变更完成。",
            backup_path=backup_path,
            completed=completed,
        )

    def rollback(self, operation_id: str) -> OperationResult:
        executed = self._executed.get(operation_id)
        if executed is None:
            return OperationResult(
                operation_id=operation_id,
                status=OperationStatus.REJECTED,
                message="没有找到可回滚的操作。",
                error="OPERATION_NOT_FOUND",
            )
        if executed.status != OperationStatus.SUCCEEDED:
            return OperationResult(
                operation_id=operation_id,
                status=OperationStatus.REJECTED,
                message="只有成功完成的操作可以回滚。",
                error="OPERATION_NOT_ROLLBACKABLE",
            )

        error = self._reverse_steps(executed.plan.steps, executed.backup_path)
        if error is not None:
            return self._finish(
                executed.plan,
                OperationStatus.MANUAL_RECOVERY_REQUIRED,
                "回滚不完整，需要人工恢复。",
                backup_path=executed.backup_path,
                error=error,
            )
        return self._finish(
            executed.plan,
            OperationStatus.ROLLED_BACK,
            "操作已回滚。",
            backup_path=executed.backup_path,
        )

    def _preflight(self, request: OperationRequest) -> list[PreflightIssue]:
        issues: list[PreflightIssue] = []
        for label, path in (
            ("能力来源", request.source_path),
            ("目标安装", request.target_path),
        ):
            if not self._is_allowed(path):
                issues.append(
                    PreflightIssue(
                        code="PATH_OUTSIDE_ALLOWED_ROOT",
                        message=f"{label}路径超出允许范围：{path}",
                    )
                )
        if request.target_path in self._protected_roots:
            issues.append(
                PreflightIssue(
                    code="PROTECTED_ROOT",
                    message=f"禁止把能力根目录本身作为操作目标：{request.target_path}",
                )
            )
        if request.source_path == request.target_path:
            issues.append(
                PreflightIssue(
                    code="SOURCE_EQUALS_TARGET",
                    message="能力来源与目标安装不能是同一路径。",
                )
            )
        if not request.source_path.is_dir():
            issues.append(
                PreflightIssue(
                    code="SOURCE_NOT_FOUND",
                    message=f"能力来源目录不存在：{request.source_path}",
                )
            )
        if not request.target_path.parent.is_dir():
            issues.append(
                PreflightIssue(
                    code="TARGET_ROOT_NOT_FOUND",
                    message=f"目标 Agent 能力目录不存在：{request.target_path.parent}",
                )
            )
        return issues

    def _build_steps(
        self,
        plan_id: str,
        request: OperationRequest,
    ) -> tuple[list[OperationStep], list[PreflightIssue]]:
        info = self._link_adapter.inspect(request.target_path)
        steps: list[OperationStep] = []
        issues: list[PreflightIssue] = []
        if request.operation_type == OperationType.ENABLE_SHARED_INSTALLATION:
            if info.kind == DirectoryEntryKind.REAL_DIRECTORY:
                backup = self._backup_root / plan_id / request.target_path.name
                steps.append(
                    OperationStep(
                        step_type=OperationStepType.BACKUP_DIRECTORY,
                        source=request.target_path,
                        target=backup,
                    )
                )
            elif info.kind == DirectoryEntryKind.DIRECTORY_LINK:
                if (
                    info.resolved_target is not None
                    and normalized_path(info.resolved_target) == request.source_path
                ):
                    return [], []
                issues.append(
                    PreflightIssue(
                        code="LINK_TARGET_CONFLICT",
                        message="目标已经是指向其他来源的目录链接。",
                    )
                )
                return [], issues
            elif info.kind != DirectoryEntryKind.MISSING:
                issues.append(
                    PreflightIssue(
                        code="TARGET_STATE_UNSAFE",
                        message="目标路径状态无法安全转换为共享安装。",
                    )
                )
                return [], issues
            steps.extend(
                [
                    OperationStep(
                        step_type=OperationStepType.CREATE_DIRECTORY_LINK,
                        source=request.source_path,
                        target=request.target_path,
                    ),
                    OperationStep(
                        step_type=OperationStepType.VERIFY_DIRECTORY_LINK,
                        source=request.source_path,
                        target=request.target_path,
                    ),
                ]
            )
        else:
            if info.kind == DirectoryEntryKind.MISSING:
                return [], []
            if (
                info.kind != DirectoryEntryKind.DIRECTORY_LINK
                or info.resolved_target is None
                or normalized_path(info.resolved_target) != request.source_path
            ):
                issues.append(
                    PreflightIssue(
                        code="NOT_EXPECTED_DIRECTORY_LINK",
                        message="停用共享只能移除指向预期来源的目录链接。",
                    )
                )
                return [], issues
            steps.append(
                OperationStep(
                    step_type=OperationStepType.REMOVE_DIRECTORY_LINK,
                    source=request.source_path,
                    target=request.target_path,
                )
            )
        return steps, issues

    def _reverse_steps(
        self,
        steps: list[OperationStep],
        backup_path: Path | None,
    ) -> str | None:
        try:
            for step in reversed(steps):
                if step.step_type == OperationStepType.VERIFY_DIRECTORY_LINK:
                    continue
                if step.step_type == OperationStepType.CREATE_DIRECTORY_LINK:
                    info = self._link_adapter.inspect(step.target)
                    if info.kind in {
                        DirectoryEntryKind.DIRECTORY_LINK,
                        DirectoryEntryKind.BROKEN_LINK,
                    }:
                        self._link_adapter.remove(step.target, step.source)
                elif step.step_type == OperationStepType.BACKUP_DIRECTORY:
                    if backup_path is not None and backup_path.is_dir():
                        if os.path.lexists(step.source):
                            raise FileExistsError(f"恢复目标已存在：{step.source}")
                        shutil.move(str(backup_path), str(step.source))
                elif step.step_type == OperationStepType.REMOVE_DIRECTORY_LINK:
                    if self._link_adapter.inspect(step.target).kind == DirectoryEntryKind.MISSING:
                        self._link_adapter.create(step.target, step.source)
            return None
        except Exception as error:
            return str(error)

    def _finish(
        self,
        plan: OperationPlan,
        status: OperationStatus,
        message: str,
        backup_path: Path | None = None,
        error: str = "",
        completed: list[OperationStep] | None = None,
    ) -> OperationResult:
        self._executed[plan.id] = _ExecutedOperation(plan, backup_path, status)
        self._audit_log.append(
            AuditRecord(
                operation_id=plan.id,
                capability_id=plan.request.capability_id,
                agent_id=plan.request.agent_id,
                operation_type=plan.request.operation_type,
                status=status,
                steps=[step.step_type for step in (completed or plan.steps)],
                backup_path=backup_path,
                error=error,
                created_at=datetime.now(timezone.utc),
            )
        )
        return OperationResult(
            operation_id=plan.id,
            status=status,
            message=message,
            backup_path=backup_path,
            error=error,
        )

    def _is_allowed(self, path: Path) -> bool:
        normalized = normalized_path(path)
        for root in self._allowed_roots:
            try:
                if os.path.commonpath([normalized, root]) == str(root):
                    return True
            except ValueError:
                continue
        return False
