from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.models import AgentSession, OpenSessionResult, PlanItem, SessionStatus

ResumeLauncher = Callable[[list[str], Mapping[str, str]], bool | None]


def _default_resume_launcher(command: list[str], env: Mapping[str, str]) -> bool:
    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    process = subprocess.Popen(command, env=dict(env), creationflags=creationflags)
    time.sleep(1.0)
    return process.poll() is None


class OpenCodeDesktopSessionAdapter(SessionAdapter):
    """Read OpenCode Desktop's shared local database without Desktop Server credentials."""

    REQUIRED_TABLES = {"session", "message", "part", "todo"}

    def __init__(
        self,
        profile: AgentProfile,
        *,
        database: str | Path | None = None,
        executable: str = "opencode",
        resume_launcher: ResumeLauncher | None = None,
        session_limit: int = 100,
    ) -> None:
        super().__init__(profile)
        default_db = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
        self._database = Path(database).expanduser() if database else default_db
        self._executable = executable
        self._command_prefix = self._resolve_command_prefix(executable)
        self._resume_launcher = resume_launcher or _default_resume_launcher
        self._session_limit = session_limit

    async def list_sessions(self) -> list[AgentSession]:
        return await asyncio.to_thread(self._list_sessions_sync)

    async def probe(self) -> ProbeResult:
        checks: list[str] = []
        failures: list[str] = []
        if not self.profile.enabled:
            failures.append("Agent Profile 已被禁用。")
        if not self._database.is_file():
            failures.append(f"未找到 OpenCode Desktop 数据库：{self._database}")
        else:
            try:
                tables = await asyncio.to_thread(self._table_names)
                missing = self.REQUIRED_TABLES - tables
                if missing:
                    failures.append(f"OpenCode Desktop 数据库缺少表：{', '.join(sorted(missing))}")
                else:
                    checks.append("OpenCode Desktop 会话、消息和 Todo 表结构可读取。")
                    sessions = await self.list_sessions()
                    checks.append(f"成功读取 {len(sessions)} 个顶层会话并保留原生会话 ID。")
                    if len(sessions) < 3:
                        failures.append("发现的顶层会话少于三个，未达到多会话验收门槛。")
            except (OSError, sqlite3.Error, ValueError) as error:
                failures.append(f"OpenCode Desktop 数据读取失败：{error}")
        if self._command_prefix:
            checks.append("已找到 OpenCode CLI，可按原生会话 ID 恢复。")
        else:
            failures.append(f"未找到 OpenCode CLI：{self._executable}")

        self.profile.connected = not failures
        self.profile.last_probe_message = "；".join(failures) if failures else "接入能力校验通过"
        return ProbeResult(
            ok=not failures,
            agent_id=self.profile.id,
            title="接入探测通过" if not failures else "接入探测失败",
            message=(
                f"{self.profile.name} 已验证 Desktop 会话发现、状态读取、Todo 和恢复入口。"
                if not failures
                else f"{self.profile.name} 尚未达到完整接入标准。"
            ),
            checks=checks,
            failures=failures,
        )

    async def open_session(self, session_id: str) -> OpenSessionResult:
        native_id = self._native_id(session_id)
        if not native_id:
            return self._missing(session_id)
        try:
            directory = await asyncio.to_thread(self._session_directory, native_id)
        except sqlite3.Error as error:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"读取 OpenCode Desktop 会话失败：{error}",
            )
        if directory is None:
            return self._missing(session_id)
        if not self._command_prefix:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"未找到 OpenCode CLI：{self._executable}",
            )
        command = [*self._command_prefix, directory, "--session", native_id]
        try:
            started = await asyncio.to_thread(self._resume_launcher, command, os.environ.copy())
        except OSError as error:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"OpenCode 会话恢复启动失败：{error}",
                resume_target=subprocess.list2cmdline(command),
            )
        return OpenSessionResult(
            ok=started is not False,
            session_id=session_id,
            agent_id=self.profile.id,
            action="resume_session_started" if started is not False else "resume_session",
            message=(
                "已使用 Desktop 共享会话库，按原生会话 ID 启动 OpenCode CLI。"
                if started is not False
                else "OpenCode 恢复进程启动后立即退出。"
            ),
            resume_target=subprocess.list2cmdline(command),
        )

    def _list_sessions_sync(self) -> list[AgentSession]:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, title, directory, time_updated, time_archived
                FROM session
                WHERE parent_id IS NULL
                ORDER BY time_updated DESC
                LIMIT ?
                """,
                (self._session_limit,),
            ).fetchall()
            if not rows:
                return []
            native_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" for _ in native_ids)
            messages = connection.execute(
                f"SELECT id, session_id, time_created, data FROM message WHERE session_id IN ({placeholders}) ORDER BY time_created DESC",
                native_ids,
            ).fetchall()
            parts = connection.execute(
                f"SELECT message_id, session_id, time_created, data FROM part WHERE session_id IN ({placeholders}) ORDER BY time_created DESC",
                native_ids,
            ).fetchall()
            todos = connection.execute(
                f"SELECT session_id, content, status, position FROM todo WHERE session_id IN ({placeholders}) ORDER BY session_id, position",
                native_ids,
            ).fetchall()

        latest_messages: dict[str, dict[str, Any]] = {}
        message_roles: dict[str, str] = {}
        latest_user_message: dict[str, str] = {}
        for row in messages:
            data = self._json(row["data"])
            message_roles[row["id"]] = str(data.get("role", ""))
            latest_messages.setdefault(row["session_id"], data)
            if data.get("role") == "user":
                latest_user_message.setdefault(row["session_id"], row["id"])

        latest_text: dict[str, str] = {}
        user_text: dict[str, str] = {}
        for row in parts:
            data = self._json(row["data"])
            text = data.get("text") if data.get("type") == "text" else None
            if not isinstance(text, str) or not text.strip():
                continue
            cleaned = text.strip()
            latest_text.setdefault(row["session_id"], cleaned)
            if message_roles.get(row["message_id"]) == "user":
                user_text.setdefault(row["session_id"], cleaned)

        todo_map: dict[str, list[PlanItem]] = {native_id: [] for native_id in native_ids}
        status_map = {
            "completed": "done",
            "in_progress": "current",
            "pending": "pending",
            "cancelled": "cancelled",
        }
        for row in todos:
            mapped = status_map.get(row["status"])
            if mapped:
                todo_map[row["session_id"]].append(
                    PlanItem(id=str(row["position"] + 1), title=row["content"], status=mapped)
                )

        result: list[AgentSession] = []
        for row in rows:
            native_id = row["id"]
            plans = todo_map[native_id]
            status, reason, confidence = self._map_status(
                latest_messages.get(native_id), row["time_archived"]
            )
            current = next((item.title for item in plans if item.status == "current"), None)
            pending = next((item.title for item in plans if item.status == "pending"), None)
            directory = row["directory"]
            result.append(
                AgentSession(
                    id=f"{self.profile.id}:{native_id}",
                    native_session_id=native_id,
                    agent_id=self.profile.id,
                    agent_name=self.profile.name,
                    title=row["title"] or native_id,
                    project_name=Path(directory).name or directory,
                    working_directory=directory,
                    status=status,
                    status_reason=reason,
                    current_goal=self._truncate(user_text.get(native_id, "")),
                    current_step=current or pending or "",
                    plan_items=plans,
                    last_activity=self._truncate(latest_text.get(native_id, "")),
                    updated_at=datetime.fromtimestamp(row["time_updated"] / 1000, tz=timezone.utc),
                    status_source="OpenCode Desktop SQLite",
                    confidence=confidence,
                    resumable=bool(self._command_prefix),
                )
            )
        return result

    @staticmethod
    def _map_status(
        message: dict[str, Any] | None, archived_at: int | None
    ) -> tuple[SessionStatus, str, str]:
        if archived_at is not None:
            return SessionStatus.CLOSED, "OpenCode Desktop 已归档该会话。", "high"
        if not message:
            return SessionStatus.UNKNOWN, "会话没有可用于判断状态的消息。", "low"
        error = message.get("error")
        if error:
            name = error.get("name") if isinstance(error, dict) else str(error)
            return SessionStatus.INTERRUPTED, f"最近一次 OpenCode 响应异常结束：{name}", "high"
        role = message.get("role")
        completed = (message.get("time") or {}).get("completed")
        if role == "assistant" and not completed:
            return SessionStatus.EXECUTING, "OpenCode Desktop 最近的 assistant 响应尚未完成。", "high"
        if role == "user":
            return SessionStatus.EXECUTING, "最近消息来自用户，尚未观察到对应 assistant 完成事件。", "medium"
        if role == "assistant" and completed:
            return SessionStatus.UNKNOWN, "最近一轮响应已结束，但会话未归档，未推断为已完成。", "medium"
        return SessionStatus.UNKNOWN, "OpenCode Desktop 未提供明确的当前运行状态。", "low"

    def _table_names(self) -> set[str]:
        with closing(self._connect()) as connection:
            return {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

    def _session_directory(self, native_id: str) -> str | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT directory FROM session WHERE id = ?", (native_id,)).fetchone()
            return row[0] if row else None

    def _connect(self) -> sqlite3.Connection:
        uri = self._database.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5.0)
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _native_id(self, session_id: str) -> str:
        prefix = f"{self.profile.id}:"
        return session_id.removeprefix(prefix) if session_id.startswith(prefix) else ""

    def _missing(self, session_id: str) -> OpenSessionResult:
        return OpenSessionResult(
            ok=False,
            session_id=session_id,
            agent_id=self.profile.id,
            action="none",
            message="没有找到该 OpenCode Desktop 会话。",
        )

    @staticmethod
    def _json(raw: str) -> dict[str, Any]:
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _truncate(value: str, limit: int = 360) -> str:
        return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"

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
