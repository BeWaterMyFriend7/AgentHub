from __future__ import annotations

import asyncio
import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path

from fastapi.testclient import TestClient

from agent_hub.agents.config import AgentProfileStore
from agent_hub.bootstrap import create_configured_runtime, create_demo_runtime
from agent_hub import main as main_module
from agent_hub.main import create_app
from agent_hub.providers.models import ProviderInput, ProviderProtocol


class ApplicationCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(create_demo_runtime()))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    def test_agent_routes_include_new_name_and_legacy_alias(self) -> None:
        paths = {route.path for route in self.client.app.routes}

        self.assertIn("/api/agents", paths)
        self.assertIn("/api/tools", paths)
        self.assertIn("/api/agents/{agent_id}/probe", paths)
        self.assertIn("/api/tools/{tool_id}/probe", paths)

    def test_imported_asgi_runtime_does_not_open_an_http_client(self) -> None:
        self.assertIsNotNone(main_module.runtime.gateway)
        self.assertFalse(main_module.runtime.gateway.client_active)

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

        dashboard = self.client.get("/api/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()["summary"]["total"], 6)
        self.assertEqual(len(dashboard.json()["sessions"]), 6)

    def test_legacy_probe_alias_and_unknown_session_response(self) -> None:
        legacy_probe = self.client.post("/api/tools/codex/probe")
        missing_session = self.client.post("/api/sessions/missing/open")

        self.assertEqual(legacy_probe.status_code, 200)
        self.assertEqual(legacy_probe.json()["tool_id"], "codex")
        self.assertNotIn("agent_id", legacy_probe.json())
        self.assertEqual(missing_session.status_code, 404)
        self.assertTrue(missing_session.json()["detail"])

    def test_configured_runtime_supports_profile_crud(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "agents.json"
            AgentProfileStore(config_path).save([])
            with TestClient(create_app(create_configured_runtime(config_path))) as client:
                definitions = client.get("/api/agent-types")
                created = client.post(
                    "/api/agents",
                    json={
                        "id": "codex-local",
                        "name": "Codex Local",
                        "agent_type": "codex",
                        "adapter_kind": "codex_desktop",
                        "enabled": False,
                        "data_path": str(Path(temporary) / ".codex"),
                    },
                )
                updated = client.put("/api/agents/codex-local", json={"enabled": True})
                deleted = client.delete("/api/agents/codex-local")

                self.assertEqual(definitions.status_code, 200)
                self.assertEqual({item["kind"] for item in definitions.json()}, {
                    "claude_code", "codex_desktop", "opencode_desktop", "opencode_server"
                })
                self.assertEqual(created.status_code, 201)
                self.assertFalse(created.json()["enabled"])
                self.assertTrue(updated.json()["enabled"])
                self.assertEqual(deleted.status_code, 204)
                self.assertEqual(client.get("/api/agents").json(), [])

    def test_environment_config_keeps_all_agenthub_state_in_the_injected_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "agents.json"
            AgentProfileStore(config_path).save([])
            with patch.dict("os.environ", {"AGENT_HUB_CONFIG": str(config_path)}):
                runtime = create_configured_runtime()

            try:
                runtime.providers.save_provider(
                    ProviderInput(
                        id="local-test",
                        name="Local Test",
                        protocol=ProviderProtocol.OPENAI_RESPONSES,
                        base_url="https://example.test/v1",
                        models=["model-a"],
                    )
                )
                self.assertEqual(
                    [provider.id for provider in runtime.providers.list_providers()],
                    ["local-test"],
                )
                self.assertTrue((Path(temporary) / "providers.json").is_file())
                self.assertFalse(runtime.client_integrations.allow_user_config_writes)
            finally:
                asyncio.run(runtime.aclose())


if __name__ == "__main__":
    unittest.main()
