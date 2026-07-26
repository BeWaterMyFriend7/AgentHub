from __future__ import annotations

import os
import re
from pathlib import Path
from uuid import uuid4

from agent_hub.agents.models import (
    AgentAdapterDefinition,
    AgentProfile,
    AgentProfileInput,
    AgentProfilePatch,
    SessionIntegrationCapabilities,
)
from agent_hub.sessions.adapters import (
    CodexSessionAdapter,
    OpenCodeDesktopSessionAdapter,
    OpenCodeSessionAdapter,
    SessionAdapter,
)


class AgentAdapterFactory:
    def __init__(self) -> None:
        self._definitions = {
            "codex_desktop": AgentAdapterDefinition(
                kind="codex_desktop",
                agent_type="codex",
                name="Codex Desktop",
                description="读取 Codex 本地状态库和 rollout，并使用 Desktop 深链定位任务。",
                fields=["name", "data_path"],
                defaults={"name": "Codex Desktop", "data_path": str(Path.home() / ".codex")},
            ),
            "opencode_desktop": AgentAdapterDefinition(
                kind="opencode_desktop",
                agent_type="opencode",
                name="OpenCode Desktop",
                description="只读 OpenCode Desktop SQLite，会话恢复使用共享数据的官方 CLI。",
                fields=["name", "data_path", "executable"],
                defaults={
                    "name": "OpenCode Desktop",
                    "data_path": str(Path.home() / ".local" / "share" / "opencode" / "opencode.db"),
                    "executable": "opencode",
                },
            ),
            "opencode_server": AgentAdapterDefinition(
                kind="opencode_server",
                agent_type="opencode",
                name="OpenCode CLI / Server",
                description="连接已启动的 OpenCode Server API，并通过 CLI attach 精确恢复会话。",
                fields=["name", "endpoint", "username", "secret_env", "executable"],
                defaults={
                    "name": "OpenCode CLI / Server",
                    "endpoint": "http://127.0.0.1:4096",
                    "username": "opencode",
                    "secret_env": "OPENCODE_SERVER_PASSWORD",
                    "executable": "opencode",
                },
            ),
        }

    def definitions(self) -> list[AgentAdapterDefinition]:
        return [item.model_copy(deep=True) for item in self._definitions.values()]

    def default_profiles(self) -> list[AgentProfile]:
        codex_home = Path.home() / ".codex"
        opencode_db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
        return [
            self.create_profile(
                AgentProfileInput(
                    id="codex-desktop",
                    name="Codex Desktop",
                    agent_type="codex",
                    adapter_kind="codex_desktop",
                    enabled=codex_home.is_dir(),
                    data_path=str(codex_home),
                )
            ),
            self.create_profile(
                AgentProfileInput(
                    id="opencode-desktop",
                    name="OpenCode Desktop",
                    agent_type="opencode",
                    adapter_kind="opencode_desktop",
                    enabled=opencode_db.is_file(),
                    data_path=str(opencode_db),
                    executable="opencode",
                )
            ),
        ]

    def create_profile(self, payload: AgentProfileInput) -> AgentProfile:
        definition = self._definitions.get(payload.adapter_kind)
        if definition is None:
            raise ValueError(f"不支持的 Adapter 类型：{payload.adapter_kind}")
        profile_id = payload.id or self._new_id(payload.adapter_kind, payload.name)
        capabilities, adapter_type, status_source = self._metadata(payload.adapter_kind)
        endpoint = payload.endpoint
        data_path = payload.data_path
        executable = payload.executable
        username = payload.username
        secret_env = payload.secret_env
        if payload.adapter_kind == "codex_desktop":
            endpoint = "local://codex"
            data_path = data_path or str(Path.home() / ".codex")
            executable = None
            username = None
            secret_env = None
        elif payload.adapter_kind == "opencode_desktop":
            endpoint = "local://opencode-desktop"
            data_path = data_path or str(
                Path.home() / ".local" / "share" / "opencode" / "opencode.db"
            )
            executable = executable or "opencode"
            username = None
            secret_env = None
        else:
            endpoint = (
                endpoint
                if endpoint and not endpoint.startswith("local://")
                else "http://127.0.0.1:4096"
            )
            data_path = None
            executable = executable or "opencode"
            username = username or "opencode"
            secret_env = secret_env or "OPENCODE_SERVER_PASSWORD"
        return AgentProfile(
            id=profile_id,
            name=payload.name.strip() or definition.name,
            agent_type=definition.agent_type,
            adapter_kind=payload.adapter_kind,
            adapter_type=adapter_type,
            enabled=payload.enabled,
            connected=False,
            endpoint=endpoint,
            data_path=data_path,
            executable=executable,
            username=username,
            secret_env=secret_env,
            settings=payload.settings,
            capabilities=capabilities,
            status_source=status_source,
        )

    def update_profile(self, profile: AgentProfile, patch: AgentProfilePatch) -> AgentProfile:
        configurable = {
            "id": profile.id,
            "name": profile.name,
            "agent_type": profile.agent_type,
            "adapter_kind": profile.adapter_kind,
            "enabled": profile.enabled,
            "endpoint": profile.endpoint,
            "data_path": profile.data_path,
            "executable": profile.executable,
            "username": profile.username,
            "secret_env": profile.secret_env,
            "settings": profile.settings,
        }
        configurable.update(patch.model_dump(exclude_unset=True))
        return self.create_profile(AgentProfileInput.model_validate(configurable))

    def build(self, profile: AgentProfile) -> SessionAdapter:
        if profile.adapter_kind == "codex_desktop":
            return CodexSessionAdapter(profile, codex_home=profile.data_path or None)
        if profile.adapter_kind == "opencode_desktop":
            return OpenCodeDesktopSessionAdapter(
                profile,
                database=profile.data_path or None,
                executable=profile.executable or "opencode",
            )
        if profile.adapter_kind == "opencode_server":
            secret_env = profile.secret_env or "OPENCODE_SERVER_PASSWORD"
            password = os.environ.get(secret_env)
            if password is None:
                raise ValueError(f"环境变量 {secret_env} 未设置。")
            if not profile.endpoint:
                raise ValueError("OpenCode Server 地址不能为空。")
            return OpenCodeSessionAdapter(
                profile,
                username=profile.username or "opencode",
                password=password,
                executable=profile.executable or "opencode",
            )
        raise ValueError(f"不支持的 Adapter 类型：{profile.adapter_kind}")

    @staticmethod
    def _new_id(kind: str, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or kind.replace("_", "-")
        return f"{slug}-{uuid4().hex[:6]}"

    @staticmethod
    def _metadata(kind: str) -> tuple[SessionIntegrationCapabilities, str, str]:
        if kind == "codex_desktop":
            return (
                SessionIntegrationCapabilities(
                    session_discovery=True,
                    status_detection=True,
                    plan_reading=True,
                    exact_resume=True,
                    event_stream=False,
                    resume_launch=True,
                ),
                "Codex 本地状态 + Desktop 深链",
                "Codex local state polling",
            )
        if kind == "opencode_desktop":
            return (
                SessionIntegrationCapabilities(
                    session_discovery=True,
                    status_detection=True,
                    plan_reading=True,
                    exact_resume=True,
                    event_stream=False,
                    resume_launch=True,
                ),
                "OpenCode Desktop SQLite + CLI Resume",
                "OpenCode Desktop SQLite polling",
            )
        return (
            SessionIntegrationCapabilities(
                session_discovery=True,
                status_detection=True,
                plan_reading=True,
                exact_resume=False,
                event_stream=False,
                resume_launch=True,
            ),
            "OpenCode Server API + CLI Resume",
            "OpenCode Server API polling",
        )
