from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_hub.agents.models import AgentProfile, SessionIntegrationCapabilities
from agent_hub.sessions.adapters.codex import CodexSessionAdapter
from agent_hub.sessions.models import SessionStatus
from tests.test_session_adapter_contract import assert_session_adapter_contract


def profile() -> AgentProfile:
    return AgentProfile(
        id="codex",
        name="Codex",
        adapter_type="Codex local state + Desktop deep link",
        enabled=True,
        connected=False,
        endpoint="local://codex",
        capabilities=SessionIntegrationCapabilities(
            session_discovery=True,
            status_detection=True,
            plan_reading=True,
            exact_resume=True,
            event_stream=False,
            resume_launch=True,
        ),
        status_source="Codex local state polling",
    )


class CodexSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temporary.name)
        self.opened: list[str] = []
        self._create_database()
        self._write_rollouts()
        self.adapter = CodexSessionAdapter(
            profile(),
            codex_home=self.codex_home,
            opener=lambda target: self.opened.append(target),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_database(self) -> None:
        with closing(sqlite3.connect(self.codex_home / "state_5.sqlite")) as connection:
            connection.execute(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    title TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    first_user_message TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    recency_at_ms INTEGER NOT NULL,
                    archived INTEGER NOT NULL
                )
                """
            )
            for index, native_id in enumerate(("running", "waiting", "closed", "interrupted")):
                rollout = self.codex_home / f"{native_id}.jsonl"
                connection.execute(
                    "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        native_id,
                        str(rollout),
                        rf"D:\Projects\{native_id}",
                        f"{native_id} task",
                        "",
                        "",
                        1_784_000_000 + index,
                        1_784_000_000_000 + index,
                        1_784_000_000_000 + index,
                    ),
                )
            connection.commit()

    def _write_rollouts(self) -> None:
        running = [
            self._event("task_started", turn_id="turn-running"),
            {
                "timestamp": "2026-07-26T10:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "update_plan",
                    "call_id": "plan-1",
                    "arguments": json.dumps(
                        {
                            "plan": [
                                {"step": "读取状态", "status": "completed"},
                                {"step": "验证状态", "status": "in_progress"},
                            ]
                        },
                        ensure_ascii=False,
                    ),
                },
            },
            {
                "timestamp": "2026-07-26T10:00:02Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "正在验证 Codex 状态"},
            },
        ]
        waiting = [
            self._event("task_started", turn_id="turn-waiting"),
            {
                "timestamp": "2026-07-26T10:01:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "request_user_input",
                    "call_id": "input-1",
                    "arguments": "{}",
                },
            },
        ]
        closed = [
            self._event("task_started", turn_id="turn-closed"),
            self._event(
                "task_complete",
                turn_id="turn-closed",
                last_agent_message="任务已经完成",
            ),
        ]
        interrupted = [
            self._event("task_started", turn_id="turn-interrupted"),
            self._event("turn_aborted", turn_id="turn-interrupted", reason="interrupted"),
        ]
        for native_id, events in (
            ("running", running),
            ("waiting", waiting),
            ("closed", closed),
            ("interrupted", interrupted),
        ):
            content = "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n"
            (self.codex_home / f"{native_id}.jsonl").write_text(content, encoding="utf-8")

    @staticmethod
    def _event(event_type: str, **payload: object) -> dict[str, object]:
        return {
            "timestamp": "2026-07-26T10:00:00Z",
            "type": "event_msg",
            "payload": {"type": event_type, **payload},
        }

    async def test_maps_running_waiting_closed_and_plan(self) -> None:
        sessions = {item.native_session_id: item for item in await self.adapter.list_sessions()}

        self.assertEqual(sessions["running"].status, SessionStatus.EXECUTING)
        self.assertEqual(sessions["waiting"].status, SessionStatus.WAITING_INPUT)
        self.assertEqual(sessions["closed"].status, SessionStatus.CLOSED)
        self.assertEqual(sessions["interrupted"].status, SessionStatus.INTERRUPTED)
        self.assertEqual([item.status for item in sessions["running"].plan_items], ["done", "current"])
        self.assertEqual(sessions["running"].last_activity, "正在验证 Codex 状态")

    async def test_request_user_input_output_returns_to_executing(self) -> None:
        path = self.codex_home / "waiting.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": "2026-07-26T10:01:02Z",
                        "type": "response_item",
                        "payload": {"type": "function_call_output", "call_id": "input-1", "output": "ok"},
                    }
                )
                + "\n"
            )

        sessions = {item.native_session_id: item for item in await self.adapter.list_sessions()}

        self.assertEqual(sessions["waiting"].status, SessionStatus.EXECUTING)

    async def test_deep_link_uses_native_thread_id(self) -> None:
        result = await self.adapter.open_session("codex:running")

        self.assertTrue(result.ok)
        self.assertEqual(self.opened, ["codex://threads/running"])
        self.assertEqual(result.resume_target, "codex://threads/running")

    async def test_missing_rollout_is_unknown_without_hiding_session(self) -> None:
        (self.codex_home / "waiting.jsonl").unlink()

        sessions = {item.native_session_id: item for item in await self.adapter.list_sessions()}

        self.assertEqual(len(sessions), 4)
        self.assertEqual(sessions["waiting"].status, SessionStatus.UNKNOWN)
        self.assertEqual(sessions["waiting"].confidence, "low")

    async def test_probe_and_shared_contract(self) -> None:
        probe = await self.adapter.probe()

        self.assertTrue(probe.ok)
        self.assertTrue(self.adapter.profile.connected)
        await assert_session_adapter_contract(self, self.adapter)


if __name__ == "__main__":
    unittest.main()
