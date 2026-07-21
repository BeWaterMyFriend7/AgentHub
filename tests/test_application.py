from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from agent_hub.bootstrap import create_demo_runtime
from agent_hub.main import create_app


class ApplicationCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(create_demo_runtime()))

    def test_agent_routes_include_new_name_and_legacy_alias(self) -> None:
        paths = {route.path for route in self.client.app.routes}

        self.assertIn("/api/agents", paths)
        self.assertIn("/api/tools", paths)
        self.assertIn("/api/agents/{agent_id}/probe", paths)
        self.assertIn("/api/tools/{tool_id}/probe", paths)

    def test_new_api_uses_agent_vocabulary(self) -> None:
        sessions = self.client.get("/api/sessions")
        probe = self.client.post("/api/agents/codex/probe")

        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(probe.status_code, 200)
        self.assertIn("agent_id", sessions.json()[0])
        self.assertIn("agent_name", sessions.json()[0])
        self.assertNotIn("tool_id", sessions.json()[0])
        self.assertEqual(probe.json()["agent_id"], "codex")
        self.assertNotIn("tool_id", probe.json())

    def test_legacy_probe_alias_and_unknown_session_response(self) -> None:
        legacy_probe = self.client.post("/api/tools/codex/probe")
        missing_session = self.client.post("/api/sessions/missing/open")

        self.assertEqual(legacy_probe.status_code, 200)
        self.assertEqual(legacy_probe.json()["tool_id"], "codex")
        self.assertNotIn("agent_id", legacy_probe.json())
        self.assertEqual(missing_session.status_code, 404)
        self.assertTrue(missing_session.json()["detail"])


if __name__ == "__main__":
    unittest.main()
