from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class DirectoryEntryKind(StrEnum):
    MISSING = "missing"
    REAL_DIRECTORY = "real_directory"
    DIRECTORY_LINK = "directory_link"
    BROKEN_LINK = "broken_link"
    INVALID = "invalid"


@dataclass(frozen=True)
class LinkInfo:
    path: Path
    kind: DirectoryEntryKind
    resolved_target: Path | None = None


def normalized_path(path: Path) -> Path:
    return Path(os.path.normcase(os.path.abspath(path)))


class DirectoryLinkAdapter(ABC):
    """跨平台目录链接 seam；调用方不感知 Junction 与 Symbolic Link 差异。"""

    def inspect(self, path: Path) -> LinkInfo:
        normalized = normalized_path(path)
        is_link = os.path.islink(normalized)
        is_junction = bool(
            getattr(os.path, "isjunction", lambda _: False)(normalized)
        )
        if is_link or is_junction:
            resolved = normalized_path(Path(os.path.realpath(normalized)))
            kind = (
                DirectoryEntryKind.DIRECTORY_LINK
                if resolved.is_dir()
                else DirectoryEntryKind.BROKEN_LINK
            )
            return LinkInfo(normalized, kind, resolved)
        if normalized.is_dir():
            return LinkInfo(normalized, DirectoryEntryKind.REAL_DIRECTORY)
        if os.path.lexists(normalized):
            return LinkInfo(normalized, DirectoryEntryKind.INVALID)
        return LinkInfo(normalized, DirectoryEntryKind.MISSING)

    @abstractmethod
    def create(self, target: Path, source: Path) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove(self, target: Path, expected_source: Path) -> None:
        raise NotImplementedError

    def _validate_create(self, target: Path, source: Path) -> tuple[Path, Path]:
        normalized_target = normalized_path(target)
        normalized_source = normalized_path(source)
        if not normalized_source.is_dir():
            raise ValueError(f"能力来源目录不存在：{normalized_source}")
        if os.path.lexists(normalized_target):
            raise FileExistsError(f"目标路径已经存在：{normalized_target}")
        if not normalized_target.parent.is_dir():
            raise ValueError(f"目标 Agent 能力目录不存在：{normalized_target.parent}")
        return normalized_target, normalized_source

    def _validate_remove(
        self,
        target: Path,
        expected_source: Path,
    ) -> tuple[Path, Path]:
        normalized_target = normalized_path(target)
        normalized_source = normalized_path(expected_source)
        info = self.inspect(normalized_target)
        if info.kind not in {
            DirectoryEntryKind.DIRECTORY_LINK,
            DirectoryEntryKind.BROKEN_LINK,
        }:
            raise ValueError("目标不是可移除的目录链接")
        if (
            info.resolved_target is not None
            and normalized_path(info.resolved_target) != normalized_source
        ):
            raise ValueError("目录链接指向与操作计划不一致")
        return normalized_target, normalized_source


class WindowsJunctionAdapter(DirectoryLinkAdapter):
    def create(self, target: Path, source: Path) -> None:
        normalized_target, normalized_source = self._validate_create(target, source)
        environment = os.environ.copy()
        environment["AGENTHUB_LINK_TARGET"] = str(normalized_target)
        environment["AGENTHUB_LINK_SOURCE"] = str(normalized_source)
        script = (
            "$ErrorActionPreference = 'Stop'; "
            "$target = $env:AGENTHUB_LINK_TARGET; "
            "$source = $env:AGENTHUB_LINK_SOURCE; "
            "New-Item -ItemType Junction -Path $target -Target $source | Out-Null"
        )
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or result.stdout.strip())
        info = self.inspect(normalized_target)
        if (
            info.kind != DirectoryEntryKind.DIRECTORY_LINK
            or info.resolved_target != normalized_source
        ):
            raise OSError("Junction 创建后验证失败")

    def remove(self, target: Path, expected_source: Path) -> None:
        normalized_target, _ = self._validate_remove(target, expected_source)
        os.rmdir(normalized_target)


class PosixSymbolicLinkAdapter(DirectoryLinkAdapter):
    def create(self, target: Path, source: Path) -> None:
        normalized_target, normalized_source = self._validate_create(target, source)
        os.symlink(normalized_source, normalized_target, target_is_directory=True)

    def remove(self, target: Path, expected_source: Path) -> None:
        normalized_target, _ = self._validate_remove(target, expected_source)
        normalized_target.unlink()


def current_directory_link_adapter(
    platform_name: str | None = None,
) -> DirectoryLinkAdapter:
    selected = platform_name or os.name
    if selected == "nt":
        return WindowsJunctionAdapter()
    return PosixSymbolicLinkAdapter()
