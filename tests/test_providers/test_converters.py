from __future__ import annotations

import unittest

from agent_hub.providers.converters import (
    CanonicalResponse,
    canonical_from_payload,
    prepare_upstream,
    render_payload,
    render_sse,
)
from agent_hub.providers.models import ClientKind, ProviderProtocol


class ProtocolConverterTests(unittest.TestCase):
    def test_length_finish_reason_is_not_reported_as_normal_completion(self) -> None:
        response = CanonicalResponse(
            id="response-1",
            model="model-a",
            text="partial",
            finish_reason="length",
        )

        claude = render_payload(ClientKind.CLAUDE_CODE, response)
        codex = render_payload(ClientKind.CODEX, response)
        codex_stream = render_sse(ClientKind.CODEX, response).decode("utf-8")

        self.assertEqual(claude["stop_reason"], "max_tokens")
        self.assertEqual(codex["status"], "incomplete")
        self.assertIn("event: response.incomplete", codex_stream)

    def test_codex_function_calls_round_trip_through_anthropic_shape(self) -> None:
        prepared = prepare_upstream(
            ClientKind.CODEX,
            ProviderProtocol.ANTHROPIC,
            {
                "model": "client-model",
                "input": [
                    {"role": "user", "content": "read file"},
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "read_file",
                        "arguments": '{"path":"README.md"}',
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "contents",
                    },
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "read_file",
                        "parameters": {
                            "type": "object",
                            "properties": {"path": {"type": "string"}},
                        },
                    }
                ],
                "stream": True,
            },
            "claude-upstream",
        )

        content_types = [
            block["type"]
            for message in prepared.payload["messages"]
            for block in message["content"]
            if isinstance(message.get("content"), list)
        ]

        self.assertIn("tool_use", content_types)
        self.assertIn("tool_result", content_types)
        self.assertEqual(prepared.payload["tools"][0]["input_schema"]["type"], "object")

        canonical = canonical_from_payload(
            ProviderProtocol.ANTHROPIC,
            {
                "id": "msg-1",
                "model": "claude-upstream",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-2",
                        "name": "write_file",
                        "input": {"path": "out.txt"},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 2, "output_tokens": 3},
            },
        )
        rendered = render_payload(ClientKind.CODEX, canonical)

        self.assertEqual(rendered["output"][0]["type"], "function_call")
        self.assertEqual(rendered["output"][0]["name"], "write_file")
        self.assertEqual(rendered["output"][0]["arguments"], '{"path": "out.txt"}')

    def test_claude_tool_definition_maps_to_openai_compatible(self) -> None:
        prepared = prepare_upstream(
            ClientKind.CLAUDE_CODE,
            ProviderProtocol.OPENAI_COMPATIBLE,
            {
                "model": "client-model",
                "messages": [{"role": "user", "content": "search"}],
                "tools": [
                    {
                        "name": "search",
                        "description": "Search files",
                        "input_schema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    }
                ],
                "max_tokens": 100,
                "stream": False,
            },
            "chat-upstream",
        )

        self.assertEqual(prepared.resource, "chat/completions")
        self.assertEqual(prepared.payload["tools"][0]["function"]["name"], "search")
        self.assertEqual(
            prepared.payload["tools"][0]["function"]["parameters"]["type"],
            "object",
        )


if __name__ == "__main__":
    unittest.main()
