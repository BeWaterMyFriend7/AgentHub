from __future__ import annotations

import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_hub.agents.models import AgentProfileInput, AgentProfilePatch
from agent_hub.bootstrap import AgentHubRuntime, create_configured_runtime

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def create_app(runtime: AgentHubRuntime | None = None) -> FastAPI:
    active_runtime = runtime or create_configured_runtime()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await active_runtime.aclose()

    application = FastAPI(
        title="Agent Session Hub MVP",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
        "agent_hub.main:app",
        host="127.0.0.1",
        port=17860,
        reload=False,
        log_level="info",
    )
