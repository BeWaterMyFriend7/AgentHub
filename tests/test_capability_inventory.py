from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_hub.capabilities import (
    CapabilityInventory,
    CapabilityLocation,
    CapabilityType,
    InstallationState,
)
from agent_hub.platform.links import DirectoryEntryKind, LinkInfo


class FakeLinkInspector:
    def __init__(self, links: dict[Path, Path] | None = None) -> None:
        self._links = {
            path.resolve(): target.resolve()
            for path, target in (links or {}).items()
        }

    def inspect(self, path: Path) -> LinkInfo:
        normalized = path.resolve()
        if normalized in self._links:
            return LinkInfo(
                path=path,
                kind=DirectoryEntryKind.DIRECTORY_LINK,
                resolved_target=self._links[normalized],
            )
        if path.is_dir():
            return LinkInfo(path=path, kind=DirectoryEntryKind.REAL_DIRECTORY)
        return LinkInfo(path=path, kind=DirectoryEntryKind.MISSING)


def write_skill(path: Path, name: str, description: str, body: str = "") -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


class CapabilityInventoryTests(unittest.TestCase):
    def test_skill_manifest_and_content_fingerprint_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "codex"
            skill = root / "reviewer"
            write_skill(skill, "reviewer", "审查代码", "第一版")
            inventory = CapabilityInventory(FakeLinkInspector())
            location = CapabilityLocation(
                agent_id="codex",
                agent_name="Codex",
                capability_type=CapabilityType.SKILL,
                root=root,
            )

            first = inventory.discover([location])
            first_capability = first.capabilities[0]
            write_skill(skill, "reviewer", "审查代码", "第二版")
            second = inventory.discover([location])

            self.assertEqual(first_capability.name, "reviewer")
            self.assertEqual(first_capability.description, "审查代码")
            self.assertEqual(
                first_capability.installations[0].state,
                InstallationState.SOURCE,
            )
            self.assertNotEqual(
                first_capability.source.fingerprint,
                second.capabilities[0].source.fingerprint,
            )

    def test_shared_conflicting_and_missing_installations_form_one_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            codex_root = base / "codex"
            opencode_root = base / "opencode"
            claude_root = base / "claude"
            source = codex_root / "reviewer"
            shared = opencode_root / "reviewer"
            conflict = claude_root / "reviewer"
            write_skill(source, "reviewer", "审查代码", "统一来源")
            write_skill(shared, "reviewer", "审查代码", "占位目录")
            write_skill(conflict, "reviewer", "审查代码", "用户修改")
            locations = [
                CapabilityLocation(
                    agent_id="codex",
                    agent_name="Codex",
                    capability_type=CapabilityType.SKILL,
                    root=codex_root,
                ),
                CapabilityLocation(
                    agent_id="opencode",
                    agent_name="OpenCode",
                    capability_type=CapabilityType.SKILL,
                    root=opencode_root,
                ),
                CapabilityLocation(
                    agent_id="claude",
                    agent_name="Claude Code",
                    capability_type=CapabilityType.SKILL,
                    root=claude_root,
                ),
                CapabilityLocation(
                    agent_id="missing",
                    agent_name="Missing Agent",
                    capability_type=CapabilityType.SKILL,
                    root=base / "missing",
                ),
            ]
            inventory = CapabilityInventory(
                FakeLinkInspector({shared: source})
            )

            result = inventory.discover(
                locations,
                source_paths={"skill:reviewer": source},
            )
            capability = result.capabilities[0]
            states = {
                item.agent_id: item.state for item in capability.installations
            }

            self.assertEqual(states["codex"], InstallationState.SOURCE)
            self.assertEqual(states["opencode"], InstallationState.SHARED)
            self.assertEqual(states["claude"], InstallationState.CONFLICT)
            self.assertEqual(states["missing"], InstallationState.MISSING)
            self.assertEqual(capability.source.path, source.resolve())

    def test_same_name_with_distinct_content_is_not_assigned_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            first_root = base / "first"
            second_root = base / "second"
            write_skill(first_root / "reviewer", "reviewer", "审查代码", "版本 A")
            write_skill(second_root / "reviewer", "reviewer", "审查代码", "版本 B")
            inventory = CapabilityInventory(FakeLinkInspector())

            result = inventory.discover(
                [
                    CapabilityLocation(
                        agent_id="first",
                        agent_name="First Agent",
                        capability_type=CapabilityType.SKILL,
                        root=first_root,
                    ),
                    CapabilityLocation(
                        agent_id="second",
                        agent_name="Second Agent",
                        capability_type=CapabilityType.SKILL,
                        root=second_root,
                    ),
                ]
            )
            capability = result.capabilities[0]

            self.assertTrue(capability.identity_conflict)
            self.assertIsNone(capability.source)
            self.assertEqual(
                {item.state for item in capability.installations},
                {InstallationState.CONFLICT},
            )


if __name__ == "__main__":
    unittest.main()
