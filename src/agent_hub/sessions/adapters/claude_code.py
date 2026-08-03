from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.models import AgentSession, OpenSessionResult, SessionStatus


LaunchCommand = Callable[[list[str], str | None], object]


def _default_launcher(args: list[str], cwd: str | None) -> subprocess.Popen[bytes]:
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    return subprocess.Popen(args, cwd=cwd or None, creationflags=flags)


class ClaudeCodeSessionAdapter(SessionAdapter):
    """Read Claude Code project JSONL files and resume sessions through the CLI."""

    def __init__(
        self,
        profile: AgentProfile,
        *,
        projects_dir: str | Path | None = None,
        executable: str = "claude",
        launcher: LaunchCommand | None = None,
        session_limit: int = 100,
        tail_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        super().__init__(profile)
        self._projects_dir = Path(
            projects_dir or profile.data_path or Path.home() / ".claude" / "projects"
        ).expanduser()
        self._executable = executable
        self._launcher = launcher or _default_launcher
        self._session_limit = session_limit
        self._tail_bytes = tail_bytes
        self._working_directories: dict[str, str | None] = {}

    async def list_sessions(self) -> list[AgentSession]:
        return await asyncio.to_thread(self._list_sessions_sync)

    async def probe(self) -> ProbeResult:
        failures: list[str] = []
        checks: list[str] = []
        if not self._projects_dir.is_dir():
            failures.append(f"未找到 Claude Code 会话目录：{self._projects_dir}")
        if not shutil.which(self._executable) and not Path(self._executable).is_file():
            failures.append(f"未找到 Claude Code CLI：{self._executable}")
        sessions = await self.list_sessions() if not failures else []
        if sessions:
            checks.append(f"成功读取 {len(sessions)} 个 Claude Code 会话。")
            checks.append("恢复入口使用 claude --resume <session-id>。")
        elif not failures:
            failures.append("Claude Code 会话目录中没有可读取的 JSONL。")
        self.profile.connected = not failures
        self.profile.last_probe_message = "；".join(failures) if failures else "接入能力校验通过"
        return ProbeResult(
            ok=not failures,
            agent_id=self.profile.id,
            title="接入探测通过" if not failures else "接入探测失败",
            message="Claude Code 会话读取与恢复入口已验证。" if not failures else "Claude Code 接入未就绪。",
            checks=checks,
            failures=failures,
        )

    async def open_session(self, session_id: str) -> OpenSessionResult:
        prefix = f"{self.profile.id}:"
        native_id = session_id.removeprefix(prefix) if session_id.startswith(prefix) else ""
        if not native_id:
            return self._missing(session_id)
        if native_id not in self._working_directories:
            await self.list_sessions()
        if native_id not in self._working_directories:
            return self._missing(session_id)
        args = [self._executable, "--resume", native_id]
        try:
            launched = await asyncio.to_thread(
                self._launcher,
                args,
                self._working_directories[native_id],
            )
        except OSError as error:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="resume_session",
                message=f"启动 Claude Code 恢复失败：{error}",
                resume_target=" ".join(args),
            )
        if isinstance(launched, subprocess.Popen):
            await asyncio.sleep(0.2)
            exit_code = launched.poll()
            if exit_code is not None:
                return OpenSessionResult(
                    ok=False,
                    session_id=session_id,
                    agent_id=self.profile.id,
                    action="resume_session",
                    message=f"Claude Code 进程启动后立即退出（exit={exit_code}）。",
                    resume_target=" ".join(args),
                )
        return OpenSessionResult(
            ok=True,
            session_id=session_id,
            agent_id=self.profile.id,
            action="resume_session",
            message="已使用原生 Session ID 启动 Claude Code 恢复。",
            resume_target=" ".join(args),
        )

    def _list_sessions_sync(self) -> list[AgentSession]:
        if not self._projects_dir.is_dir():
            return []
        paths = sorted(
            self._projects_dir.glob("**/*.jsonl"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[: self._session_limit]
        sessions: list[AgentSession] = []
        working_directories: dict[str, str | None] = {}
        for path in paths:
            events = self._read_events(path)
            if not events:
                continue
            native_id = str(next((item.get("sessionId") for item in events if item.get("sessionId")), path.stem))
            directory = next(
                (str(item.get("cwd")) for item in reversed(events) if item.get("cwd")),
                None,
            )
            title = self._first_user_text(events) or path.stem
            activity = self._last_assistant_text(events)
            last_type = str(events[-1].get("type") or "")
            status = SessionStatus.CLOSED if last_type == "assistant" else SessionStatus.EXECUTING
            reason = (
                "Claude Code JSONL 最后一条记录是 assistant 响应。"
                if status == SessionStatus.CLOSED
                else "Claude Code JSONL 最后一条记录尚未出现 assistant 响应。"
            )
            updated = self._updated_at(events[-1], path)
            working_directories[native_id] = directory
            sessions.append(
                AgentSession(
                    id=f"{self.profile.id}:{native_id}",
                    native_session_id=native_id,
                    agent_id=self.profile.id,
                    agent_name=self.profile.name,
                    title=self._compact(title, 240),
                    project_name=Path(directory).name if directory else path.parent.name,
                    working_directory=directory,
                    status=status,
                    status_reason=reason,
                    current_goal="",
                    current_step="",
                    last_activity=self._compact(activity),
                    updated_at=updated,
                    status_source="Claude Code project JSONL",
                    confidence="medium",
                    resumable=True,
                )
            )
        self._working_directories = working_directories
        return sessions

    def _read_events(self, path: Path) -> list[dict[str, Any]]:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - self._tail_bytes)
            handle.seek(start)
            data = handle.read()
        if start:
            newline = data.find(b"\n")
            data = data[newline + 1 :] if newline >= 0 else b""
        events: list[dict[str, Any]] = []
        for line in data.decode("utf-8", errors="replace").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events

    @classmethod
    def _first_user_text(cls, events: list[dict[str, Any]]) -> str:
        for event in events:
            if event.get("type") == "user":
                text = cls._message_text(event.get("message"))
                if text:
                    return text
        return ""

    @classmethod
    def _last_assistant_text(cls, events: list[dict[str, Any]]) -> str:
        for event in reversed(events):
            if event.get("type") == "assistant":
                text = cls._message_text(event.get("message"))
                if text:
                    return text
        return ""

    @staticmethod
    def _message_text(message: object) -> str:
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text", "")).strip()
                for item in content
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
            )
        return ""

    @staticmethod
    def _updated_at(event: dict[str, Any], path: Path) -> datetime:
        value = event.get("timestamp")
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    def _missing(self, session_id: str) -> OpenSessionResult:
        return OpenSessionResult(
            ok=False,
            session_id=session_id,
            agent_id=self.profile.id,
            action="none",
            message="没有找到该 Claude Code 会话。",
        )

    @staticmethod
    def _compact(value: str, limit: int = 500) -> str:
        normalized = " ".join(value.split())
        return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"
