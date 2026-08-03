from __future__ import annotations

import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agent_hub.agents.models import AgentProfileInput, AgentProfilePatch
from agent_hub.bootstrap import AgentHubRuntime, create_configured_runtime
from agent_hub.providers.clients import ClientConfigChanged, UnsafeClientConfigPath
from agent_hub.providers.models import (
    ClientKind,
    DefaultRouteInput,
    ProviderInput,
    SessionRouteAction,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def create_app(runtime: AgentHubRuntime | None = None) -> FastAPI:
    active_runtime = runtime or create_configured_runtime()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Register pre-existing native sessions before the gateway accepts traffic.
        # Unknown historical routes fail closed until the user chooses a route.
        await active_runtime.sessions.register_existing_routes()
        yield
        await active_runtime.aclose()

    application = FastAPI(
        title="Agent Session Hub MVP",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.middleware("http")
    async def reject_cross_origin_mutations(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin.rstrip("/") != expected.rstrip("/"):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "拒绝跨来源修改本地 AgentHub 状态。"},
                )
        return await call_next(request)

    @application.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/summary")
    async def get_summary():
        return await active_runtime.sessions.summary()

    @application.get("/api/dashboard")
    async def get_dashboard():
        dashboard = await active_runtime.sessions.dashboard()
        dashboard["agents"] = active_runtime.agents.list_profiles()
        return dashboard

    @application.get("/api/sessions")
    async def get_sessions():
        return await active_runtime.sessions.list_sessions()

    @application.get("/api/attention")
    async def get_attention():
        return await active_runtime.sessions.attention_sessions()

    @application.get("/api/agents")
    async def get_agents():
        return active_runtime.agents.list_profiles()

    @application.get("/api/agent-types")
    async def get_agent_types():
        return active_runtime.adapter_definitions()

    @application.get("/api/providers")
    async def get_providers():
        if active_runtime.providers is None:
            return {"providers": [], "defaults": [], "integrations": []}
        integrations = []
        if active_runtime.client_integrations is not None:
            integrations = [
                active_runtime.client_integrations.status(client)
                for client in ClientKind
            ]
        return {
            "providers": active_runtime.providers.list_providers(),
            "defaults": active_runtime.providers.list_default_routes(),
            "integrations": integrations,
        }

    @application.post("/api/providers", status_code=201)
    async def create_provider(payload: ProviderInput):
        if active_runtime.providers is None:
            raise HTTPException(status_code=503, detail="Provider 控制面未启用。")
        return active_runtime.providers.save_provider(payload)

    @application.put("/api/providers/routes/{client}")
    async def set_default_provider_route(client: ClientKind, payload: DefaultRouteInput):
        if active_runtime.providers is None:
            raise HTTPException(status_code=503, detail="Provider 控制面未启用。")
        try:
            return active_runtime.providers.set_default_route(client, payload)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.put("/api/providers/{provider_id}")
    async def update_provider(provider_id: str, payload: ProviderInput):
        if active_runtime.providers is None:
            raise HTTPException(status_code=503, detail="Provider 控制面未启用。")
        if provider_id != payload.id:
            raise HTTPException(status_code=400, detail="路径 Provider ID 与请求体不一致。")
        if not active_runtime.providers.has_provider(provider_id):
            raise HTTPException(status_code=404, detail="Provider 不存在。")
        return active_runtime.providers.save_provider(payload)

    @application.delete("/api/providers/{provider_id}", status_code=204)
    async def delete_provider(provider_id: str):
        if active_runtime.providers is None:
            raise HTTPException(status_code=503, detail="Provider 控制面未启用。")
        if not active_runtime.providers.delete_provider(provider_id):
            raise HTTPException(status_code=404, detail="Provider 不存在。")

    @application.post("/api/providers/{provider_id}/test")
    async def test_provider(provider_id: str):
        if active_runtime.gateway is None:
            raise HTTPException(status_code=503, detail="Provider Gateway 未启用。")
        try:
            return await active_runtime.gateway.test_provider(provider_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @application.get("/api/clients/integrations")
    async def get_client_integrations():
        if active_runtime.client_integrations is None:
            return []
        return [active_runtime.client_integrations.status(client) for client in ClientKind]

    @application.post("/api/clients/{client}/integration/enable")
    async def enable_client_integration(client: ClientKind):
        if active_runtime.providers is None or active_runtime.client_integrations is None:
            raise HTTPException(status_code=503, detail="客户端配置接管未启用。")
        try:
            route = active_runtime.providers.resolve_route(client)
            return active_runtime.client_integrations.enable(client, route)
        except (ValueError, OSError, ClientConfigChanged, UnsafeClientConfigPath) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.post("/api/clients/{client}/integration/disable")
    async def disable_client_integration(client: ClientKind):
        if active_runtime.client_integrations is None:
            raise HTTPException(status_code=503, detail="客户端配置接管未启用。")
        try:
            return active_runtime.client_integrations.disable(client)
        except (ValueError, OSError, ClientConfigChanged, UnsafeClientConfigPath) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.put("/api/sessions/{session_id}/route")
    async def set_session_route(session_id: str, payload: SessionRouteAction):
        try:
            result = await active_runtime.set_session_route(session_id, payload)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if result is None:
            raise HTTPException(status_code=404, detail="没有找到该会话。")
        return result

    @application.get("/v1/models")
    async def gateway_models():
        if active_runtime.providers is None:
            return {"object": "list", "data": []}
        data = []
        seen: set[str] = set()
        for provider in active_runtime.providers.list_providers():
            if not provider.enabled:
                continue
            for model in provider.models:
                model_id = f"{provider.id}/{model}"
                if model_id not in seen:
                    data.append({"id": model_id, "object": "model", "owned_by": provider.id})
                    seen.add(model_id)
        for route in active_runtime.providers.list_default_routes():
            if route.model not in seen:
                data.append(
                    {
                        "id": route.model,
                        "object": "model",
                        "owned_by": route.provider_id,
                    }
                )
                seen.add(route.model)
        return {"object": "list", "data": data}

    @application.post("/v1/responses")
    async def gateway_responses(request: Request):
        if active_runtime.gateway is None:
            raise HTTPException(status_code=503, detail="Provider Gateway 未启用。")
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象。")
            return await active_runtime.gateway.forward(ClientKind.CODEX, payload, request.headers)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"上游请求失败：{error}") from error

    @application.post("/v1/messages")
    async def gateway_messages(request: Request):
        if active_runtime.gateway is None:
            raise HTTPException(status_code=503, detail="Provider Gateway 未启用。")
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象。")
            return await active_runtime.gateway.forward(ClientKind.CLAUDE_CODE, payload, request.headers)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except httpx.HTTPError as error:
            raise HTTPException(status_code=502, detail=f"上游请求失败：{error}") from error

    @application.get("/api/agents/discover")
    async def discover_agents():
        from agent_hub.agents.discovery import AgentDiscovery
        candidates = AgentDiscovery.discover_all()
        return {"candidates": [c.model_dump() for c in candidates]}

    @application.post("/api/agents", status_code=201)
    async def create_agent(payload: AgentProfileInput):
        try:
            return await active_runtime.create_profile(payload)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @application.put("/api/agents/{agent_id}")
    async def update_agent(agent_id: str, payload: AgentProfilePatch):
        try:
            profile = await active_runtime.update_profile(agent_id, payload)
        except (RuntimeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if profile is None:
            raise HTTPException(status_code=404, detail="没有找到该 Agent Profile。")
        return profile

    @application.delete("/api/agents/{agent_id}", status_code=204)
    async def delete_agent(agent_id: str):
        try:
            deleted = await active_runtime.delete_profile(agent_id)
        except RuntimeError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if not deleted:
            raise HTTPException(status_code=404, detail="没有找到该 Agent Profile。")

    @application.get("/api/tools")
    async def get_tools():
        """旧前端兼容入口；新代码使用 /api/agents。"""
        return active_runtime.agents.list_profiles()

    @application.get("/api/events")
    async def get_events():
        return active_runtime.events.records

    @application.post("/api/agents/{agent_id}/probe")
    async def probe_agent(agent_id: str):
        return await active_runtime.probe_agent(agent_id)

    @application.post("/api/tools/{tool_id}/probe")
    async def probe_tool(tool_id: str):
        """旧前端兼容入口；新代码使用 /api/agents/{agent_id}/probe。"""
        result = await active_runtime.sessions.probe_agent(tool_id)
        payload = result.model_dump()
        payload["tool_id"] = payload.pop("agent_id")
        return payload

    @application.post("/api/sessions/{session_id}/open")
    async def open_session(session_id: str):
        result = await active_runtime.sessions.open_session(session_id)
        if not result.ok and result.action == "none":
            raise HTTPException(status_code=404, detail=result.message)
        return result

    @application.post("/api/sessions/{session_id}/ignore")
    async def ignore_session(session_id: str, ignored: bool = True):
        active_runtime.sessions.set_session_ignored(session_id, ignored)
        return {"ok": True, "session_id": session_id, "ignored": ignored}

    @application.post("/api/sessions/{session_id}/mark-complete")
    async def mark_session_complete(session_id: str):
        # 标记为完成实际上就是忽略该会话
        active_runtime.sessions.set_session_ignored(session_id, True)
        return {"ok": True, "session_id": session_id, "message": "会话已标记为完成"}

    @application.post("/api/sessions/{session_id}/follow-up")
    async def follow_up_session(session_id: str, follow_up: bool = True):
        active_runtime.sessions.set_session_follow_up(session_id, follow_up)
        return {"ok": True, "session_id": session_id, "follow_up": follow_up}

    @application.post("/api/demo/tick")
    async def demo_tick():
        if active_runtime.demo is None:
            raise HTTPException(status_code=404, detail="当前运行时未启用 Demo 控制器。")
        changes = await active_runtime.demo.tick()
        return {
            "ok": True,
            "changes": changes,
            "message": f"模拟探测完成，产生 {len(changes)} 条状态变化。",
        }

    return application


runtime = create_configured_runtime()
app = create_app(runtime)


def open_browser() -> None:
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:17860")


if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=17860,
        reload=False,
        log_level="info",
    )
