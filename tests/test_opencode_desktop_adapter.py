from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_hub.adapter_factory import AgentAdapterFactory
from agent_hub.agents.models import AgentProfileInput
from agent_hub.sessions.adapters.opencode_desktop import OpenCodeDesktopSessionAdapter
from agent_hub.sessions.models import SessionStatus
from tests.test_session_adapter_contract import assert_session_adapter_contract


class OpenCodeDesktopSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "opencode.db"
        self.commands: list[list[str]] = []
        self._create_database()
        profile = AgentAdapterFactory().create_profile(
            AgentProfileInput(
                id="opencode-desktop-test",
                name="OpenCode Desktop Test",
                agent_type="opencode",
                adapter_kind="opencode_desktop",
                data_path=str(self.database),
                executable=sys.executable,
            )
        )
        self.adapter = OpenCodeDesktopSessionAdapter(
            profile,
            database=self.database,
            executable=sys.executable,
            resume_launcher=lambda command, env: self.commands.append(command) or True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _create_database(self) -> None:
        with closing(sqlite3.connect(self.database)) as connection:
            connection.executescript(
                """
                CREATE TABLE session (
                    id TEXT PRIMARY KEY, title TEXT, directory TEXT, parent_id TEXT,
                    time_updated INTEGER NOT NULL, time_archived INTEGER
                );
                CREATE TABLE message (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    time_created INTEGER NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE part (
                    id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL,
                    time_created INTEGER NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE todo (
                    session_id TEXT NOT NULL, content TEXT NOT NULL,
                    status TEXT NOT NULL, position INTEGER NOT NULL
                );
                """
            )
            for index, native_id in enumerate(("running", "interrupted", "idle", "archived")):
                connection.execute(
                    "INSERT INTO session VALUES (?, ?, ?, NULL, ?, ?)",
                    (
                        native_id,
                        f"{native_id} session",
                        str(Path(self.temporary.name) / native_id),
                        1_784_000_000_000 + index,
                        1_784_000_000_999 if native_id == "archived" else None,
                    ),
                )
                data = {
                    "role": "assistant",
                    "time": {"created": 1_784_000_000_000},
                }
                if native_id != "running":
                    data["time"]["completed"] = 1_784_000_001_000
                    data["finish"] = "stop"
                if native_id == "interrupted":
                    data["error"] = {"name": "MessageAbortedError"}
                message_id = f"message-{native_id}"
                connection.execute(
                    "INSERT INTO message VALUES (?, ?, ?, ?)",
                    (message_id, native_id, 1_784_000_000_000 + index, json.dumps(data)),
                )
                connection.execute(
                    "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
                    (
                        f"part-{native_id}",
                        message_id,
                        native_id,
                        1_784_000_000_000 + index,
                        json.dumps({"type": "text", "text": f"activity {native_id}"}),
                    ),
                )
            connection.execute(
                "INSERT INTO todo VALUES ('running', 'implement adapter', 'in_progress', 0)"
            )
            connection.commit()

    async def test_maps_desktop_state_todo_and_stable_ids(self) -> None:
        first = await self.adapter.list_sessions()
        second = await self.adapter.list_sessions()
        statuses = {item.native_session_id: item.status for item in first}

        self.assertEqual(statuses["running"], SessionStatus.EXECUTING)
        self.assertEqual(statuses["interrupted"], SessionStatus.INTERRUPTED)
        self.assertEqual(statuses["idle"], SessionStatus.UNKNOWN)
        self.assertEqual(statuses["archived"], SessionStatus.CLOSED)
        self.assertEqual(
            {item.id for item in first},
            {item.id for item in second},
        )
        running = next(item for item in first if item.native_session_id == "running")
        self.assertEqual(running.current_step, "implement adapter")
        self.assertEqual(running.last_activity, "activity running")

    async def test_probe_contract_and_resume_use_native_id(self) -> None:
        result = await self.adapter.probe()
        sessions = await self.adapter.list_sessions()
        await assert_session_adapter_contract(self, self.adapter)
        opened = await self.adapter.open_session(sessions[0].id)

        self.assertTrue(result.ok)
        self.assertTrue(opened.ok)
        self.assertIn(sessions[0].native_session_id, self.commands[0])
        self.assertIn("--session", self.commands[0])


if __name__ == "__main__":
    unittest.main()
