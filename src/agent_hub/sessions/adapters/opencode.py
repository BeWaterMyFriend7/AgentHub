from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.models import (
    AgentSession,
    OpenSessionResult,
    PlanItem,
    SessionStatus,
)

ResumeLauncher = Callable[[list[str], Mapping[str, str]], bool | None]


def _default_resume_launcher(command: list[str], env: Mapping[str, str]) -> bool:
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    process = subprocess.Popen(command, env=dict(env), creationflags=creationflags)
    time.sleep(1.0)
    return process.poll() is None


class OpenCodeSessionAdapter(SessionAdapter):
    """Map the documented OpenCode Server API to AgentHub sessions."""

    def __init__(
        self,
        profile: AgentProfile,
        *,
        username: str = "opencode",
        password: str,
        executable: str = "opencode",
        client: httpx.AsyncClient | None = None,
        resume_launcher: ResumeLauncher | None = None,
        session_limit: int = 100,
    ) -> None:
        super().__init__(profile)
        self._username = username
        self._password = password
        self._executable = executable
        self._command_prefix = self._resolve_command_prefix(executable)
        self._session_limit = session_limit
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=profile.endpoint.rstrip("/"),
            auth=(username, password),
            timeout=10.0,
        )
        self._request_semaphore = asyncio.Semaphore(20)
        self._resume_launcher = resume_launcher or _default_resume_launcher

    async def list_sessions(self) -> list[AgentSession]:
        response = await self._get_json(
            "/api/session",
            params={"limit": self._session_limit, "order": "desc"},
        )
        native_sessions = response.get("data", [])
        active_ok, active_payload = await self._try_get_json("/api/session/active")
        active = active_payload.get("data", {}) if active_ok else {}
        directories = sorted(
            {
                item.get("location", {}).get("directory")
                for item in native_sessions
                if item.get("location", {}).get("directory")
            }
        )
        status_results = await asyncio.gather(
            *(
                self._try_get_json(
                    "/session/status",
                    params={"directory": item},
                )
                for item in directories
            )
        )
        statuses = dict(zip(directories, status_results, strict=True))

        mapped = await asyncio.gather(
            *(
                self._map_session(
                    item,
                    active.get(item.get("id")),
                    statuses.get(item.get("location", {}).get("directory"), (False, {}))[1].get(
                        item.get("id")
                    ),
                    active_ok
                    or statuses.get(item.get("location", {}).get("directory"), (False, {}))[0],
                )
                for item in native_sessions
            )
        )
        return [session for session in mapped if session is not None]

    async def probe(self) -> ProbeResult:
        checks: list[str] = []
        failures: list[str] = []
        try:
            if not self.profile.enabled:
                failures.append("Agent Profile 已被禁用。")
            health = await self._get_json("/global/health")
            await self._get_json("/api/session/active")
            if not health.get("healthy"):
                failures.append("OpenCode Server 健康检查未通过。")
            else:
                checks.append(f"OpenCode Server {health.get('version', 'unknown')} 健康检查通过。")

            sessions = await self.list_sessions()
            if len(sessions) < 3:
                failures.append(f"仅发现 {len(sessions)} 个内部会话，未达到三个会话的验收门槛。")
            else:
                checks.append(f"成功列出 {len(sessions)} 个内部会话并保留原生会话 ID。")

            if sessions:
                sample = sessions[0]
                await self._get_json(
                    f"/session/{sample.native_session_id}/todo",
                    params={"directory": sample.working_directory},
                )
                checks.append("OpenCode 原生 Todo 端点读取成功。")

            if self.profile.capabilities.exact_resume or self.profile.capabilities.resume_launch:
                if self._command_prefix:
                    checks.append("恢复命令使用官方 CLI attach --session 参数。")
                else:
                    failures.append(f"未找到 OpenCode CLI：{self._executable}")
            else:
                failures.append("Profile 未声明会话恢复或恢复命令启动能力。")
        except (httpx.HTTPError, ValueError) as error:
            failures.append(f"OpenCode Server 探测失败：{error}")

        self.profile.connected = not failures
        self.profile.last_probe_message = "；".join(failures) if failures else "接入能力校验通过"
        return ProbeResult(
            ok=not failures,
            agent_id=self.profile.id,
            title="接入探测通过" if not failures else "接入探测失败",
            message=(
                f"{self.profile.name} 已验证会话发现、Todo 读取和恢复命令入口。"
                if not failures
                else f"{self.profile.name} 尚未达到完整接入标准。"
            ),
            checks=checks,
            failures=failures,
        )

    async def open_session(self, session_id: str) -> OpenSessionResult:
        prefix = f"{self.profile.id}:"
        native_id = session_id.removeprefix(prefix) if session_id.startswith(prefix) else ""
        session = None
        if native_id:
            try:
                native = (await self._get_json(f"/api/session/{native_id}")).get("data")
                active = (await self._get_json("/api/session/active")).get("data", {})
                if native:
                    directory = native.get("location", {}).get("directory")
                    legacy_ok, legacy_statuses = (
                        await self._try_get_json("/session/status", params={"directory": directory})
                        if directory
                        else (False, {})
                    )
                    session = await self._map_session(
                        native,
                        active.get(native_id),
                        legacy_statuses.get(native_id),
                        True,
                    )
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    return self._resume_lookup_failure(session_id, str(error))
            except (httpx.HTTPError, ValueError) as error:
                return self._resume_lookup_failure(session_id, str(error))
        if session is None:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="none",
                message="没有找到该 OpenCode 会话。",
            )

        if not self._command_prefix:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"未找到 OpenCode CLI：{self._executable}",
            )

        command = [
            *self._command_prefix,
            "attach",
            self.profile.endpoint.rstrip("/"),
            "--session",
            session.native_session_id,
            "--username",
            self._username,
        ]
        if session.working_directory:
            command.extend(["--dir", session.working_directory])

        env = os.environ.copy()
        env["OPENCODE_SERVER_USERNAME"] = self._username
        env["OPENCODE_SERVER_PASSWORD"] = self._password
        try:
            started = await asyncio.to_thread(self._resume_launcher, command, env)
        except OSError as error:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"OpenCode 精确恢复启动失败：{error}",
                resume_target=subprocess.list2cmdline(command),
            )
        if started is False:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message="OpenCode 恢复进程启动后立即退出，未确认进入目标会话。",
                resume_target=subprocess.list2cmdline(command),
            )

        return OpenSessionResult(
            ok=True,
            session_id=session_id,
            agent_id=self.profile.id,
            action="resume_session_started",
            message=f"已按原生会话 ID 启动“{session.title}”的恢复命令。",
            resume_target=subprocess.list2cmdline(command),
        )

    async def _map_session(
        self,
        native: dict[str, Any],
        active: dict[str, Any] | None,
        legacy_status: dict[str, Any] | None,
        status_available: bool,
    ) -> AgentSession | None:
        native_id = native.get("id")
        location = native.get("location") or {}
        directory = location.get("directory")
        if not native_id or not directory:
            return None

        todos, messages = await asyncio.gather(
            self._safe_get_json(
                f"/session/{native_id}/todo",
                [],
                params={"directory": directory},
            ),
            self._safe_get_json(
                f"/session/{native_id}/message",
                [],
                params={"directory": directory, "limit": 1},
            ),
        )
        status, reason, confidence = self._map_status(
            active,
            legacy_status,
            status_available,
        )
        plan_items = self._map_todos(todos)
        last_activity = self._last_activity(messages)
        current = next((item.title for item in plan_items if item.status == "current"), None)
        pending = next((item.title for item in plan_items if item.status == "pending"), None)

        updated_ms = (native.get("time") or {}).get("updated")
        updated_at = (
            datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc)
            if isinstance(updated_ms, (int, float))
            else datetime.now(timezone.utc)
        )
        title = native.get("title") or native_id
        return AgentSession(
            id=f"{self.profile.id}:{native_id}",
            native_session_id=native_id,
            agent_id=self.profile.id,
            agent_name=self.profile.name,
            title=title,
            project_name=Path(directory).name or directory,
            working_directory=directory,
            status=status,
            status_reason=reason,
            current_goal="",
            current_step=current or pending or "",
            plan_items=plan_items,
            last_activity=last_activity or "",
            updated_at=updated_at,
            status_source="OpenCode Server API",
            confidence=confidence,
            resumable=(
                self.profile.capabilities.exact_resume
                or self.profile.capabilities.resume_launch
            ),
        )

    @staticmethod
    def _map_status(
        active: dict[str, Any] | None,
        legacy: dict[str, Any] | None,
        status_available: bool,
    ) -> tuple[SessionStatus, str, str]:
        if active and active.get("type") == "running":
            return SessionStatus.EXECUTING, "OpenCode 报告该会话正在运行。", "high"

        native_type = (legacy or {}).get("type")
        if native_type == "busy":
            return SessionStatus.EXECUTING, "OpenCode 报告该会话处于 busy。", "high"
        if native_type == "retry":
            message = (legacy or {}).get("message") or "OpenCode 正在重试。"
            return SessionStatus.EXECUTING, message, "high"
        if native_type == "idle":
            return SessionStatus.UNKNOWN, "OpenCode 报告该会话处于 idle，未推断是否完成。", "medium"
        if not status_available:
            return SessionStatus.UNKNOWN, "OpenCode 状态端点暂时不可用。", "low"
        return (
            SessionStatus.UNKNOWN,
            "OpenCode 状态端点未返回活动状态，未推断是否完成。",
            "medium",
        )

    @staticmethod
    def _map_todos(payload: Any) -> list[PlanItem]:
        if not isinstance(payload, list):
            return []
        status_map = {
            "completed": "done",
            "in_progress": "current",
            "pending": "pending",
            "cancelled": "cancelled",
        }
        result: list[PlanItem] = []
        for index, item in enumerate(payload):
            mapped = status_map.get(item.get("status")) if isinstance(item, dict) else None
            content = item.get("content") if isinstance(item, dict) else None
            if mapped and content:
                result.append(PlanItem(id=str(index + 1), title=content, status=mapped))
        return result

    @staticmethod
    def _last_activity(payload: Any) -> str | None:
        messages = payload if isinstance(payload, list) else []
        for message in messages:
            parts = message.get("parts", []) if isinstance(message, dict) else []
            for part in reversed(parts):
                if part.get("type") == "text" and part.get("text"):
                    return part["text"].strip()
        return None

    async def _get_json(self, path: str, **kwargs: Any) -> Any:
        async with self._request_semaphore:
            response = await self._client.get(path, **kwargs)
        response.raise_for_status()
        return response.json()

    def _resume_lookup_failure(self, session_id: str, detail: str) -> OpenSessionResult:
        return OpenSessionResult(
            ok=False,
            session_id=session_id,
            agent_id=self.profile.id,
            action="resume_session",
            message=f"读取 OpenCode 目标会话失败：{detail}",
        )

    async def _safe_get_json(self, path: str, default: Any, **kwargs: Any) -> Any:
        try:
            return await self._get_json(path, **kwargs)
        except (httpx.HTTPError, ValueError):
            return default

    async def _try_get_json(self, path: str, **kwargs: Any) -> tuple[bool, Any]:
        try:
            return True, await self._get_json(path, **kwargs)
        except (httpx.HTTPError, ValueError):
            return False, {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _resolve_command_prefix(executable: str) -> list[str]:
        resolved = executable if Path(executable).is_file() else shutil.which(executable)
        if not resolved:
            return []
        suffix = Path(resolved).suffix.lower()
        if suffix in {".cmd", ".bat", ".ps1"}:
            native = Path(resolved).parent / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
            return [str(native)] if native.is_file() else []
        return [resolved]
