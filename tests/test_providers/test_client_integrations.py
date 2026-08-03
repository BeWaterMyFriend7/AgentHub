from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tomli

from agent_hub.providers.clients import (
    ClientConfigChanged,
    ClientIntegrationManager,
    UnsafeClientConfigPath,
)
from agent_hub.providers.models import ClientKind, ResolvedRoute


class _Provider:
    id = "gateway"


class ClientIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.codex_config = self.root / ".codex" / "config.toml"
        self.claude_settings = self.root / ".claude" / "settings.json"
        self.codex_config.parent.mkdir(parents=True)
        self.claude_settings.parent.mkdir(parents=True)
        self.codex_original = b'model = "old-model"\napproval_policy = "never"\n'
        self.claude_original = json.dumps(
            {"theme": "dark", "env": {"KEEP_ME": "yes"}}, indent=2
        ).encode("utf-8") + b"\n"
        self.codex_config.write_bytes(self.codex_original)
        self.claude_settings.write_bytes(self.claude_original)
        self.manager = ClientIntegrationManager(
            data_dir=self.root / ".agenthub",
            codex_config_path=self.codex_config,
            claude_settings_path=self.claude_settings,
            proxy_base_url="http://127.0.0.1:17860",
            allow_user_config_writes=True,
        )
        self.route = ResolvedRoute(provider=_Provider(), model="model-a", source="default")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_codex_takeover_preserves_unrelated_config_and_restores_exact_bytes(self) -> None:
        status = self.manager.enable(ClientKind.CODEX, self.route)
        active = tomli.loads(self.codex_config.read_text(encoding="utf-8"))

        self.assertTrue(status.active)
        self.assertEqual(active["approval_policy"], "never")
        self.assertEqual(active["model_provider"], "openai")
        self.assertEqual(active["openai_base_url"], "http://127.0.0.1:17860/v1")
        self.assertEqual(active["model"], "model-a")

        restored = self.manager.disable(ClientKind.CODEX)

        self.assertFalse(restored.active)
        self.assertEqual(self.codex_config.read_bytes(), self.codex_original)

    def test_claude_takeover_uses_gateway_environment_and_restores_exact_bytes(self) -> None:
        status = self.manager.enable(ClientKind.CLAUDE_CODE, self.route)
        active = json.loads(self.claude_settings.read_text(encoding="utf-8"))

        self.assertTrue(status.active)
        self.assertEqual(active["theme"], "dark")
        self.assertEqual(active["env"]["KEEP_ME"], "yes")
        self.assertEqual(active["env"]["ANTHROPIC_BASE_URL"], "http://127.0.0.1:17860")
        self.assertEqual(active["env"]["ANTHROPIC_AUTH_TOKEN"], "agenthub-local")
        self.assertEqual(active["env"]["ANTHROPIC_MODEL"], "model-a")

        self.manager.disable(ClientKind.CLAUDE_CODE)

        self.assertEqual(self.claude_settings.read_bytes(), self.claude_original)

    def test_real_home_write_requires_explicit_runtime_authorization(self) -> None:
        for protected_path in (
            Path.home() / ".codex" / "config.toml",
            Path.home() / ".codex" / "alternate-config.toml",
        ):
            manager = ClientIntegrationManager(
                data_dir=self.root / ".agenthub-guard",
                codex_config_path=protected_path,
                claude_settings_path=self.claude_settings,
                proxy_base_url="http://127.0.0.1:17860",
                allow_user_config_writes=False,
            )

            with self.assertRaises(UnsafeClientConfigPath):
                manager.enable(ClientKind.CODEX, self.route)

    def test_external_edit_is_never_overwritten_during_restore(self) -> None:
        self.manager.enable(ClientKind.CODEX, self.route)
        self.codex_config.write_text(
            self.codex_config.read_text(encoding="utf-8") + '\nmodel = "user-edit"\n',
            encoding="utf-8",
        )

        with self.assertRaises(ClientConfigChanged):
            self.manager.disable(ClientKind.CODEX)

        self.assertIn("user-edit", self.codex_config.read_text(encoding="utf-8"))

    def test_journal_failure_rolls_back_config_write(self) -> None:
        with patch.object(
            self.manager,
            "_write_json_atomic",
            side_effect=OSError("journal failed"),
        ):
            with self.assertRaises(OSError):
                self.manager.enable(ClientKind.CODEX, self.route)

        self.assertEqual(self.codex_config.read_bytes(), self.codex_original)
        self.assertFalse(
            (self.root / ".agenthub" / "client-integrations" / "codex.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
