from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
