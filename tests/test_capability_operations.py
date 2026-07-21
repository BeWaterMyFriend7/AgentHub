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
)
from agent_hub.platform.links import DirectoryEntryKind, LinkInfo


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
            self.assertEqual(result.status, OperationStatus.SUCCEEDED)
            self.assertEqual(links.inspect(target).resolved_target, source.resolve())
            self.assertTrue(result.backup_path.joinpath("user.txt").is_file())
            self.assertEqual(len(audits.records), 1)

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
            manager = CapabilityOperationManager(
                link_adapter=FailingCreateLinkAdapter(),
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
                target.joinpath("keep.txt").read_text(encoding="utf-8"),
                "保留",
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


if __name__ == "__main__":
    unittest.main()
