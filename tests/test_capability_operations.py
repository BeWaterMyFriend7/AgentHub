from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from agent_hub.operations import (
    CapabilityOperationManager,
    Confirmation,
    InMemoryAuditLog,
    OperationRequest,
    OperationStatus,
    OperationType,
    StepExecutionStatus,
)
from agent_hub.platform.links import (
    DirectoryEntryKind,
    LinkInfo,
    current_directory_link_adapter,
)


class FakeDirectoryLinkAdapter:
    def __init__(self) -> None:
        self.links: dict[Path, Path] = {}

    def inspect(self, path: Path) -> LinkInfo:
        normalized = Path(os.path.abspath(path))
        if normalized in self.links:
            target = self.links[normalized]
            kind = (
                DirectoryEntryKind.DIRECTORY_LINK
                if target.is_dir()
                else DirectoryEntryKind.BROKEN_LINK
            )
            return LinkInfo(path=normalized, kind=kind, resolved_target=target)
        if normalized.is_dir():
            return LinkInfo(path=normalized, kind=DirectoryEntryKind.REAL_DIRECTORY)
        if os.path.lexists(normalized):
            return LinkInfo(path=normalized, kind=DirectoryEntryKind.INVALID)
        return LinkInfo(path=normalized, kind=DirectoryEntryKind.MISSING)

    def create(self, target: Path, source: Path) -> None:
        self.links[Path(os.path.abspath(target))] = Path(os.path.abspath(source))

    def remove(self, target: Path, expected_source: Path) -> None:
        normalized = Path(os.path.abspath(target))
        actual = self.links.get(normalized)
        if actual != Path(os.path.abspath(expected_source)):
            raise ValueError("链接目标与操作计划不一致")
        del self.links[normalized]


class FailingCreateLinkAdapter(FakeDirectoryLinkAdapter):
    def create(self, target: Path, source: Path) -> None:
        raise OSError("模拟链接创建失败")


class PartiallyFailingCreateLinkAdapter(FakeDirectoryLinkAdapter):
    def create(self, target: Path, source: Path) -> None:
        super().create(target, source)
        raise OSError("链接已创建，但 Adapter 随后失败")


class CapabilityOperationTests(unittest.TestCase):
    def test_share_real_directory_is_backed_up_and_can_be_rolled_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            target.mkdir(parents=True)
            target.joinpath("user.txt").write_text("用户修改", encoding="utf-8")
            links = FakeDirectoryLinkAdapter()
            audits = InMemoryAuditLog()
            manager = CapabilityOperationManager(
                link_adapter=links,
                audit_log=audits,
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            request = OperationRequest(
                operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                capability_id="skill:reviewer",
                agent_id="opencode",
                source_path=source,
                target_path=target,
            )

            plan = manager.plan(request)
            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )

            self.assertTrue(plan.ready)
            self.assertIn(
                "TARGET_LOCAL_CONTENT_WILL_BE_BACKED_UP",
                {issue.code for issue in plan.issues},
            )
            self.assertEqual(result.status, OperationStatus.SUCCEEDED)
            self.assertEqual(links.inspect(target).resolved_target, source.resolve())
            self.assertTrue(result.backup_path.joinpath("user.txt").is_file())
            self.assertEqual(len(audits.records), 1)
            self.assertGreaterEqual(audits.write_count, len(plan.steps) + 2)

            rollback = manager.rollback(result.operation_id)

            self.assertEqual(rollback.status, OperationStatus.ROLLED_BACK)
            self.assertEqual(
                links.inspect(target).kind,
                DirectoryEntryKind.REAL_DIRECTORY,
            )
            self.assertEqual(
                target.joinpath("user.txt").read_text(encoding="utf-8"),
                "用户修改",
            )

    def test_preflight_rejects_outside_and_protected_targets_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            source.mkdir(parents=True)
            manager = CapabilityOperationManager(
                link_adapter=FakeDirectoryLinkAdapter(),
                audit_log=InMemoryAuditLog(),
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )

            protected = manager.plan(
                OperationRequest(
                    operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=agent_root,
                )
            )
            outside = manager.plan(
                OperationRequest(
                    operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=base.parent / "outside" / "reviewer",
                )
            )

            self.assertFalse(protected.ready)
            self.assertIn("PROTECTED_ROOT", {issue.code for issue in protected.issues})
            self.assertFalse(outside.ready)
            self.assertIn(
                "PATH_OUTSIDE_ALLOWED_ROOT",
                {issue.code for issue in outside.issues},
            )

    def test_create_failure_restores_backed_up_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            target.mkdir(parents=True)
            target.joinpath("keep.txt").write_text("保留", encoding="utf-8")
            audits = InMemoryAuditLog()
            manager = CapabilityOperationManager(
                link_adapter=FailingCreateLinkAdapter(),
                audit_log=audits,
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            plan = manager.plan(
                OperationRequest(
                    operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=target,
                )
            )

            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )

            self.assertEqual(result.status, OperationStatus.ROLLED_BACK)
            self.assertEqual(
                target.joinpath("keep.txt").read_text(encoding="utf-8"),
                "保留",
            )
            record = audits.records[0]
            self.assertEqual(record.operator, "local-user")
            self.assertEqual(record.before_state, DirectoryEntryKind.REAL_DIRECTORY)
            self.assertEqual(record.after_state, DirectoryEntryKind.REAL_DIRECTORY)
            self.assertEqual(
                [item.status for item in record.step_results],
                [
                    StepExecutionStatus.COMPENSATED,
                    StepExecutionStatus.FAILED,
                    StepExecutionStatus.NOT_EXECUTED,
                ],
            )

    def test_partial_create_failure_removes_created_link(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            links = PartiallyFailingCreateLinkAdapter()
            manager = CapabilityOperationManager(
                link_adapter=links,
                audit_log=InMemoryAuditLog(),
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            plan = manager.plan(
                OperationRequest(
                    operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=target,
                )
            )

            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )

            self.assertEqual(result.status, OperationStatus.ROLLED_BACK)
            self.assertEqual(
                links.inspect(target).kind,
                DirectoryEntryKind.MISSING,
            )

    def test_disable_shared_installation_removes_only_link_and_can_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            source.joinpath("SKILL.md").write_text("source", encoding="utf-8")
            links = FakeDirectoryLinkAdapter()
            links.create(target, source)
            manager = CapabilityOperationManager(
                link_adapter=links,
                audit_log=InMemoryAuditLog(),
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            plan = manager.plan(
                OperationRequest(
                    operation_type=OperationType.DISABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=target,
                )
            )

            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )

            self.assertEqual(result.status, OperationStatus.SUCCEEDED)
            self.assertEqual(
                links.inspect(target).kind,
                DirectoryEntryKind.MISSING,
            )
            self.assertTrue(source.joinpath("SKILL.md").is_file())

            rollback = manager.rollback(result.operation_id)

            self.assertEqual(rollback.status, OperationStatus.ROLLED_BACK)
            self.assertEqual(
                links.inspect(target).resolved_target,
                source.resolve(),
            )

    def test_execute_rejects_plan_when_target_changed_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            manager = CapabilityOperationManager(
                link_adapter=FakeDirectoryLinkAdapter(),
                audit_log=InMemoryAuditLog(),
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            plan = manager.plan(
                OperationRequest(
                    operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=target,
                )
            )
            target.mkdir()
            target.joinpath("new.txt").write_text("外部新增", encoding="utf-8")

            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )

            self.assertEqual(result.status, OperationStatus.REJECTED)
            self.assertEqual(result.error, "PLAN_STALE")
            self.assertEqual(
                target.joinpath("new.txt").read_text(encoding="utf-8"),
                "外部新增",
            )

    def test_rollback_reports_manual_recovery_when_target_is_occupied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            source = source_root / "reviewer"
            target = agent_root / "reviewer"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            links = FakeDirectoryLinkAdapter()
            links.create(target, source)
            manager = CapabilityOperationManager(
                link_adapter=links,
                audit_log=InMemoryAuditLog(),
                allowed_roots=[source_root, agent_root],
                protected_roots=[source_root, agent_root],
                backup_root=base / "backups",
            )
            plan = manager.plan(
                OperationRequest(
                    operation_type=OperationType.DISABLE_SHARED_INSTALLATION,
                    capability_id="skill:reviewer",
                    agent_id="opencode",
                    source_path=source,
                    target_path=target,
                )
            )
            result = manager.execute(
                plan,
                Confirmation(plan_id=plan.id, confirmation_type=plan.confirmation_type),
            )
            target.mkdir()
            target.joinpath("external.txt").write_text("外部内容", encoding="utf-8")

            rollback = manager.rollback(result.operation_id)

            self.assertEqual(
                rollback.status,
                OperationStatus.MANUAL_RECOVERY_REQUIRED,
            )
            self.assertTrue(target.joinpath("external.txt").is_file())

    def test_preflight_resolves_parent_links_before_allowed_root_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            outside = base / "outside"
            source = source_root / "reviewer"
            escape = agent_root / "escape"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            outside.mkdir()
            adapter = current_directory_link_adapter()
            adapter.create(escape, outside)
            try:
                manager = CapabilityOperationManager(
                    link_adapter=adapter,
                    audit_log=InMemoryAuditLog(),
                    allowed_roots=[source_root, agent_root],
                    protected_roots=[source_root, agent_root],
                    backup_root=base / "backups",
                )

                plan = manager.plan(
                    OperationRequest(
                        operation_type=OperationType.ENABLE_SHARED_INSTALLATION,
                        capability_id="skill:reviewer",
                        agent_id="opencode",
                        source_path=source,
                        target_path=escape / "reviewer",
                    )
                )

                self.assertFalse(plan.ready)
                self.assertIn(
                    "PATH_OUTSIDE_ALLOWED_ROOT",
                    {issue.code for issue in plan.issues},
                )
            finally:
                adapter.remove(escape, outside)

    def test_preflight_rejects_outside_link_even_when_it_points_inside(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source_root = base / "sources"
            agent_root = base / "agent-skills"
            outside_root = base / "outside"
            source = source_root / "reviewer"
            outside_link = outside_root / "reviewer"
            source.mkdir(parents=True)
            agent_root.mkdir(parents=True)
            outside_root.mkdir()
            adapter = current_directory_link_adapter()
            adapter.create(outside_link, source)
            try:
                manager = CapabilityOperationManager(
                    link_adapter=adapter,
                    audit_log=InMemoryAuditLog(),
                    allowed_roots=[source_root, agent_root],
                    protected_roots=[source_root, agent_root],
                    backup_root=base / "backups",
                )

                plan = manager.plan(
                    OperationRequest(
                        operation_type=OperationType.DISABLE_SHARED_INSTALLATION,
                        capability_id="skill:reviewer",
                        agent_id="opencode",
                        source_path=source,
                        target_path=outside_link,
                    )
                )

                self.assertFalse(plan.ready)
                self.assertIn(
                    "PATH_OUTSIDE_ALLOWED_ROOT",
                    {issue.code for issue in plan.issues},
                )
            finally:
                adapter.remove(outside_link, source)


if __name__ == "__main__":
    unittest.main()
