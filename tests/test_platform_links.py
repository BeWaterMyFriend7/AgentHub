from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_hub.platform.links import (
    DirectoryEntryKind,
    current_directory_link_adapter,
)


class PlatformDirectoryLinkTests(unittest.TestCase):
    def test_current_platform_link_can_be_created_verified_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = base / "source"
            target_root = base / "agent"
            target = target_root / "reviewer"
            source.mkdir()
            target_root.mkdir()
            source.joinpath("SKILL.md").write_text("source", encoding="utf-8")
            adapter = current_directory_link_adapter()

            adapter.create(target, source)
            try:
                info = adapter.inspect(target)
                self.assertEqual(info.kind, DirectoryEntryKind.DIRECTORY_LINK)
                self.assertEqual(info.resolved_target, source.resolve())
            finally:
                if adapter.inspect(target).kind in {
                    DirectoryEntryKind.DIRECTORY_LINK,
                    DirectoryEntryKind.BROKEN_LINK,
                }:
                    adapter.remove(target, source)

            self.assertEqual(adapter.inspect(target).kind, DirectoryEntryKind.MISSING)
            self.assertTrue(source.joinpath("SKILL.md").is_file())

    def test_remove_rejects_real_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir) / "real"
            directory.mkdir()
            adapter = current_directory_link_adapter()

            with self.assertRaisesRegex(ValueError, "不是可移除的目录链接"):
                adapter.remove(directory, directory)

            self.assertTrue(directory.is_dir())


if __name__ == "__main__":
    unittest.main()
