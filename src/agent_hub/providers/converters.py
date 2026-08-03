from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent_hub.providers.models import ClientKind, ProviderProtocol


@dataclass(frozen=True)
class UpstreamRequest:
    resource: str
    payload: dict[str, Any]
    response_protocol: ProviderProtocol
    passthrough: bool


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class CanonicalResponse:
    id: str
    model: str
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0


def prepare_upstream(
    client: ClientKind,
    protocol: ProviderProtocol,
    payload: dict[str, Any],
    model: str,
) -> UpstreamRequest:
    body = copy.deepcopy(payload)
    if client == ClientKind.CODEX:
        if protocol == ProviderProtocol.OPENAI_RESPONSES:
            body["model"] = model
            return UpstreamRequest("responses", body, protocol, passthrough=True)
        if protocol == ProviderProtocol.OPENAI_COMPATIBLE:
            return UpstreamRequest(
                "chat/completions",
                responses_to_chat(body, model),
                protocol,
                passthrough=False,
            )
        return UpstreamRequest(
            "messages",
            responses_to_anthropic(body, model),
            protocol,
            passthrough=False,
        )

    if protocol == ProviderProtocol.ANTHROPIC:
        body["model"] = model
        return UpstreamRequest("messages", body, protocol, passthrough=True)
    if protocol == ProviderProtocol.OPENAI_COMPATIBLE:
        return UpstreamRequest(
            "chat/completions",
            anthropic_to_chat(body, model),
            protocol,
            passthrough=False,
        )
    return UpstreamRequest(
        "responses",
        anthropic_to_responses(body, model),
        protocol,
        passthrough=False,
    )


def responses_to_chat(payload: dict[str, Any], model: str) -> dict[str, Any]:
    messages, system = _responses_messages(payload.get("input"))
    instructions = payload.get("instructions")
    if instructions:
        system.insert(0, str(instructions))
    if system:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system)})
    result: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(payload.get("stream")),
    }
    if "temperature" in payload:
        result["temperature"] = payload["temperature"]
    if "max_output_tokens" in payload:
        result["max_tokens"] = payload["max_output_tokens"]
    tools = [_responses_tool_to_chat(item) for item in payload.get("tools", [])]
    if tools:
        result["tools"] = tools
    return result


def responses_to_anthropic(payload: dict[str, Any], model: str) -> dict[str, Any]:
    messages, system = _responses_messages(payload.get("input"), anthropic=True)
    instructions = payload.get("instructions")
    if instructions:
        system.insert(0, str(instructions))
    result: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": int(payload.get("max_output_tokens") or 4096),
        "stream": bool(payload.get("stream")),
    }
    if system:
        result["system"] = "\n\n".join(system)
    if "temperature" in payload:
        result["temperature"] = payload["temperature"]
    tools = [_responses_tool_to_anthropic(item) for item in payload.get("tools", [])]
    if tools:
        result["tools"] = tools
    return result


def anthropic_to_chat(payload: dict[str, Any], model: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = []
    system = _content_text(payload.get("system"))
    if system:
        messages.append({"role": "system", "content": system})
    for item in payload.get("messages", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text") or ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"call_{uuid4().hex}"),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or "tool"),
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
            elif block.get("type") == "tool_result":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(block.get("tool_use_id") or ""),
                        "content": _content_text(block.get("content")),
                    }
                )
        if text_parts or tool_calls:
            message: dict[str, Any] = {"role": role, "content": "\n".join(text_parts) or None}
            if tool_calls:
                message["tool_calls"] = tool_calls
            messages.append(message)
    result: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(payload.get("stream")),
        "max_tokens": int(payload.get("max_tokens") or 4096),
    }
    if "temperature" in payload:
        result["temperature"] = payload["temperature"]
    tools = []
    for item in payload.get("tools", []):
        if isinstance(item, dict):
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "description": item.get("description"),
                        "parameters": item.get("input_schema") or {"type": "object"},
                    },
                }
            )
    if tools:
        result["tools"] = tools
    return result


def anthropic_to_responses(payload: dict[str, Any], model: str) -> dict[str, Any]:
    input_items: list[dict[str, Any]] = []
    for item in payload.get("messages", []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, str):
            input_items.append({"role": role, "content": content})
            continue
        text_blocks: list[dict[str, str]] = []
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_blocks.append({"type": "input_text", "text": str(block.get("text") or "")})
            elif block.get("type") == "tool_use":
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                    }
                )
            elif block.get("type") == "tool_result":
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": block.get("tool_use_id"),
                        "output": _content_text(block.get("content")),
                    }
                )
        if text_blocks:
            input_items.append({"role": role, "content": text_blocks})
    result: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "stream": bool(payload.get("stream")),
    }
    system = _content_text(payload.get("system"))
    if system:
        result["instructions"] = system
    if "max_tokens" in payload:
        result["max_output_tokens"] = payload["max_tokens"]
    tools = []
    for item in payload.get("tools", []):
        if isinstance(item, dict):
            tools.append(
                {
                    "type": "function",
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "parameters": item.get("input_schema") or {"type": "object"},
                }
            )
    if tools:
        result["tools"] = tools
    return result


def canonical_from_payload(protocol: ProviderProtocol, payload: dict[str, Any]) -> CanonicalResponse:
    if protocol == ProviderProtocol.ANTHROPIC:
        content = payload.get("content", [])
        text: list[str] = []
        calls: list[ToolCall] = []
        for item in content if isinstance(content, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                text.append(str(item.get("text") or ""))
            elif item.get("type") == "tool_use":
                calls.append(
                    ToolCall(
                        id=str(item.get("id") or f"call_{uuid4().hex}"),
                        name=str(item.get("name") or "tool"),
                        arguments=json.dumps(item.get("input") or {}, ensure_ascii=False),
                    )
                )
        usage = payload.get("usage") or {}
        return CanonicalResponse(
            id=str(payload.get("id") or f"msg_{uuid4().hex}"),
            model=str(payload.get("model") or ""),
            text="".join(text),
            tool_calls=calls,
            finish_reason=str(payload.get("stop_reason") or "stop"),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )

    if protocol == ProviderProtocol.OPENAI_COMPATIBLE:
        choices = payload.get("choices") or [{}]
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        calls = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") or {}
            calls.append(
                ToolCall(
                    id=str(item.get("id") or f"call_{uuid4().hex}"),
                    name=str(function.get("name") or "tool"),
                    arguments=str(function.get("arguments") or "{}"),
                )
            )
        usage = payload.get("usage") or {}
        return CanonicalResponse(
            id=str(payload.get("id") or f"chatcmpl_{uuid4().hex}"),
            model=str(payload.get("model") or ""),
            text=str(message.get("content") or ""),
            tool_calls=calls,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )

    text: list[str] = []
    calls: list[ToolCall] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for block in item.get("content", []):
                if isinstance(block, dict) and block.get("type") in {"output_text", "text"}:
                    text.append(str(block.get("text") or ""))
        elif item.get("type") == "function_call":
            calls.append(
                ToolCall(
                    id=str(item.get("call_id") or item.get("id") or f"call_{uuid4().hex}"),
                    name=str(item.get("name") or "tool"),
                    arguments=str(item.get("arguments") or "{}"),
                )
            )
    usage = payload.get("usage") or {}
    status = str(payload.get("status") or "completed")
    incomplete = payload.get("incomplete_details") or {}
    finish_reason = str(incomplete.get("reason") or status)
    return CanonicalResponse(
        id=str(payload.get("id") or f"resp_{uuid4().hex}"),
        model=str(payload.get("model") or ""),
        text="".join(text),
        tool_calls=calls,
        finish_reason=finish_reason,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )


def canonical_from_sse(protocol: ProviderProtocol, content: bytes) -> CanonicalResponse:
    events = _sse_events(content)
    if protocol == ProviderProtocol.ANTHROPIC:
        message: dict[str, Any] = {"content": [], "usage": {}}
        blocks: dict[int, dict[str, Any]] = {}
        for _, data in events:
            event_type = data.get("type")
            if event_type == "message_start":
                message.update(data.get("message") or {})
                message.setdefault("content", [])
            elif event_type == "content_block_start":
                blocks[int(data.get("index") or 0)] = copy.deepcopy(data.get("content_block") or {})
            elif event_type == "content_block_delta":
                block = blocks.setdefault(int(data.get("index") or 0), {})
                delta = data.get("delta") or {}
                if delta.get("type") == "text_delta":
                    block["type"] = "text"
                    block["text"] = str(block.get("text") or "") + str(delta.get("text") or "")
                elif delta.get("type") == "input_json_delta":
                    block["_json"] = str(block.get("_json") or "") + str(delta.get("partial_json") or "")
            elif event_type == "message_delta":
                message["stop_reason"] = (data.get("delta") or {}).get("stop_reason")
                message["usage"] = {**(message.get("usage") or {}), **(data.get("usage") or {})}
        for index in sorted(blocks):
            block = blocks[index]
            if block.get("type") == "tool_use" and "_json" in block:
                try:
                    block["input"] = json.loads(block.pop("_json") or "{}")
                except json.JSONDecodeError:
                    block["input"] = {}
            message["content"].append(block)
        return canonical_from_payload(protocol, message)

    if protocol == ProviderProtocol.OPENAI_COMPATIBLE:
        payload: dict[str, Any] = {"choices": [{"message": {"content": "", "tool_calls": []}}]}
        calls: dict[int, dict[str, Any]] = {}
        for _, data in events:
            payload["id"] = data.get("id", payload.get("id"))
            payload["model"] = data.get("model", payload.get("model"))
            choice = (data.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            payload["choices"][0]["message"]["content"] += str(delta.get("content") or "")
            if choice.get("finish_reason"):
                payload["choices"][0]["finish_reason"] = choice["finish_reason"]
            for item in delta.get("tool_calls") or []:
                index = int(item.get("index") or 0)
                call = calls.setdefault(index, {"id": item.get("id"), "type": "function", "function": {"name": "", "arguments": ""}})
                function = item.get("function") or {}
                call["id"] = item.get("id") or call.get("id")
                call["function"]["name"] += str(function.get("name") or "")
                call["function"]["arguments"] += str(function.get("arguments") or "")
            if data.get("usage"):
                payload["usage"] = data["usage"]
        payload["choices"][0]["message"]["tool_calls"] = [calls[key] for key in sorted(calls)]
        return canonical_from_payload(protocol, payload)

    completed = next(
        (data.get("response") for name, data in reversed(events) if name == "response.completed" and data.get("response")),
        None,
    )
    if isinstance(completed, dict):
        return canonical_from_payload(protocol, completed)
    text = "".join(
        str(data.get("delta") or "")
        for name, data in events
        if name == "response.output_text.delta"
    )
    return CanonicalResponse(id=f"resp_{uuid4().hex}", model="", text=text)


def render_payload(client: ClientKind, response: CanonicalResponse) -> dict[str, Any]:
    if client == ClientKind.CLAUDE_CODE:
        content: list[dict[str, Any]] = []
        if response.text:
            content.append({"type": "text", "text": response.text})
        content.extend(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": _json_object(call.arguments),
            }
            for call in response.tool_calls
        )
        stop_reason = _anthropic_stop_reason(response)
        return {
            "id": response.id,
            "type": "message",
            "role": "assistant",
            "model": response.model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            },
        }

    output: list[dict[str, Any]] = []
    if response.text:
        output.append(
            {
                "id": f"msg_{uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": response.text, "annotations": []}],
            }
        )
    output.extend(
        {
            "id": f"fc_{uuid4().hex}",
            "type": "function_call",
            "status": "completed",
            "call_id": call.id,
            "name": call.name,
            "arguments": call.arguments,
        }
        for call in response.tool_calls
    )
    response_status = _responses_status(response.finish_reason)
    result = {
        "id": response.id,
        "object": "response",
        "status": response_status,
        "model": response.model,
        "output": output,
        "usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "total_tokens": response.input_tokens + response.output_tokens,
        },
    }
    if response_status == "incomplete":
        result["incomplete_details"] = {"reason": "max_output_tokens"}
    return result


def render_sse(client: ClientKind, response: CanonicalResponse) -> bytes:
    if client == ClientKind.CLAUDE_CODE:
        stop_reason = _anthropic_stop_reason(response)
        events: list[tuple[str, dict[str, Any]]] = [
            (
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": response.id,
                        "type": "message",
                        "role": "assistant",
                        "model": response.model,
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": response.input_tokens, "output_tokens": 0},
                    },
                },
            )
        ]
        index = 0
        if response.text:
            events.extend(
                [
                    ("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}}),
                    ("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": response.text}}),
                    ("content_block_stop", {"type": "content_block_stop", "index": index}),
                ]
            )
            index += 1
        for call in response.tool_calls:
            events.extend(
                [
                    ("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": call.id, "name": call.name, "input": {}}}),
                    ("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": call.arguments}}),
                    ("content_block_stop", {"type": "content_block_stop", "index": index}),
                ]
            )
            index += 1
        events.extend(
            [
                ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": response.output_tokens}}),
                ("message_stop", {"type": "message_stop"}),
            ]
        )
        return _encode_sse(events)

    response_payload = render_payload(client, response)
    events = [("response.created", {"type": "response.created", "response": {**response_payload, "status": "in_progress", "output": []}})]
    index = 0
    if response.text:
        item = response_payload["output"][0]
        events.extend(
            [
                ("response.output_item.added", {"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress", "content": []}}),
                ("response.content_part.added", {"type": "response.content_part.added", "item_id": item["id"], "output_index": index, "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}}),
                ("response.output_text.delta", {"type": "response.output_text.delta", "item_id": item["id"], "output_index": index, "content_index": 0, "delta": response.text}),
                ("response.output_text.done", {"type": "response.output_text.done", "item_id": item["id"], "output_index": index, "content_index": 0, "text": response.text}),
                ("response.content_part.done", {"type": "response.content_part.done", "item_id": item["id"], "output_index": index, "content_index": 0, "part": item["content"][0]}),
                ("response.output_item.done", {"type": "response.output_item.done", "output_index": index, "item": item}),
            ]
        )
        index += 1
    tool_items = [item for item in response_payload["output"] if item.get("type") == "function_call"]
    for item in tool_items:
        events.extend(
            [
                ("response.output_item.added", {"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress", "arguments": ""}}),
                ("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "item_id": item["id"], "output_index": index, "delta": item["arguments"]}),
                ("response.function_call_arguments.done", {"type": "response.function_call_arguments.done", "item_id": item["id"], "output_index": index, "arguments": item["arguments"]}),
                ("response.output_item.done", {"type": "response.output_item.done", "output_index": index, "item": item}),
            ]
        )
        index += 1
    terminal_event = (
        "response.incomplete"
        if response_payload["status"] == "incomplete"
        else "response.completed"
    )
    events.append((terminal_event, {"type": terminal_event, "response": response_payload}))
    return _encode_sse(events)


def _anthropic_stop_reason(response: CanonicalResponse) -> str:
    if response.tool_calls:
        return "tool_use"
    if response.finish_reason in {
        "length",
        "max_tokens",
        "max_output_tokens",
        "incomplete",
    }:
        return "max_tokens"
    if response.finish_reason == "stop_sequence":
        return "stop_sequence"
    return "end_turn"


def _responses_status(finish_reason: str) -> str:
    return (
        "incomplete"
        if finish_reason
        in {"length", "max_tokens", "max_output_tokens", "incomplete"}
        else "completed"
    )


def _responses_messages(value: object, *, anthropic: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(value, str):
        return ([{"role": "user", "content": value}], [])
    messages: list[dict[str, Any]] = []
    system: list[str] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = str(item.get("role") or "user")
        if item_type == "function_call":
            call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid4().hex}")
            arguments = str(item.get("arguments") or "{}")
            if anthropic:
                messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": call_id, "name": item.get("name"), "input": _json_object(arguments)}]})
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": item.get("name"), "arguments": arguments}}]})
            continue
        if item_type == "function_call_output":
            if anthropic:
                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": item.get("call_id"), "content": _content_text(item.get("output"))}]})
            else:
                messages.append({"role": "tool", "tool_call_id": item.get("call_id"), "content": _content_text(item.get("output"))})
            continue
        text = _content_text(item.get("content"))
        if role in {"system", "developer"}:
            if text:
                system.append(text)
        elif text:
            messages.append({"role": role, "content": text})
    return messages, system


def _responses_tool_to_chat(item: object) -> dict[str, Any]:
    value = item if isinstance(item, dict) else {}
    return {"type": "function", "function": {"name": value.get("name"), "description": value.get("description"), "parameters": value.get("parameters") or {"type": "object"}}}


def _responses_tool_to_anthropic(item: object) -> dict[str, Any]:
    value = item if isinstance(item, dict) else {}
    return {"name": value.get("name"), "description": value.get("description"), "input_schema": value.get("parameters") or {"type": "object"}}


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    if isinstance(value, list):
        return "\n".join(
            str(item.get("text") or item.get("content") or "")
            for item in value
            if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}
        )
    return str(value) if value is not None else ""


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"value": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _sse_events(content: bytes) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in content.decode("utf-8", errors="replace").splitlines() + [""]:
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif not line and data_lines:
            raw = "\n".join(data_lines)
            data_lines = []
            if raw == "[DONE]":
                event_name = "message"
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                event_name = "message"
                continue
            if isinstance(payload, dict):
                result.append((event_name, payload))
            event_name = "message"
    return result


def _encode_sse(events: list[tuple[str, dict[str, Any]]]) -> bytes:
    return "".join(
        f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
        for name, payload in events
    ).encode("utf-8")
