from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import webbrowser
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.models import AgentSession, OpenSessionResult, PlanItem, SessionStatus


OpenTarget = Callable[[str], bool | None]


@dataclass(frozen=True)
class _RolloutSnapshot:
    status: SessionStatus
    reason: str
    confidence: str
    plan_items: list[PlanItem]
    last_activity: str


def _default_open_target(target: str) -> bool:
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return True
    return webbrowser.open(target, new=0)


class CodexSessionAdapter(SessionAdapter):
    """Read Codex Desktop thread metadata and native rollout lifecycle events."""

    def __init__(
        self,
        profile: AgentProfile,
        *,
        codex_home: str | Path | None = None,
        state_db: str | Path | None = None,
        opener: OpenTarget | None = None,
        session_limit: int = 100,
        tail_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        super().__init__(profile)
        configured_home = codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        self._codex_home = Path(configured_home).expanduser()
        self._state_db = (
            Path(state_db).expanduser() if state_db else self._latest_state_db(self._codex_home)
        )
        self._opener = opener or _default_open_target
        self._session_limit = session_limit
        self._tail_bytes = tail_bytes

    async def list_sessions(self) -> list[AgentSession]:
        return await asyncio.to_thread(self._list_sessions_sync)

    async def probe(self) -> ProbeResult:
        checks: list[str] = []
        failures: list[str] = []
        if not self.profile.enabled:
            failures.append("Agent Profile 已被禁用。")
        if not self._state_db.is_file():
            failures.append(f"未找到 Codex 状态数据库：{self._state_db}")

        sessions: list[AgentSession] = []
        if not failures:
            try:
                sessions = await self.list_sessions()
            except (OSError, sqlite3.Error, ValueError) as error:
                failures.append(f"Codex 本地状态读取失败：{error}")

        if sessions:
            checks.append(f"成功列出 {len(sessions)} 个 Codex 任务并保留原生 Thread ID。")
            native_statuses = {item.status for item in sessions}
            if SessionStatus.EXECUTING in native_statuses:
                checks.append("检测到 task_started 且尚未结束的运行中任务。")
            if SessionStatus.CLOSED in native_statuses:
                checks.append("检测到带 task_complete 证据的已结束任务。")
        elif not failures:
            failures.append("Codex 状态数据库中没有可读取的任务。")

        if len(sessions) < 3 and not failures:
            failures.append(f"仅发现 {len(sessions)} 个 Codex 任务，未达到三个任务的验收门槛。")
        if self.profile.capabilities.exact_resume:
            checks.append("精确定位使用 Codex Desktop codex://threads/<threadId> 深链。")

        self.profile.connected = not failures
        self.profile.last_probe_message = "；".join(failures) if failures else "接入能力校验通过"
        return ProbeResult(
            ok=not failures,
            agent_id=self.profile.id,
            title="接入探测通过" if not failures else "接入探测失败",
            message=(
                f"{self.profile.name} 已验证本地任务发现、生命周期状态读取和精确定位入口。"
                if not failures
                else f"{self.profile.name} 尚未达到本地状态接入标准。"
            ),
            checks=checks,
            failures=failures,
        )

    async def open_session(self, session_id: str) -> OpenSessionResult:
        prefix = f"{self.profile.id}:"
        native_id = session_id.removeprefix(prefix) if session_id.startswith(prefix) else ""
        if not native_id or not await asyncio.to_thread(self._thread_exists, native_id):
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="none",
                message="没有找到该 Codex 任务。",
            )

        target = f"codex://threads/{native_id}"
        try:
            opened = await asyncio.to_thread(self._opener, target)
        except OSError as error:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="open_thread",
                message=f"Codex 任务定位失败：{error}",
                resume_target=target,
            )
        if opened is False:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="open_thread",
                message="系统没有接受 Codex 任务深链。",
                resume_target=target,
            )
        return OpenSessionResult(
            ok=True,
            session_id=session_id,
            agent_id=self.profile.id,
            action="open_thread",
            message="已按原生 Thread ID 在 Codex Desktop 中定位任务。",
            resume_target=target,
        )

    def _list_sessions_sync(self) -> list[AgentSession]:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT id, rollout_path, cwd, title, preview, first_user_message,
                       updated_at, updated_at_ms
                FROM threads
                WHERE archived = 0
                ORDER BY recency_at_ms DESC, updated_at_ms DESC, updated_at DESC
                LIMIT ?
                """,
                (self._session_limit,),
            ).fetchall()

        sessions: list[AgentSession] = []
        for row in rows:
            native_id = str(row["id"] or "").strip()
            if not native_id:
                continue
            rollout_path = self._native_path(str(row["rollout_path"] or ""))
            snapshot = self._read_rollout(rollout_path)
            directory = self._display_path(str(row["cwd"] or "")) or None
            updated_at = self._updated_at(row)
            title = self._compact(
                str(row["title"] or row["preview"] or row["first_user_message"] or native_id),
                limit=240,
            )
            current = next((item.title for item in snapshot.plan_items if item.status == "current"), "")
            pending = next((item.title for item in snapshot.plan_items if item.status == "pending"), "")
            sessions.append(
                AgentSession(
                    id=f"{self.profile.id}:{native_id}",
                    native_session_id=native_id,
                    agent_id=self.profile.id,
                    agent_name=self.profile.name,
                    title=title,
                    project_name=Path(directory).name if directory else "Codex",
                    working_directory=directory,
                    status=snapshot.status,
                    status_reason=snapshot.reason,
                    current_goal="",
                    current_step=current or pending,
                    plan_items=snapshot.plan_items,
                    last_activity=snapshot.last_activity,
                    updated_at=updated_at,
                    status_source=f"Codex {self._state_db.name} + rollout JSONL",
                    confidence=snapshot.confidence,
                    resumable=self.profile.capabilities.exact_resume,
                )
            )
        return sessions

    def _thread_exists(self, native_id: str) -> bool:
        with closing(self._connect()) as connection:
            return connection.execute("SELECT 1 FROM threads WHERE id = ?", (native_id,)).fetchone() is not None

    def _connect(self) -> sqlite3.Connection:
        uri = f"{self._state_db.resolve().as_uri()}?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=5.0)

    def _read_rollout(self, path: Path) -> _RolloutSnapshot:
        if not path.is_file():
            return _RolloutSnapshot(
                status=SessionStatus.UNKNOWN,
                reason="未找到 Codex rollout 文件，无法判断任务状态。",
                confidence="low",
                plan_items=[],
                last_activity="",
            )

        lifecycle: tuple[str, dict[str, Any], str] | None = None
        pending_input_calls: set[str] = set()
        plan_items: list[PlanItem] = []
        last_activity = ""
        for raw_line in self._tail_lines(path):
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            payload = event.get("payload") or {}
            payload_type = payload.get("type")
            timestamp = str(event.get("timestamp") or "")

            if payload_type == "task_started":
                lifecycle = ("started", payload, timestamp)
                pending_input_calls.clear()
                plan_items = []
                last_activity = ""
                continue
            if payload_type == "task_complete":
                lifecycle = ("complete", payload, timestamp)
                pending_input_calls.clear()
                message = payload.get("last_agent_message")
                if isinstance(message, str) and message.strip():
                    last_activity = self._compact(message)
                continue
            if payload_type == "turn_aborted":
                lifecycle = ("aborted", payload, timestamp)
                pending_input_calls.clear()
                continue

            call_id = payload.get("call_id")
            if payload_type in {"function_call_output", "custom_tool_call_output"} and call_id:
                pending_input_calls.discard(str(call_id))
            if payload_type in {"function_call", "custom_tool_call"}:
                if payload.get("name") == "request_user_input" and call_id and lifecycle:
                    pending_input_calls.add(str(call_id))
                if payload.get("name") == "update_plan":
                    parsed_plan = self._parse_plan(payload)
                    if parsed_plan:
                        plan_items = parsed_plan

            activity = self._activity_text(payload)
            if activity:
                last_activity = self._compact(activity)

        if lifecycle is None:
            return _RolloutSnapshot(
                status=SessionStatus.UNKNOWN,
                reason="rollout 尾部没有完整生命周期事件，未推断任务状态。",
                confidence="low",
                plan_items=plan_items,
                last_activity=last_activity,
            )

        lifecycle_type, payload, timestamp = lifecycle
        turn_id = payload.get("turn_id") or "unknown"
        evidence = f"turn={turn_id}" + (f"，event={timestamp}" if timestamp else "")
        if lifecycle_type == "complete":
            status = SessionStatus.CLOSED
            reason = f"Codex rollout 记录 task_complete（{evidence}）。"
        elif lifecycle_type == "aborted":
            status = SessionStatus.INTERRUPTED
            reason = f"Codex rollout 记录 turn_aborted（{evidence}）。"
        elif pending_input_calls:
            status = SessionStatus.WAITING_INPUT
            reason = f"当前轮次存在尚未返回的 request_user_input（{evidence}）。"
        else:
            status = SessionStatus.EXECUTING
            reason = f"Codex rollout 记录 task_started，尚无完成或中断事件（{evidence}）。"
        return _RolloutSnapshot(
            status=status,
            reason=reason,
            confidence="medium" if status == SessionStatus.EXECUTING else "high",
            plan_items=plan_items,
            last_activity=last_activity,
        )

    def _tail_lines(self, path: Path) -> list[str]:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            start = max(0, size - self._tail_bytes)
            handle.seek(start)
            data = handle.read()
        if start:
            newline = data.find(b"\n")
            data = data[newline + 1 :] if newline >= 0 else b""
        return data.decode("utf-8", errors="replace").splitlines()

    @staticmethod
    def _parse_plan(payload: dict[str, Any]) -> list[PlanItem]:
        raw = payload.get("arguments", payload.get("input", {}))
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
        items = raw.get("plan", []) if isinstance(raw, dict) else []
        status_map = {"completed": "done", "in_progress": "current", "pending": "pending"}
        result: list[PlanItem] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            title = item.get("step")
            status = status_map.get(item.get("status"))
            if title and status:
                result.append(PlanItem(id=str(index + 1), title=str(title), status=status))
        return result

    @staticmethod
    def _activity_text(payload: dict[str, Any]) -> str:
        if payload.get("type") == "agent_message":
            message = payload.get("message")
            return message.strip() if isinstance(message, str) else ""
        if payload.get("type") == "message" and payload.get("role") == "assistant":
            parts = payload.get("content", [])
            texts = [
                str(part.get("text", "")).strip()
                for part in parts
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}
            ]
            return "\n".join(item for item in texts if item)
        return ""

    @staticmethod
    def _compact(value: str, limit: int = 500) -> str:
        normalized = " ".join(value.split())
        return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"

    @staticmethod
    def _native_path(value: str) -> Path:
        return Path(value)

    @staticmethod
    def _display_path(value: str) -> str:
        return value[4:] if value.startswith("\\\\?\\") else value

    @staticmethod
    def _latest_state_db(codex_home: Path) -> Path:
        candidates: list[tuple[int, Path]] = []
        for path in codex_home.glob("state_*.sqlite"):
            try:
                version = int(path.stem.removeprefix("state_"))
            except ValueError:
                continue
            candidates.append((version, path))
        return max(candidates, default=(5, codex_home / "state_5.sqlite"))[1]

    @staticmethod
    def _updated_at(row: sqlite3.Row) -> datetime:
        updated_ms = row["updated_at_ms"]
        if isinstance(updated_ms, int) and updated_ms > 0:
            return datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc)
        return datetime.fromtimestamp(int(row["updated_at"] or 0), tz=timezone.utc)
