from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from agent_hub.agents.models import (
    AgentProfile,
    SessionIntegrationCapabilities,
)


class AgentProfileStore:
    """Persist Agent connection profiles without storing secret values."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("AGENT_HUB_CONFIG")
        self.path = Path(configured).expanduser() if configured else Path.home() / ".agenthub" / "agents.json"

    def list_profiles(self) -> list[AgentProfile]:
        if not self.path.is_file():
            return self.default_profiles()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        profiles = payload.get("profiles", payload) if isinstance(payload, dict) else payload
        if not isinstance(profiles, list):
            raise ValueError("Agent 配置文件格式无效，profiles 必须是数组。")
        result: list[AgentProfile] = []
        profile_ids: set[str] = set()
        for index, item in enumerate(profiles):
            try:
                profile = AgentProfile.model_validate(self._migrate(item))
                if profile.id in profile_ids:
                    raise ValueError(f"Agent Profile ID 重复：{profile.id}")
            except (ValidationError, ValueError) as error:
                profile = self._invalid_profile(index, item, str(error))
            profile_ids.add(profile.id)
            result.append(profile)
        return result

    def save(self, profiles: list[AgentProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "profiles": [profile.model_dump(mode="json") for profile in profiles],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def upsert(self, profile: AgentProfile) -> AgentProfile:
        profiles = self.list_profiles()
        for index, current in enumerate(profiles):
            if current.id == profile.id:
                profiles[index] = profile.model_copy(deep=True)
                break
        else:
            profiles.append(profile.model_copy(deep=True))
        self.save(profiles)
        return profile.model_copy(deep=True)

    def delete(self, profile_id: str) -> bool:
        profiles = self.list_profiles()
        remaining = [profile for profile in profiles if profile.id != profile_id]
        if len(remaining) == len(profiles):
            return False
        self.save(remaining)
        return True

    @staticmethod
    def default_profiles() -> list[AgentProfile]:
        from agent_hub.adapter_factory import AgentAdapterFactory

        return AgentAdapterFactory().default_profiles()

    @staticmethod
    def _migrate(payload: object) -> object:
        if not isinstance(payload, dict) or payload.get("adapter_kind"):
            return payload
        migrated = dict(payload)
        adapter_type = str(migrated.get("adapter_type", "")).lower()
        name = str(migrated.get("name", "")).lower()
        if "codex" in adapter_type or "codex" in name:
            migrated["agent_type"] = "codex"
            migrated["adapter_kind"] = "codex_desktop"
        elif "server" in adapter_type:
            migrated["agent_type"] = "opencode"
            migrated["adapter_kind"] = "opencode_server"
        else:
            migrated["adapter_kind"] = "unsupported"
        return migrated

    @staticmethod
    def _invalid_profile(index: int, payload: object, reason: str) -> AgentProfile:
        raw = payload if isinstance(payload, dict) else {}
        original_id = raw.get("id") or f"item-{index + 1}"
        return AgentProfile(
            id=f"invalid-profile-{index + 1}",
            name=str(raw.get("name") or f"无效 Profile {original_id}"),
            agent_type=str(raw.get("agent_type") or "invalid"),
            adapter_kind="invalid",
            adapter_type="无效 Agent Profile",
            enabled=True,
            connected=False,
            endpoint=str(raw.get("endpoint") or ""),
            capabilities=SessionIntegrationCapabilities(
                session_discovery=False,
                status_detection=False,
                plan_reading=False,
                exact_resume=False,
                event_stream=False,
                resume_launch=False,
            ),
            status_source="AgentHub profile validation",
            last_probe_message=f"配置校验失败：{reason}",
        )
