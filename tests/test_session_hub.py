from __future__ import annotations

import unittest

from agent_hub.bootstrap import create_demo_runtime


class SessionHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_runtime_preserves_session_summary(self) -> None:
        runtime = create_demo_runtime()

        summary = await runtime.sessions.summary()

        self.assertEqual(summary.total, 6)
        self.assertEqual(summary.executing, 1)
        self.assertEqual(summary.waiting, 2)
        self.assertEqual(summary.awaiting_review, 1)
        self.assertEqual(summary.interrupted, 1)
        self.assertEqual(summary.closed, 1)
        self.assertEqual(summary.attention, 4)

    async def test_open_session_uses_native_session_target_and_records_event(self) -> None:
        runtime = create_demo_runtime()
        before = len(runtime.events.records)

        result = await runtime.sessions.open_session("codex-agent-hub")

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "resume_session")
        self.assertEqual(
            result.resume_target,
            "codex://session/thread_demo_agent_hub",
        )
        self.assertEqual(len(runtime.events.records), before + 1)
        self.assertEqual(runtime.events.records[0].session_id, "codex-agent-hub")

    async def test_unknown_agent_probe_is_a_recorded_failure(self) -> None:
        runtime = create_demo_runtime()
        before = len(runtime.events.records)

        result = await runtime.sessions.probe_agent("missing-agent")

        self.assertFalse(result.ok)
        self.assertEqual(result.agent_id, "missing-agent")
        self.assertEqual(len(runtime.events.records), before + 1)
        self.assertEqual(runtime.events.records[0].agent_id, "missing-agent")


if __name__ == "__main__":
    unittest.main()
