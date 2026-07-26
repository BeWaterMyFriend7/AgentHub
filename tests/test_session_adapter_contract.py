from __future__ import annotations

import unittest

from agent_hub.demo.seed import profiles, sessions
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.adapters.mock import MockSessionAdapter


async def assert_session_adapter_contract(
    test_case: unittest.TestCase,
    adapter: SessionAdapter,
) -> None:
    first = await adapter.list_sessions()
    second = await adapter.list_sessions()

    first_ids = [item.id for item in first]
    test_case.assertEqual(first_ids, [item.id for item in second])
    test_case.assertEqual(len(first_ids), len(set(first_ids)))
    test_case.assertTrue(all(item.native_session_id for item in first))
    test_case.assertTrue(all(item.status_reason for item in first))
    test_case.assertTrue(
        all(plan.id and plan.title and plan.status for item in first for plan in item.plan_items)
    )

    probe = await adapter.probe()
    test_case.assertTrue(probe.ok)

    if first and (adapter.profile.capabilities.exact_resume or adapter.profile.capabilities.resume_launch):
        result = await adapter.open_session(first[0].id)
        test_case.assertTrue(result.ok)
        test_case.assertIn(first[0].native_session_id, result.resume_target or "")


class SessionAdapterContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_mock_adapters_share_the_contract(self) -> None:
        session_map = sessions()
        for item in profiles():
            with self.subTest(adapter=item.id):
                await assert_session_adapter_contract(
                    self,
                    MockSessionAdapter(item, session_map.get(item.id, [])),
                )


if __name__ == "__main__":
    unittest.main()
