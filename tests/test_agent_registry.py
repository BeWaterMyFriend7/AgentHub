from __future__ import annotations

import unittest

from agent_hub.agents import AgentRegistry
from agent_hub.demo.seed import profiles as seed_profiles
from agent_hub.sessions.events import SessionEventLog
from agent_hub.sessions.hub import SessionHub


class AgentRegistryTests(unittest.TestCase):
    def test_duplicate_profile_ids_are_rejected(self) -> None:
        profile = seed_profiles()[0]

        with self.assertRaisesRegex(ValueError, "ID 必须唯一"):
            AgentRegistry([profile, profile.model_copy(deep=True)])


class SessionAdapterCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_without_session_adapter_remains_visible(self) -> None:
        agents = AgentRegistry(seed_profiles())
        sessions = SessionHub(agents, {}, SessionEventLog())

        result = await sessions.probe_agent("codex")

        self.assertEqual(len(agents.list_profiles()), 3)
        self.assertFalse(result.ok)
        self.assertIn("尚未配置 Session Adapter", result.message)


if __name__ == "__main__":
    unittest.main()
