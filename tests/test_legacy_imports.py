from __future__ import annotations

import unittest

from agent_hub.adapters import MockAgentAdapter
from agent_hub.repository import Repository
from agent_hub.seed import sessions, tools
from agent_hub.service import SessionHubService


class LegacyImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_previous_import_paths_remain_usable_during_migration(self) -> None:
        profiles = tools()
        session_map = sessions()
        repository = Repository(profiles)
        adapters = {
            profile.id: MockAgentAdapter(profile, session_map.get(profile.id, []))
            for profile in profiles
        }

        service = SessionHubService(repository, adapters)

        self.assertEqual((await service.summary()).total, 6)
        self.assertEqual(len(service.list_tools()), 3)


if __name__ == "__main__":
    unittest.main()
