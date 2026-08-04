from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from agent_hub.agents.config import AgentProfileStore
from agent_hub.bootstrap import create_configured_runtime
from agent_hub.main import create_app
from agent_hub.providers.models import ClientKind


class ProviderApiGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.agent_config = self.root / "agents.json"
        AgentProfileStore(self.agent_config).save([])
        self.codex_config = self.root / ".codex" / "config.toml"
        self.claude_settings = self.root / ".claude" / "settings.json"
        self.codex_config.parent.mkdir(parents=True)
        self.claude_settings.parent.mkdir(parents=True)
        self.codex_config.write_text('approval_policy = "never"\n', encoding="utf-8")
        self.claude_settings.write_text("{}\n", encoding="utf-8")
        os.environ["TEST_PROVIDER_KEY"] = "upstream-secret"
        self.requests: list[httpx.Request] = []

        async def upstream(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            body = json.loads(request.content.decode("utf-8")) if request.content else {}
            if request.url.path.endswith("/models"):
                if request.url.host == "fail.test":
                    return httpx.Response(500, json={"error": "boom"})
                return httpx.Response(
                    200,
                    json={"data": [{"id": "model-a"}, {"id": "model-b"}]},
                )
            if request.url.path.endswith("/responses"):
                return httpx.Response(
                    200,
                    json={
                        "id": "resp-1",
                        "object": "response",
                        "model": body["model"],
                        "output": [
                            {
                                "type": "message",
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": "responses-ok"}],
                            }
                        ],
                        "usage": {"input_tokens": 1, "output_tokens": 2},
                    },
                )
            if request.url.path.endswith("/chat/completions"):
                return httpx.Response(
                    200,
                    json={
                        "id": "chat-1",
                        "object": "chat.completion",
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "chat-ok"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                    },
                )
            if request.url.path.endswith("/messages"):
                if body.get("stream"):
                    events = [
                        ("message_start", {"type": "message_start", "message": {"id": "msg-1", "model": body["model"], "usage": {"input_tokens": 1, "output_tokens": 0}}}),
                        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
                        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "anthropic-ok"}}),
                        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}}),
                        ("message_stop", {"type": "message_stop"}),
                    ]
                    content = "".join(
                        f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events
                    )
                    return httpx.Response(200, text=content, headers={"content-type": "text/event-stream"})
                return httpx.Response(
                    200,
                    json={
                        "id": "msg-1",
                        "type": "message",
                        "role": "assistant",
                        "model": body["model"],
                        "content": [{"type": "text", "text": "anthropic-ok"}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 1, "output_tokens": 2},
                    },
                )
            raise AssertionError(f"unexpected upstream path {request.url.path}")

        self.runtime = create_configured_runtime(
            self.agent_config,
            data_dir=self.root / ".agenthub",
            codex_config_path=self.codex_config,
            claude_settings_path=self.claude_settings,
            allow_user_config_writes=True,
            gateway_transport=httpx.MockTransport(upstream),
        )
        self.client = TestClient(create_app(self.runtime))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        os.environ.pop("TEST_PROVIDER_KEY", None)
        self.temporary.cleanup()

    def _create_provider(self, provider_id: str, protocol: str) -> None:
        response = self.client.post(
            "/api/providers",
            json={
                "id": provider_id,
                "name": provider_id,
                "protocol": protocol,
                "base_url": "https://upstream.test/v1",
                "secret_env": "TEST_PROVIDER_KEY",
                "models": ["model-a"],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_management_api_health_and_client_takeover(self) -> None:
        self._create_provider("responses", "openai_responses")
        route = self.client.put(
            "/api/providers/routes/codex",
            json={"provider_id": "responses", "model": "model-a"},
        )
        health = self.client.post("/api/providers/responses/test")
        enabled = self.client.post("/api/clients/codex/integration/enable")

        self.assertEqual(route.status_code, 200)
        self.assertTrue(health.json()["ok"])
        self.assertTrue(enabled.json()["active"])
        self.assertEqual(self.client.get("/api/providers").json()["providers"][0]["credential_available"], True)
        self.assertEqual(self.requests[-1].headers["authorization"], "Bearer upstream-secret")
        model_ids = {item["id"] for item in self.client.get("/v1/models").json()["data"]}
        self.assertIn("responses/model-a", model_ids)
        self.assertIn("model-a", model_ids)

    def test_management_http_mutations_are_thread_safe_and_idempotent(self) -> None:
        def create(index: int) -> int:
            return self.client.post(
                "/api/providers",
                json={
                    "id": f"concurrent-{index}",
                    "name": f"Concurrent {index}",
                    "protocol": "openai_responses",
                    "base_url": "https://upstream.test/v1",
                    "secret_env": "TEST_PROVIDER_KEY",
                    "models": ["model-a"],
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=8) as executor:
            statuses = list(executor.map(create, range(12)))

        self.assertEqual(statuses, [201] * 12)
        provider_ids = {
            item["id"] for item in self.client.get("/api/providers").json()["providers"]
        }
        self.assertTrue({f"concurrent-{index}" for index in range(12)} <= provider_ids)

        def set_route(client: str, provider_id: str) -> int:
            return self.client.put(
                f"/api/providers/routes/{client}",
                json={"provider_id": provider_id, "model": "model-a"},
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            route_statuses = list(
                executor.map(
                    lambda item: set_route(*item),
                    (("codex", "concurrent-0"), ("claude_code", "concurrent-1")),
                )
            )
        self.assertEqual(route_statuses, [200, 200])
        defaults = {
            item["client"]: item["provider_id"]
            for item in self.client.get("/api/providers").json()["defaults"]
        }
        self.assertEqual(defaults, {"codex": "concurrent-0", "claude_code": "concurrent-1"})

        first_enable = self.client.post("/api/clients/codex/integration/enable")
        second_enable = self.client.post("/api/clients/codex/integration/enable")
        first_disable = self.client.post("/api/clients/codex/integration/disable")
        second_disable = self.client.post("/api/clients/codex/integration/disable")
        self.assertTrue(first_enable.json()["active"])
        self.assertTrue(second_enable.json()["active"])
        self.assertFalse(first_disable.json()["active"])
        self.assertFalse(second_disable.json()["active"])

        update_payload = {
            "id": "concurrent-2",
            "name": "Updated",
            "protocol": "openai_responses",
            "base_url": "https://upstream.test/v1",
            "models": ["model-a"],
        }
        first_update = self.client.put("/api/providers/concurrent-2", json=update_payload)
        second_update = self.client.put("/api/providers/concurrent-2", json=update_payload)
        self.assertEqual(first_update.json(), second_update.json())
        self.assertEqual(self.client.delete("/api/providers/concurrent-11").status_code, 204)
        self.assertEqual(self.client.delete("/api/providers/concurrent-11").status_code, 404)

    def test_cross_origin_state_change_is_rejected(self) -> None:
        response = self.client.post(
            "/api/providers",
            headers={"origin": "https://malicious.example"},
            json={
                "id": "blocked",
                "name": "Blocked",
                "protocol": "openai_responses",
                "base_url": "https://upstream.test/v1",
                "models": ["model-a"],
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.runtime.providers.list_providers(), [])

    def test_gateway_rejects_non_object_json(self) -> None:
        response = self.client.post("/v1/responses", json=[])

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON 对象", response.json()["detail"])

    def test_codex_responses_passthrough_rewrites_route_and_auth(self) -> None:
        self._create_provider("responses", "openai_responses")
        self.client.put(
            "/api/providers/routes/codex",
            json={"provider_id": "responses", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/responses",
            json={"model": "client-model", "input": "hello", "stream": False},
            headers={"authorization": "Bearer agenthub-local"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["output"][0]["content"][0]["text"], "responses-ok")
        upstream_body = json.loads(self.requests[-1].content)
        self.assertEqual(upstream_body["model"], "model-a")
        self.assertEqual(self.requests[-1].headers["authorization"], "Bearer upstream-secret")

    def test_codex_to_anthropic_stream_is_converted_to_responses_sse(self) -> None:
        self._create_provider("anthropic", "anthropic")
        self.client.put(
            "/api/providers/routes/codex",
            json={"provider_id": "anthropic", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/responses",
            json={
                "model": "client-model",
                "input": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: response.output_text.delta", response.text)
        self.assertIn("anthropic-ok", response.text)
        self.assertTrue(self.requests[-1].url.path.endswith("/messages"))
        self.assertEqual(self.requests[-1].headers["x-api-key"], "upstream-secret")

    def test_claude_to_openai_compatible_returns_anthropic_message(self) -> None:
        self._create_provider("compatible", "openai_compatible")
        self.client.put(
            "/api/providers/routes/claude_code",
            json={"provider_id": "compatible", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/messages",
            json={
                "model": "claude-client-model",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 100,
                "stream": False,
                "metadata": {"user_id": "user_test_session_claude-session-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"][0]["text"], "chat-ok")
        self.assertTrue(self.requests[-1].url.path.endswith("/chat/completions"))
        observed = self.runtime.providers.find_session_route(
            client=ClientKind.CLAUDE_CODE,
            native_session_id="claude-session-1",
        )
        self.assertEqual(observed.provider_id, "compatible")

    def test_claude_to_anthropic_is_passed_through(self) -> None:
        self._create_provider("anthropic", "anthropic")
        self.client.put(
            "/api/providers/routes/claude_code",
            json={"provider_id": "anthropic", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/messages",
            json={
                "model": "claude-client-model",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 100,
                "stream": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"][0]["text"], "anthropic-ok")
        self.assertEqual(self.requests[-1].headers["anthropic-version"], "2023-06-01")

    def test_claude_to_responses_stream_returns_anthropic_sse(self) -> None:
        self._create_provider("responses", "openai_responses")
        self.client.put(
            "/api/providers/routes/claude_code",
            json={"provider_id": "responses", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/messages",
            json={
                "model": "claude-client-model",
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 100,
                "stream": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: content_block_delta", response.text)
        self.assertIn("responses-ok", response.text)

    def test_codex_to_openai_compatible_returns_responses_payload(self) -> None:
        self._create_provider("compatible", "openai_compatible")
        self.client.put(
            "/api/providers/routes/codex",
            json={"provider_id": "compatible", "model": "model-a"},
        )

        response = self.client.post(
            "/v1/responses",
            json={"model": "client-model", "input": "hello", "stream": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["output"][0]["content"][0]["text"], "chat-ok")

    def test_create_provider_without_id_auto_detects_models_and_encrypts_key(self) -> None:
        response = self.client.post(
            "/api/providers",
            json={
                "name": "Keyed Gateway",
                "protocol": "openai_responses",
                "base_url": "https://upstream.test/v1",
                "api_key": "sk-gateway-secret",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        provider = response.json()
        self.assertEqual(provider["id"], "keyed-gateway")
        self.assertEqual(provider["models"], ["model-a", "model-b"])
        self.assertTrue(provider["api_key_stored"])
        self.assertTrue(provider["credential_available"])
        self.assertNotIn("api_key", provider)
        self.assertNotIn("sk-gateway-secret", response.text)
        secrets_path = self.root / ".agenthub" / "secrets.json"
        self.assertTrue(secrets_path.is_file())
        self.assertNotIn("sk-gateway-secret", secrets_path.read_text(encoding="utf-8"))

        self.client.put(
            "/api/providers/routes/codex",
            json={"provider_id": "keyed-gateway", "model": "model-a"},
        )
        forwarded = self.client.post(
            "/v1/responses",
            json={"model": "client-model", "input": "hello", "stream": False},
        )
        self.assertEqual(forwarded.status_code, 200)
        self.assertEqual(
            self.requests[-1].headers["authorization"],
            "Bearer sk-gateway-secret",
        )

    def test_model_visibility_hides_models_from_v1_models(self) -> None:
        self._create_provider("visible", "openai_responses")
        hidden = self.client.post(
            "/api/providers/visible/models/visibility",
            json={"model": "model-b", "visible": False},
        )
        self.assertEqual(hidden.status_code, 200)
        self.assertEqual(hidden.json()["hidden_models"], ["model-b"])

        model_ids = {
            item["id"] for item in self.client.get("/v1/models").json()["data"]
        }
        self.assertIn("visible/model-a", model_ids)
        self.assertNotIn("visible/model-b", model_ids)

        shown = self.client.post(
            "/api/providers/visible/models/visibility",
            json={"model": "model-b", "visible": True},
        )
        self.assertEqual(shown.json()["hidden_models"], [])

    def test_refresh_models_endpoint_updates_provider(self) -> None:
        self._create_provider("refreshable", "openai_responses")
        response = self.client.post("/api/providers/refreshable/models/refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["models"], ["model-a", "model-b"])

    def test_detection_failure_warns_but_provider_is_saved(self) -> None:
        response = self.client.post(
            "/api/providers",
            json={
                "name": "Broken Gateway",
                "protocol": "openai_responses",
                "base_url": "https://fail.test/v1",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["models"], [])
        self.assertIn("模型自动检测失败", response.json()["detection_warning"])

    def test_edit_without_api_key_keeps_stored_secret(self) -> None:
        created = self.client.post(
            "/api/providers",
            json={
                "name": "Persist Key",
                "protocol": "openai_responses",
                "base_url": "https://upstream.test/v1",
                "api_key": "sk-persist",
            },
        )
        self.assertEqual(created.status_code, 201)
        provider_id = created.json()["id"]

        updated = self.client.put(
            f"/api/providers/{provider_id}",
            json={
                "id": provider_id,
                "name": "Persist Key Renamed",
                "protocol": "openai_responses",
                "base_url": "https://upstream.test/v1",
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertTrue(updated.json()["api_key_stored"])
        self.assertTrue(updated.json()["credential_available"])

    def test_delete_provider_clears_stored_secret_file_entry(self) -> None:
        created = self.client.post(
            "/api/providers",
            json={
                "name": "Temp Secret",
                "protocol": "openai_responses",
                "base_url": "https://upstream.test/v1",
                "api_key": "sk-temp",
            },
        )
        self.assertEqual(created.status_code, 201)
        provider_id = created.json()["id"]
        secrets_path = self.root / ".agenthub" / "secrets.json"
        self.assertIn(provider_id, secrets_path.read_text(encoding="utf-8"))

        self.assertEqual(self.client.delete(f"/api/providers/{provider_id}").status_code, 204)
        self.assertNotIn(provider_id, secrets_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
