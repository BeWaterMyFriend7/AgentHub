from __future__ import annotations

from collections.abc import Iterable

from agent_hub.agents.models import AgentProfile


class AgentRegistry:
    """Agent Profile 的统一读取入口。"""

    def __init__(self, profiles: Iterable[AgentProfile]) -> None:
        profile_list = list(profiles)
        self._profiles = {profile.id: profile for profile in profile_list}
        if len(self._profiles) != len(profile_list):
            raise ValueError("Agent Profile ID 必须唯一。")

    def list_profiles(self) -> list[AgentProfile]:
        return [profile.model_copy(deep=True) for profile in self._profiles.values()]

    def profile_for(self, agent_id: str) -> AgentProfile | None:
        profile = self._profiles.get(agent_id)
        return profile.model_copy(deep=True) if profile is not None else None

    def profile_ids(self) -> set[str]:
        return set(self._profiles)

    def replace(self, profiles: Iterable[AgentProfile]) -> None:
        profile_list = list(profiles)
        replacement = {profile.id: profile.model_copy(deep=True) for profile in profile_list}
        if len(replacement) != len(profile_list):
            raise ValueError("Agent Profile ID 必须唯一。")
        self._profiles = replacement

    def set_connection(self, agent_id: str, connected: bool, message: str) -> None:
        profile = self._profiles.get(agent_id)
        if profile is None:
            return
        profile.connected = connected
        profile.last_probe_message = message
