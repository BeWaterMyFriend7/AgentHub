from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from agent_hub.platform.links import DirectoryEntryKind


class OperationType(StrEnum):
    ENABLE_SHARED_INSTALLATION = "enable_shared_installation"
    DISABLE_SHARED_INSTALLATION = "disable_shared_installation"


class ConfirmationType(StrEnum):
    INSTALLATION_CHANGE = "installation_change"
    SOURCE_DELETION = "source_deletion"
    PERMANENT_PURGE = "permanent_purge"


class RecoveryLevel(StrEnum):
    AUTOMATIC_ROLLBACK = "automatic_rollback"
    COMPENSATING_RECOVERY = "compensating_recovery"
    MANUAL_RECOVERY = "manual_recovery"
    IRREVERSIBLE = "irreversible"


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class OperationStepType(StrEnum):
    BACKUP_DIRECTORY = "backup_directory"
    CREATE_DIRECTORY_LINK = "create_directory_link"
    VERIFY_DIRECTORY_LINK = "verify_directory_link"
    REMOVE_DIRECTORY_LINK = "remove_directory_link"


class OperationStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    MANUAL_RECOVERY_REQUIRED = "manual_recovery_required"


class StepExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_EXECUTED = "not_executed"
    COMPENSATED = "compensated"


class OperationRequest(BaseModel):
    operation_type: OperationType
    capability_id: str
    agent_id: str
    source_path: Path
    target_path: Path
    operator: str = "local-user"


class PreflightIssue(BaseModel):
    code: str
    message: str
    severity: IssueSeverity = IssueSeverity.ERROR


class OperationStep(BaseModel):
    step_type: OperationStepType
    source: Path | None = None
    target: Path


class OperationStepResult(BaseModel):
    step_type: OperationStepType
    status: StepExecutionStatus
    error: str = ""


class OperationPlan(BaseModel):
    id: str
    request: OperationRequest
    steps: list[OperationStep] = Field(default_factory=list)
    issues: list[PreflightIssue] = Field(default_factory=list)
    confirmation_type: ConfirmationType = ConfirmationType.INSTALLATION_CHANGE
    recovery_level: RecoveryLevel = RecoveryLevel.AUTOMATIC_ROLLBACK
    before_state: DirectoryEntryKind = DirectoryEntryKind.MISSING
    impact_summary: list[str] = Field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not any(issue.severity == IssueSeverity.ERROR for issue in self.issues)


class Confirmation(BaseModel):
    plan_id: str
    confirmation_type: ConfirmationType


class OperationResult(BaseModel):
    operation_id: str
    status: OperationStatus
    message: str
    backup_path: Path | None = None
    error: str = ""


class AuditRecord(BaseModel):
    operation_id: str
    capability_id: str
    agent_id: str
    operation_type: OperationType
    operator: str
    source_path: Path
    target_path: Path
    confirmation_type: ConfirmationType
    recovery_level: RecoveryLevel
    before_state: DirectoryEntryKind
    after_state: DirectoryEntryKind
    status: OperationStatus
    step_results: list[OperationStepResult] = Field(default_factory=list)
    backup_path: Path | None = None
    error: str = ""
    recovery_message: str = ""
    created_at: datetime
