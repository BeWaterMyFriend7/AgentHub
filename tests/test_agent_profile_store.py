from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from agent_hub.adapter_factory import AgentAdapterFactory
from agent_hub.agents.config import AgentProfileStore
from agent_hub.agents.models import AgentProfileInput


class AgentProfileStoreTests(unittest.TestCase):
    def test_profiles_persist_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "agents.json"
            store = AgentProfileStore(path)
            factory = AgentAdapterFactory()
            os.environ["TEST_OPENCODE_PASSWORD"] = "must-not-be-persisted"
            self.addCleanup(os.environ.pop, "TEST_OPENCODE_PASSWORD", None)
            profile = factory.create_profile(
                AgentProfileInput(
                    id="server-one",
                    name="OpenCode Server One",
                    agent_type="opencode",
                    adapter_kind="opencode_server",
                    endpoint="http://127.0.0.1:4096",
                    username="opencode",
                    secret_env="TEST_OPENCODE_PASSWORD",
                )
            )

            store.save([profile])

            raw = path.read_text(encoding="utf-8")
            loaded = store.list_profiles()
            self.assertNotIn("must-not-be-persisted", raw)
            self.assertEqual(loaded[0].secret_env, "TEST_OPENCODE_PASSWORD")
            self.assertEqual(json.loads(raw)["profiles"][0]["id"], "server-one")

    def test_same_product_can_have_distinct_desktop_and_server_profiles(self) -> None:
        factory = AgentAdapterFactory()
        desktop = factory.create_profile(
            AgentProfileInput(
                id="desktop",
                name="OpenCode Desktop",
                agent_type="opencode",
                adapter_kind="opencode_desktop",
            )
        )
        server = factory.create_profile(
            AgentProfileInput(
                id="server",
                name="OpenCode Server",
                agent_type="opencode",
                adapter_kind="opencode_server",
            )
        )

        self.assertEqual(desktop.agent_type, server.agent_type)
        self.assertNotEqual(desktop.id, server.id)
        self.assertNotEqual(desktop.adapter_kind, server.adapter_kind)

    def test_invalid_profile_does_not_hide_valid_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "agents.json"
            path.write_text(
                json.dumps(
                    {
                        "profiles": [
                            {"id": "broken", "name": "Broken"},
                            AgentAdapterFactory().create_profile(
                                AgentProfileInput(
                                    id="valid",
                                    name="Valid Codex",
                                    agent_type="codex",
                                    adapter_kind="codex_desktop",
                                    enabled=False,
                                )
                            ).model_dump(mode="json"),
                        ]
                    }
                ),
                encoding="utf-8",
            )

            profiles = AgentProfileStore(path).list_profiles()

            self.assertEqual(len(profiles), 2)
            self.assertEqual(profiles[0].adapter_kind, "invalid")
            self.assertIn("配置校验失败", profiles[0].last_probe_message)
            self.assertEqual(profiles[1].id, "valid")


if __name__ == "__main__":
    unittest.main()
