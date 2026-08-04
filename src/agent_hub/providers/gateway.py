from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
from fastapi.responses import JSONResponse, Response, StreamingResponse

from agent_hub.providers.control import ProviderControl
from agent_hub.providers.converters import (
    canonical_from_payload,
    canonical_from_sse,
    prepare_upstream,
    render_payload,
    render_sse,
)
from agent_hub.providers.models import ClientKind, ProviderHealth, ProviderProfile, ProviderProtocol


class ProviderGateway:
    def __init__(
        self,
        control: ProviderControl,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.control = control
        self._transport = transport
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client_active(self) -> bool:
        return self._client is not None and not self._client.is_closed

    async def test_provider(self, provider_id: str) -> ProviderHealth:
        provider = self.control.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"Provider 不存在：{provider_id}")
        try:
            models = await self.fetch_models(provider_id)
            return ProviderHealth(
                ok=True,
                provider_id=provider.id,
                message=f"连接成功，发现 {len(models)} 个模型。",
                models=models,
            )
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as error:
            return ProviderHealth(
                ok=False,
                provider_id=provider.id,
                message=f"连接失败：{error}",
            )

    async def fetch_models(self, provider_id: str) -> list[str]:
        provider = self.control.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"Provider 不存在：{provider_id}")
        response = await self._http_client().get(
            self._endpoint(provider.base_url, "models"),
            headers=self._upstream_headers(provider, {}),
        )
        response.raise_for_status()
        payload = response.json()
        return [
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]

    async def forward(
        self,
        client: ClientKind,
        payload: dict[str, Any],
        incoming_headers: Mapping[str, str],
    ) -> Response:
        native_session_id = self._session_id(client, incoming_headers, payload)
        agent_id = incoming_headers.get("x-agenthub-agent-id") or self._canonical_agent_id(client)
        route = self.control.resolve_route(
            client,
            requested_model=str(payload.get("model") or ""),
            agent_id=agent_id if native_session_id else None,
            native_session_id=native_session_id,
        )
        if native_session_id:
            self.control.record_observed_route(
                client=client,
                agent_id=agent_id,
                native_session_id=native_session_id,
                provider_id=route.provider.id,
                model=route.model,
            )
        prepared = prepare_upstream(client, route.provider.protocol, payload, route.model)
        http_client = self._http_client()
        request = http_client.build_request(
            "POST",
            self._endpoint(route.provider.base_url, prepared.resource),
            json=prepared.payload,
            headers=self._upstream_headers(route.provider, incoming_headers),
        )
        upstream = await http_client.send(request, stream=True)
        if upstream.status_code >= 400:
            content = await upstream.aread()
            media_type = upstream.headers.get("content-type", "application/json").split(";", 1)[0]
            await upstream.aclose()
            return Response(content=content, status_code=upstream.status_code, media_type=media_type)

        wants_stream = bool(payload.get("stream"))
        if wants_stream and prepared.passthrough:
            async def stream_body():
                try:
                    async for chunk in upstream.aiter_raw():
                        yield chunk
                finally:
                    await upstream.aclose()

            return StreamingResponse(
                stream_body(),
                status_code=upstream.status_code,
                media_type="text/event-stream",
                headers={"cache-control": "no-cache"},
            )

        content = await upstream.aread()
        content_type = upstream.headers.get("content-type", "")
        await upstream.aclose()
        if prepared.passthrough:
            return Response(
                content=content,
                status_code=upstream.status_code,
                media_type=content_type.split(";", 1)[0] or "application/json",
            )

        if "text/event-stream" in content_type:
            canonical = canonical_from_sse(prepared.response_protocol, content)
        else:
            canonical = canonical_from_payload(
                prepared.response_protocol,
                json.loads(content.decode("utf-8")),
            )
        canonical.model = route.model
        if wants_stream:
            return Response(
                content=render_sse(client, canonical),
                status_code=upstream.status_code,
                media_type="text/event-stream",
                headers={"cache-control": "no-cache"},
            )
        return JSONResponse(render_payload(client, canonical), status_code=upstream.status_code)

    def _upstream_headers(
        self,
        provider: ProviderProfile,
        incoming: Mapping[str, str],
    ) -> dict[str, str]:
        headers = {
            key: value
            for key, value in incoming.items()
            if key.lower() in {"accept", "anthropic-version", "anthropic-beta", "openai-beta"}
        }
        secret = self.control.credential_for(provider)
        if provider.secret_env and not secret:
            raise ValueError(f"环境变量 {provider.secret_env} 未设置。")
        if secret:
            if provider.protocol == ProviderProtocol.ANTHROPIC:
                headers["x-api-key"] = secret
            else:
                headers["authorization"] = f"Bearer {secret}"
        if provider.protocol == ProviderProtocol.ANTHROPIC:
            headers.setdefault("anthropic-version", "2023-06-01")
        return headers

    def _http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
            )
        return self._client

    @staticmethod
    def _endpoint(base_url: str, resource: str) -> str:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/{resource}"
        return f"{base}/v1/{resource}"

    @staticmethod
    def _session_id(
        client: ClientKind,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> str | None:
        candidates = (
            ("x-codex-parent-thread-id", "session_id", "x-session-id")
            if client == ClientKind.CODEX
            else (
                "x-claude-code-session-id",
                "claude-code-session-id",
                "x-claude-session-id",
                "x-session-id",
            )
        )
        header_value = next((headers.get(name) for name in candidates if headers.get(name)), None)
        if header_value:
            return header_value
        metadata = payload.get("metadata")
        if not isinstance(metadata, Mapping):
            return None
        session_id = metadata.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
        user_id = metadata.get("user_id")
        if isinstance(user_id, str) and "_session_" in user_id:
            suffix = user_id.split("_session_", 1)[1]
            return suffix or None
        return None

    @staticmethod
    def _canonical_agent_id(client: ClientKind) -> str:
        return "codex-desktop" if client == ClientKind.CODEX else "claude-code"
