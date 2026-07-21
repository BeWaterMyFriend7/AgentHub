from __future__ import annotations

import fnmatch
import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_hub.capabilities.models import (
    Capability,
    CapabilityInstallation,
    CapabilityLocation,
    CapabilityMatrix,
    CapabilitySource,
    CapabilityType,
    InstallationState,
)
from agent_hub.platform.links import DirectoryEntryKind, LinkInfo, normalized_path


class LinkInspector(Protocol):
    def inspect(self, path: Path) -> LinkInfo: ...


@dataclass(frozen=True)
class _DiscoveredSkill:
    location: CapabilityLocation
    name: str
    description: str
    path: Path
    entry_kind: DirectoryEntryKind
    resolved_source: Path | None
    fingerprint: str
    has_manifest: bool
    validation_errors: tuple[str, ...]


def _parse_skill_manifest(skill_dir: Path) -> tuple[str, str, bool]:
    manifest = skill_dir / "SKILL.md"
    if not manifest.is_file():
        return skill_dir.name, "", False
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return skill_dir.name, "", False

    name = skill_dir.name
    description = ""
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, separator, value = line.partition(":")
            if not separator:
                continue
            normalized_key = key.strip().lower()
            normalized_value = value.strip().strip('"').strip("'")
            if normalized_key == "name" and normalized_value:
                name = normalized_value
            elif normalized_key == "description":
                description = normalized_value
    return name, description, True


def _content_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    ignored_directories = {".git", "__pycache__", "node_modules"}
    try:
        for current_root, directories, files in os.walk(root):
            directories[:] = sorted(
                item for item in directories if item not in ignored_directories
            )
            for filename in sorted(files):
                path = Path(current_root) / filename
                relative = path.relative_to(root).as_posix()
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(path.read_bytes())
                digest.update(b"\0")
        return digest.hexdigest()
    except OSError:
        return ""


class CapabilityInventory:
    """发现并归一化能力来源与 Agent 安装；不执行任何文件变更。"""

    def __init__(self, link_inspector: LinkInspector) -> None:
        self._link_inspector = link_inspector

    def discover(
        self,
        locations: list[CapabilityLocation],
        source_paths: dict[str, Path] | None = None,
    ) -> CapabilityMatrix:
        selected_sources = {
            capability_id: normalized_path(path)
            for capability_id, path in (source_paths or {}).items()
        }
        discovered = self._scan_skills(locations)
        grouped: dict[str, list[_DiscoveredSkill]] = defaultdict(list)
        for item in discovered:
            grouped[item.name].append(item)

        capabilities: list[Capability] = []
        for name, items in grouped.items():
            capabilities.extend(
                self._build_skill_variants(
                    name,
                    items,
                    locations,
                    selected_sources.get(f"skill:{name}"),
                )
            )
        capabilities.sort(key=lambda item: (item.capability_type, item.name.lower()))
        return CapabilityMatrix(capabilities=capabilities, locations=locations)

    def _scan_skills(
        self,
        locations: list[CapabilityLocation],
    ) -> list[_DiscoveredSkill]:
        results: list[_DiscoveredSkill] = []
        for location in locations:
            if location.capability_type != CapabilityType.SKILL:
                continue
            root = normalized_path(location.root)
            if not root.is_dir():
                continue
            for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if any(fnmatch.fnmatch(path.name, pattern) for pattern in location.ignore_patterns):
                    continue
                info = self._link_inspector.inspect(path)
                if info.kind not in {
                    DirectoryEntryKind.REAL_DIRECTORY,
                    DirectoryEntryKind.DIRECTORY_LINK,
                    DirectoryEntryKind.BROKEN_LINK,
                }:
                    continue
                content_path = (
                    info.resolved_target
                    if info.kind == DirectoryEntryKind.DIRECTORY_LINK
                    and info.resolved_target is not None
                    else path
                )
                name, description, has_manifest = _parse_skill_manifest(content_path)
                errors: list[str] = []
                if info.kind == DirectoryEntryKind.BROKEN_LINK:
                    errors.append("目录链接已断开")
                elif not has_manifest:
                    errors.append("缺少 SKILL.md")
                fingerprint = (
                    _content_fingerprint(content_path)
                    if has_manifest and content_path.is_dir()
                    else ""
                )
                results.append(
                    _DiscoveredSkill(
                        location=location,
                        name=name,
                        description=description,
                        path=normalized_path(path),
                        entry_kind=info.kind,
                        resolved_source=(
                            normalized_path(info.resolved_target)
                            if info.resolved_target is not None
                            else None
                        ),
                        fingerprint=fingerprint,
                        has_manifest=has_manifest,
                        validation_errors=tuple(errors),
                    )
                )
        return results

    def _build_skill_variants(
        self,
        name: str,
        discovered: list[_DiscoveredSkill],
        locations: list[CapabilityLocation],
        selected_source: Path | None,
    ) -> list[Capability]:
        source_paths = self._source_candidates(discovered, selected_source)
        if not source_paths:
            return [
                self._build_skill_variant(
                    name,
                    discovered,
                    locations,
                    source_path=None,
                    identity_conflict=False,
                )
            ]
        identity_conflict = len(source_paths) > 1
        return [
            self._build_skill_variant(
                name,
                discovered,
                locations,
                source_path=source_path,
                identity_conflict=identity_conflict,
            )
            for source_path in source_paths
        ]

    def _build_skill_variant(
        self,
        name: str,
        discovered: list[_DiscoveredSkill],
        locations: list[CapabilityLocation],
        source_path: Path | None,
        identity_conflict: bool,
    ) -> Capability:
        source_fingerprint = ""
        if source_path is not None:
            matching = next(
                (item for item in discovered if item.path == source_path),
                None,
            )
            source_fingerprint = (
                matching.fingerprint
                if matching is not None
                else _content_fingerprint(source_path)
            )

        installations: list[CapabilityInstallation] = []
        for location in locations:
            if location.capability_type != CapabilityType.SKILL:
                continue
            agent_items = [
                item
                for item in discovered
                if item.location.agent_id == location.agent_id
            ]
            item = self._select_variant_installation(
                agent_items,
                source_path,
                source_fingerprint,
            )
            if item is None:
                installations.append(
                    CapabilityInstallation(
                        agent_id=location.agent_id,
                        agent_name=location.agent_name,
                        state=InstallationState.MISSING,
                    )
                )
                continue
            installations.append(
                CapabilityInstallation(
                    agent_id=location.agent_id,
                    agent_name=location.agent_name,
                    path=item.path,
                    entry_kind=item.entry_kind,
                    resolved_source=item.resolved_source,
                    fingerprint=item.fingerprint,
                    state=self._installation_state(
                        item,
                        source_path,
                        source_fingerprint,
                    ),
                    validation_errors=list(item.validation_errors),
                )
            )

        source_identity = (
            hashlib.sha256(os.fspath(source_path).encode("utf-8")).hexdigest()[:16]
            if source_path is not None
            else "unresolved"
        )
        capability_id = f"skill:{name}@{source_identity}"
        source = (
            CapabilitySource(
                id=f"source:{source_identity}",
                path=source_path,
                fingerprint=source_fingerprint,
                manifest_id=name,
            )
            if source_path is not None
            else None
        )
        description = self._variant_description(discovered, source_path)
        return Capability(
            id=capability_id,
            capability_type=CapabilityType.SKILL,
            name=name,
            description=description,
            source=source,
            installations=installations,
            identity_conflict=identity_conflict,
        )

    @staticmethod
    def _source_candidates(
        discovered: list[_DiscoveredSkill],
        selected_source: Path | None,
    ) -> list[Path]:
        real_directories = [
            item
            for item in discovered
            if item.entry_kind == DirectoryEntryKind.REAL_DIRECTORY
            and item.has_manifest
        ]
        candidates: list[Path] = []
        known_fingerprints: set[str] = set()
        if selected_source is not None:
            candidates.append(selected_source)
            selected_item = next(
                (item for item in discovered if item.path == selected_source),
                None,
            )
            selected_fingerprint = (
                selected_item.fingerprint
                if selected_item is not None
                else _content_fingerprint(selected_source)
            )
            if selected_fingerprint:
                known_fingerprints.add(selected_fingerprint)

        for item in sorted(real_directories, key=lambda entry: str(entry.path)):
            if item.path in candidates:
                continue
            if item.fingerprint and item.fingerprint in known_fingerprints:
                continue
            candidates.append(item.path)
            if item.fingerprint:
                known_fingerprints.add(item.fingerprint)

        for item in discovered:
            resolved = item.resolved_source
            if (
                item.entry_kind == DirectoryEntryKind.DIRECTORY_LINK
                and resolved is not None
                and resolved.is_dir()
                and resolved not in candidates
            ):
                fingerprint = item.fingerprint or _content_fingerprint(resolved)
                if fingerprint and fingerprint in known_fingerprints:
                    continue
                candidates.append(resolved)
                if fingerprint:
                    known_fingerprints.add(fingerprint)
        return candidates

    @staticmethod
    def _select_variant_installation(
        items: list[_DiscoveredSkill],
        source_path: Path | None,
        source_fingerprint: str,
    ) -> _DiscoveredSkill | None:
        if not items:
            return None
        if source_path is None:
            return items[0]
        exact = next((item for item in items if item.path == source_path), None)
        if exact is not None:
            return exact
        shared = next(
            (item for item in items if item.resolved_source == source_path),
            None,
        )
        if shared is not None:
            return shared
        matching_copy = next(
            (
                item
                for item in items
                if source_fingerprint
                and item.fingerprint == source_fingerprint
                and item.entry_kind == DirectoryEntryKind.REAL_DIRECTORY
            ),
            None,
        )
        return matching_copy or items[0]

    @staticmethod
    def _variant_description(
        discovered: list[_DiscoveredSkill],
        source_path: Path | None,
    ) -> str:
        if source_path is not None:
            source_item = next(
                (
                    item
                    for item in discovered
                    if item.path == source_path and item.description
                ),
                None,
            )
            if source_item is not None:
                return source_item.description
        return next(
            (item.description for item in discovered if item.description),
            "",
        )

    @staticmethod
    def _installation_state(
        item: _DiscoveredSkill,
        source_path: Path | None,
        source_fingerprint: str,
    ) -> InstallationState:
        if item.entry_kind == DirectoryEntryKind.BROKEN_LINK:
            return InstallationState.BROKEN_LINK
        if not item.has_manifest:
            return InstallationState.INVALID
        if source_path is not None and item.path == source_path:
            return InstallationState.SOURCE
        if item.entry_kind == DirectoryEntryKind.DIRECTORY_LINK:
            if source_path is not None and item.resolved_source == source_path:
                return InstallationState.SHARED
            return InstallationState.CONFLICT
        if item.entry_kind == DirectoryEntryKind.REAL_DIRECTORY:
            if source_path is None:
                return InstallationState.CONFLICT
            if source_fingerprint and item.fingerprint == source_fingerprint:
                return InstallationState.LOCAL_COPY
            return InstallationState.CONFLICT
        return InstallationState.INVALID
