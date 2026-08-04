from __future__ import annotations

from pathlib import Path

from agent_hub.capabilities.models import CapabilityLocation, CapabilityType


def default_capability_locations() -> list[CapabilityLocation]:
    """返回 Codex、Claude Code、OpenCode 的默认 Skill 目录预设。"""
    home = Path.home()
    return [
        CapabilityLocation(
            agent_id="codex",
            agent_name="Codex",
            capability_type=CapabilityType.SKILL,
            root=home / ".codex" / "skills",
        ),
        CapabilityLocation(
            agent_id="claude_code",
            agent_name="Claude Code",
            capability_type=CapabilityType.SKILL,
            root=home / ".claude" / "skills",
        ),
        CapabilityLocation(
            agent_id="opencode",
            agent_name="OpenCode",
            capability_type=CapabilityType.SKILL,
            root=home / ".config" / "opencode" / "skills",
        ),
    ]
