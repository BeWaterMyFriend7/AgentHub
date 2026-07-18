from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent_hub.adapters import MockAgentAdapter
from agent_hub.repository import Repository
from agent_hub.seed import sessions as seed_sessions
from agent_hub.seed import tools as seed_tools
from agent_hub.service import SessionHubService

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

tool_list = seed_tools()
session_map = seed_sessions()
repository = Repository(tool_list)
adapters = {
    tool.id: MockAgentAdapter(tool, session_map.get(tool.id, []))
    for tool in tool_list
}
service = SessionHubService(repository, adapters)

app = FastAPI(title="Agent Session Hub MVP", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/summary")
async def get_summary():
    return await service.summary()


@app.get("/api/sessions")
async def get_sessions():
    return await service.list_sessions()


@app.get("/api/attention")
async def get_attention():
    return await service.attention_sessions()


@app.get("/api/tools")
async def get_tools():
    return service.list_tools()


@app.get("/api/events")
async def get_events():
    return repository.events


@app.post("/api/tools/{tool_id}/probe")
async def probe_tool(tool_id: str):
    return await service.probe_tool(tool_id)


@app.post("/api/sessions/{session_id}/open")
async def open_session(session_id: str):
    result = await service.open_session(session_id)
    if not result.ok and result.action == "none":
        raise HTTPException(status_code=404, detail=result.message)
    return result


@app.post("/api/demo/tick")
async def demo_tick():
    changes = await service.advance_demo()
    return {
        "ok": True,
        "changes": changes,
        "message": f"模拟探测完成，产生 {len(changes)} 条状态变化。",
    }


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
