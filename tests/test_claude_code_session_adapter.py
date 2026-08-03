from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_hub.agents.models import AgentProfile, SessionIntegrationCapabilities
from agent_hub.sessions.adapters.claude_code import ClaudeCodeSessionAdapter
from agent_hub.sessions.models import SessionStatus


def profile() -> AgentProfile:
    return AgentProfile(
        id="claude-code",
        name="Claude Code",
        agent_type="claude_code",
        adapter_kind="claude_code",
        adapter_type="Claude Code project JSONL + CLI resume",
        enabled=True,
        connected=False,
        endpoint="local://claude-code",
        capabilities=SessionIntegrationCapabilities(
            session_discovery=True,
            status_detection=True,
            plan_reading=True,
            exact_resume=True,
            event_stream=False,
            resume_launch=True,
        ),
        status_source="Claude Code project JSONL polling",
    )


class ClaudeCodeSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.projects = Path(self.temporary.name) / "projects"
        project = self.projects / "D--Projects--demo"
        project.mkdir(parents=True)
        events = [
            {
                "type": "user",
                "sessionId": "session-1",
                "cwd": r"D:\Projects\demo",
                "timestamp": "2026-08-03T10:00:00Z",
                "message": {"role": "user", "content": "实现 Provider 切换"},
            },
            {
                "type": "assistant",
                "sessionId": "session-1",
                "cwd": r"D:\Projects\demo",
                "timestamp": "2026-08-03T10:00:02Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "已经完成第一步"}],
                },
            },
        ]
        (project / "session-1.jsonl").write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
            encoding="utf-8",
        )
        self.launched: list[list[str]] = []
        self.adapter = ClaudeCodeSessionAdapter(
            profile(),
            projects_dir=self.projects,
            executable="claude",
            launcher=lambda args, cwd: self.launched.append(args),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    async def test_lists_native_session_and_resumes_by_id(self) -> None:
        sessions = await self.adapter.list_sessions()

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].native_session_id, "session-1")
        self.assertEqual(sessions[0].title, "实现 Provider 切换")
        self.assertEqual(sessions[0].last_activity, "已经完成第一步")
        self.assertEqual(sessions[0].status, SessionStatus.CLOSED)

        result = await self.adapter.open_session("claude-code:session-1")

        self.assertTrue(result.ok)
        self.assertEqual(self.launched, [["claude", "--resume", "session-1"]])


if __name__ == "__main__":
    unittest.main()
