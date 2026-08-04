from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_hub.providers.control import ProviderControl
from agent_hub.providers.models import (
    ClientKind,
    DefaultRouteInput,
    ProviderInput,
    ProviderProtocol,
    SessionRouteInput,
)
from agent_hub.providers.registry import ProviderRegistry
from agent_hub.providers.secrets import SecretStore
from agent_hub.providers.session_routes import SessionRouteStore


def _fake_protect(data: bytes) -> bytes:
    return b"enc(" + data + b")"


def _fake_unprotect(ciphertext: bytes) -> bytes:
    return ciphertext[4:-1]


class ProviderControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.registry_path = root / "providers.json"
        self.control = ProviderControl.from_paths(
            registry_path=self.registry_path,
            session_routes_path=root / "session-routes.json",
        )
        os.environ["AGENTHUB_TEST_KEY"] = "secret-value"

    def tearDown(self) -> None:
        os.environ.pop("AGENTHUB_TEST_KEY", None)
        self.temporary.cleanup()

    def test_provider_registry_never_persists_or_returns_secret_values(self) -> None:
        provider = self.control.save_provider(
            ProviderInput(
                id="test-openai",
                name="Test OpenAI",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://example.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                models=["test-model"],
            )
        )

        stored = json.loads(self.registry_path.read_text(encoding="utf-8"))

        self.assertEqual(provider.secret_env, "AGENTHUB_TEST_KEY")
        self.assertTrue(provider.credential_available)
        self.assertNotIn("secret-value", json.dumps(stored))
        self.assertNotIn("secret-value", self.registry_path.read_text(encoding="utf-8"))

    def test_concurrent_provider_updates_do_not_lose_successful_writes(self) -> None:
        def save(index: int) -> None:
            self.control.save_provider(
                ProviderInput(
                    id=f"provider-{index}",
                    name=f"Provider {index}",
                    protocol=ProviderProtocol.OPENAI_RESPONSES,
                    base_url=f"https://provider-{index}.test/v1",
                    models=["model-a"],
                )
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save, range(20)))

        self.assertEqual(len(self.control.list_providers()), 20)

    def test_concurrent_auto_id_generation_stays_unique(self) -> None:
        def save(index: int) -> None:
            self.control.save_provider(
                ProviderInput(
                    name="Same Name",
                    protocol=ProviderProtocol.OPENAI_RESPONSES,
                    base_url=f"https://same-{index}.test/v1",
                    models=["model-a"],
                )
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save, range(20)))

        provider_ids = {item.id for item in self.control.list_providers()}
        self.assertEqual(len(provider_ids), 20)
        self.assertEqual(len(self.control.list_providers()), 20)

    def test_default_route_explicit_model_and_session_binding_have_clear_precedence(self) -> None:
        self.control.save_provider(
            ProviderInput(
                id="primary",
                name="Primary",
                protocol=ProviderProtocol.OPENAI_COMPATIBLE,
                base_url="https://primary.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                models=["chat-a", "chat-b"],
            )
        )
        self.control.set_default_route(
            ClientKind.CODEX,
            DefaultRouteInput(provider_id="primary", model="chat-a"),
        )

        default_route = self.control.resolve_route(ClientKind.CODEX, requested_model="ignored")
        explicit_route = self.control.resolve_route(
            ClientKind.CODEX,
            requested_model="primary/chat-b",
        )
        self.control.bind_session(
            SessionRouteInput(
                client=ClientKind.CODEX,
                agent_id="codex-desktop",
                native_session_id="thread-1",
                provider_id="primary",
                model="chat-b",
            )
        )
        bound_route = self.control.resolve_route(
            ClientKind.CODEX,
            requested_model="primary/chat-a",
            agent_id="codex-desktop",
            native_session_id="thread-1",
        )

        self.assertEqual((default_route.provider.id, default_route.model), ("primary", "chat-a"))
        self.assertEqual((explicit_route.provider.id, explicit_route.model), ("primary", "chat-b"))
        self.assertEqual((bound_route.provider.id, bound_route.model), ("primary", "chat-b"))
        self.assertEqual(bound_route.source, "session")

    def test_model_ids_with_slashes_follow_default_unless_prefix_is_a_known_provider(self) -> None:
        self.control.save_provider(
            ProviderInput(
                id="openrouter",
                name="OpenRouter",
                protocol=ProviderProtocol.OPENAI_COMPATIBLE,
                base_url="https://openrouter.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                models=["anthropic/claude-test"],
            )
        )
        self.control.set_default_route(
            ClientKind.CLAUDE_CODE,
            DefaultRouteInput(
                provider_id="openrouter",
                model="anthropic/claude-test",
            ),
        )

        route = self.control.resolve_route(
            ClientKind.CLAUDE_CODE,
            requested_model="anthropic/claude-test",
        )

        self.assertEqual(route.provider.id, "openrouter")
        self.assertEqual(route.model, "anthropic/claude-test")

        with self.assertRaisesRegex(ValueError, "不存在的 Provider"):
            self.control.resolve_route(
                ClientKind.CLAUDE_CODE,
                requested_model="missing/model",
            )

    def test_manual_binding_replaces_observed_binding_and_can_return_to_default(self) -> None:
        self.control.save_provider(
            ProviderInput(
                id="primary",
                name="Primary",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://primary.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                models=["model-a", "model-b"],
            )
        )
        self.control.set_default_route(
            ClientKind.CODEX,
            DefaultRouteInput(provider_id="primary", model="model-a"),
        )
        self.control.record_observed_route(
            client=ClientKind.CODEX,
            agent_id="codex-desktop",
            native_session_id="thread-shared",
            provider_id="primary",
            model="model-a",
        )
        self.control.bind_session(
            SessionRouteInput(
                client=ClientKind.CODEX,
                agent_id="custom-codex-profile",
                native_session_id="thread-shared",
                provider_id="primary",
                model="model-b",
            )
        )

        bound = self.control.resolve_route(
            ClientKind.CODEX,
            agent_id="codex-desktop",
            native_session_id="thread-shared",
        )
        self.control.follow_default(
            ClientKind.CODEX,
            "custom-codex-profile",
            "thread-shared",
        )
        default = self.control.resolve_route(
            ClientKind.CODEX,
            agent_id="codex-desktop",
            native_session_id="thread-shared",
        )
        self.control.set_default_route(
            ClientKind.CODEX,
            DefaultRouteInput(provider_id="primary", model="model-b"),
        )
        changed_default = self.control.resolve_route(
            ClientKind.CODEX,
            agent_id="codex-desktop",
            native_session_id="thread-shared",
        )

        self.assertEqual(bound.model, "model-b")
        self.assertEqual(default.model, "model-a")
        self.assertEqual(default.source, "default")
        self.assertEqual(changed_default.model, "model-b")
        self.assertEqual(changed_default.source, "default")

    def test_discovered_historical_session_is_unresolved_until_user_chooses(self) -> None:
        self.control.save_provider(
            ProviderInput(
                id="primary",
                name="Primary",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://primary.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                models=["model-a"],
            )
        )
        self.control.set_default_route(
            ClientKind.CODEX,
            DefaultRouteInput(provider_id="primary", model="model-a"),
        )
        self.control.register_existing_sessions(
            ClientKind.CODEX,
            [("codex-desktop", "old-thread")],
        )
        views = self.control.route_views_for_sessions(
            ClientKind.CODEX,
            [("codex-desktop", "old-thread")],
        )

        self.assertEqual(views[("codex-desktop", "old-thread")].source, "unbound")
        self.assertFalse(views[("codex-desktop", "old-thread")].follows_default)
        with self.assertRaisesRegex(ValueError, "历史会话"):
            self.control.resolve_route(
                ClientKind.CODEX,
                agent_id="codex-desktop",
                native_session_id="old-thread",
            )

        new_views = self.control.route_views_for_sessions(
            ClientKind.CODEX,
            [("codex-desktop", "new-thread")],
        )
        self.assertEqual(new_views[("codex-desktop", "new-thread")].source, "default")

    def _control_with_fake_secrets(self) -> ProviderControl:
        root = Path(self.temporary.name)
        store = SecretStore(
            root / "fake-secrets.json",
            protect=_fake_protect,
            unprotect=_fake_unprotect,
        )
        return ProviderControl(
            ProviderRegistry(self.registry_path),
            SessionRouteStore(root / "session-routes.json"),
            secrets=store,
        )

    def test_missing_id_is_generated_from_name_and_stays_unique(self) -> None:
        first = self.control.save_provider(
            ProviderInput(
                name="OpenAI API",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://one.test/v1",
                models=["model-a"],
            )
        )
        second = self.control.save_provider(
            ProviderInput(
                name="OpenAI API",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://two.test/v1",
                models=["model-a"],
            )
        )
        chinese = self.control.save_provider(
            ProviderInput(
                name="我的 测试 提供商",
                protocol=ProviderProtocol.OPENAI_COMPATIBLE,
                base_url="https://three.test/v1",
            )
        )

        self.assertEqual(first.id, "openai-api")
        self.assertEqual(second.id, "openai-api-2")
        self.assertEqual(chinese.id, "provider")

    def test_api_key_is_encrypted_stored_and_never_returned(self) -> None:
        control = self._control_with_fake_secrets()
        view = control.save_provider(
            ProviderInput(
                name="Keyed Provider",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://keyed.test/v1",
                api_key="sk-plain-key",
            )
        )

        self.assertTrue(view.api_key_stored)
        self.assertTrue(view.credential_available)
        self.assertNotIn("sk-plain-key", view.model_dump_json())
        self.assertNotIn("sk-plain-key", self.registry_path.read_text(encoding="utf-8"))
        secrets_file = Path(self.temporary.name) / "fake-secrets.json"
        content = secrets_file.read_text(encoding="utf-8")
        self.assertNotIn("sk-plain-key", content)
        ciphertext = base64.b64decode(
            json.loads(content)["secrets"]["keyed-provider"]["ciphertext"]
        )
        self.assertEqual(ciphertext, b"enc(sk-plain-key)")

    def test_stored_key_takes_precedence_over_environment_variable(self) -> None:
        control = self._control_with_fake_secrets()
        control.save_provider(
            ProviderInput(
                name="Env Provider",
                protocol=ProviderProtocol.OPENAI_COMPATIBLE,
                base_url="https://env.test/v1",
                secret_env="AGENTHUB_TEST_KEY",
                api_key="stored-key",
            )
        )
        provider = control.get_provider("env-provider")

        self.assertIsNotNone(provider)
        self.assertEqual(control.credential_for(provider), "stored-key")

    def test_refresh_models_and_visibility_are_persisted(self) -> None:
        self.control.save_provider(
            ProviderInput(
                id="visible",
                name="Visible",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://visible.test/v1",
                models=["model-a", "model-b"],
            )
        )
        view = self.control.set_model_visibility("visible", "model-b", False)
        self.assertEqual(view.hidden_models, ["model-b"])

        refreshed = self.control.refresh_models("visible", ["model-a", "model-c"])
        self.assertEqual(refreshed.models, ["model-a", "model-c"])
        self.assertEqual(refreshed.hidden_models, [])

    def test_delete_provider_clears_stored_secret(self) -> None:
        control = self._control_with_fake_secrets()
        control.save_provider(
            ProviderInput(
                name="Delete Me",
                protocol=ProviderProtocol.OPENAI_RESPONSES,
                base_url="https://delete.test/v1",
                api_key="sk-delete",
            )
        )
        self.assertTrue(control.api_key_stored("delete-me"))

        self.assertTrue(control.delete_provider("delete-me"))
        self.assertFalse(control.api_key_stored("delete-me"))
        secrets_file = Path(self.temporary.name) / "fake-secrets.json"
        self.assertNotIn("delete-me", secrets_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
