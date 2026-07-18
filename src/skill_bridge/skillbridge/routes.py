import os
import sys
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from skillbridge.config import DEFAULT_AGENTS
from skillbridge.database import init_db, get_all_agents, get_enabled_agents, upsert_agent, delete_agent, clear_scan_cache, insert_scan_cache, get_scan_cache, get_source_selection, upsert_source_selection, get_operations
from skillbridge.models import AgentConfig, AgentCreate, AgentUpdate
from skillbridge.scanner import scan_agent_skills
from skillbridge.catalog import build_skill_matrix
from skillbridge.sharing import enable_sharing, disable_sharing, rollback_operation, migrate_source
from skillbridge.security import generate_session_token, get_session_token

app = FastAPI(title="SkillBridge")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def _state_label(state: str) -> str:
    return {
        "SOURCE_LOCAL": "源",
        "SHARED_LINK": "已共享",
        "MISSING": "未启用",
        "LOCAL_COPY": "本地副本",
        "CONFLICT": "冲突",
        "BROKEN_LINK": "断链",
        "INVALID": "无效",
    }.get(state, state)


def _state_icon(state: str) -> str:
    return {
        "SOURCE_LOCAL": "\U0001f512",
        "SHARED_LINK": "\u2713",
        "MISSING": "\u25cb",
        "LOCAL_COPY": "\u25cf",
        "CONFLICT": "!",
        "BROKEN_LINK": "\u2717",
        "INVALID": "\u2298",
    }.get(state, "?")


def _state_class(state: str) -> str:
    return {
        "SOURCE_LOCAL": "state-source",
        "SHARED_LINK": "state-shared",
        "MISSING": "state-missing",
        "LOCAL_COPY": "state-local-copy",
        "CONFLICT": "state-conflict",
        "BROKEN_LINK": "state-broken",
        "INVALID": "state-invalid",
    }.get(state, "")


def _to_agent_configs(agents: list[dict]) -> list[AgentConfig]:
    return [AgentConfig(**a) for a in agents]


class SessionTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE"):
            token = request.headers.get("x-session-token", "")
            if not token or token != get_session_token():
                return JSONResponse(status_code=403, content={"success": False, "error": "Invalid session token"})
        return await call_next(request)


app.add_middleware(SessionTokenMiddleware)


def _agent_icon(icon_name: str) -> str:
    return {
        "codex": "\u26a1",
        "opencode": "\u25c6",
        "claude": "\u25c8",
        "custom": "\u25a3",
    }.get(icon_name, "\u25a3")


@app.on_event("startup")
async def startup():
    generate_session_token()
    init_db()
    if not get_all_agents():
        for agent in DEFAULT_AGENTS:
            upsert_agent(agent)


def _refresh_scan_cache():
    try:
        agents = get_enabled_agents()
        all_skills = []
        for agent in agents:
            try:
                skills = scan_agent_skills(agent["id"], agent["skill_root"],
                                           agent.get("ignore_patterns", []))
                all_skills.extend(skills)
            except Exception:
                pass
        clear_scan_cache()
        insert_scan_cache(all_skills)
    except Exception:
        pass


# HTML Pages


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    agents_list = _to_agent_configs(get_enabled_agents())
    scan_data = get_scan_cache()
    matrix = build_skill_matrix(agents_list, scan_data) if scan_data else build_skill_matrix(agents_list, [])
    token = get_session_token()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "matrix": matrix,
        "state_label": _state_label,
        "state_icon": _state_icon,
        "state_class": _state_class,
        "agent_icon": _agent_icon,
        "session_token": token,
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    agents_list = get_all_agents()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "agents": agents_list,
        "session_token": get_session_token(),
    })


@app.get("/skills/{skill_name}", response_class=HTMLResponse)
async def skill_detail_page(request: Request, skill_name: str):
    agents_list = _to_agent_configs(get_enabled_agents())
    scan_data = get_scan_cache()
    if not scan_data:
        return HTMLResponse("No scan data. Please run scan first.", status_code=400)
    matrix = build_skill_matrix(agents_list, scan_data)
    skill = next((s for s in matrix.skills if s.skill_name == skill_name), None)
    if not skill:
        return HTMLResponse("Skill not found", status_code=404)
    return templates.TemplateResponse("skill_detail.html", {
        "request": request,
        "skill": skill,
        "state_label": _state_label,
        "state_icon": _state_icon,
        "state_class": _state_class,
        "agent_icon": _agent_icon,
        "session_token": get_session_token(),
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    ops = get_operations()
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "operations": ops,
    })


# JSON API


@app.get("/api/agents")
async def api_get_agents():
    return get_all_agents()


@app.post("/api/agents")
async def api_create_agent(agent: AgentCreate):
    upsert_agent(agent.model_dump())
    return {"success": True, "agent_id": agent.id}


@app.put("/api/agents/{agent_id}")
async def api_update_agent(agent_id: str, update: AgentUpdate):
    agents_list = get_all_agents()
    existing = next((a for a in agents_list if a["id"] == agent_id), None)
    if not existing:
        raise HTTPException(status_code=404, detail="Agent not found")
    merged = {**existing, **update.model_dump(exclude_none=True)}
    upsert_agent(merged)
    return {"success": True}


@app.delete("/api/agents/{agent_id}")
async def api_delete_agent(agent_id: str):
    delete_agent(agent_id)
    return {"success": True}


@app.post("/api/scan")
async def api_scan():
    agents_list = get_enabled_agents()
    if not agents_list:
        return {"success": False, "message": "No enabled agents configured"}
    all_skills = []
    errors = []
    for agent in agents_list:
        from skillbridge.scanner import check_directory_available
        ok, err_msg = check_directory_available(agent["skill_root"])
        if not ok:
            errors.append(f"{agent['id']}: {err_msg} ({agent['skill_root']})")
            continue
        try:
            skills = scan_agent_skills(agent["id"], agent["skill_root"],
                                       agent.get("ignore_patterns", []))
            all_skills.extend(skills)
        except Exception as e:
            errors.append(f"{agent['id']}: {str(e)}")
    clear_scan_cache()
    insert_scan_cache(all_skills)
    return {
        "success": True,
        "message": f"Scanned {len(all_skills)} skills across {len(agents_list)} agents",
        "skill_count": len(all_skills),
        "errors": errors,
    }


@app.get("/api/skills")
async def api_get_skills():
    agents_list = _to_agent_configs(get_enabled_agents())
    scan_data = get_scan_cache()
    if not scan_data:
        return {"skills": [], "agents": [a.model_dump() for a in agents_list]}
    matrix = build_skill_matrix(agents_list, scan_data)
    return matrix.model_dump()


@app.get("/api/skills/{skill_name}")
async def api_get_skill_detail(skill_name: str):
    agents_list = _to_agent_configs(get_enabled_agents())
    scan_data = get_scan_cache()
    if not scan_data:
        raise HTTPException(status_code=404, detail="No scan data")
    matrix = build_skill_matrix(agents_list, scan_data)
    skill = next((s for s in matrix.skills if s.skill_name == skill_name), None)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill.model_dump()


@app.post("/api/skills/{skill_name}/share")
async def api_enable_share(skill_name: str, request: Request):
    body = await request.json()
    target_agent_id = body.get("agent_id")
    if not target_agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")

    agents_list = get_all_agents()
    target_agent = next((a for a in agents_list if a["id"] == target_agent_id), None)
    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    source = get_source_selection(skill_name)
    if not source:
        raise HTTPException(status_code=400, detail=f"No source selected for skill '{skill_name}'. Run scan first.")

    result = enable_sharing(skill_name, source["source_path"], target_agent["skill_root"], target_agent_id)
    _refresh_scan_cache()
    return result


@app.delete("/api/skills/{skill_name}/share/{agent_id}")
async def api_disable_share(skill_name: str, agent_id: str):
    agents_list = get_all_agents()
    target_agent = next((a for a in agents_list if a["id"] == agent_id), None)
    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    source = get_source_selection(skill_name)
    source_path = source["source_path"] if source else ""

    result = disable_sharing(skill_name, source_path, target_agent["skill_root"], agent_id)
    _refresh_scan_cache()
    return result


@app.post("/api/skills/{skill_name}/source")
async def api_set_source(skill_name: str, request: Request):
    body = await request.json()
    agent_id = body.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id required")

    agents_list = get_enabled_agents()
    scan_data = get_scan_cache()
    if not scan_data:
        raise HTTPException(status_code=400, detail="No scan data. Run scan first.")

    target_instances = [s for s in scan_data if s["skill_name"] == skill_name and s["agent_id"] == agent_id]
    if not target_instances:
        raise HTTPException(status_code=404, detail=f"No instance found for skill '{skill_name}' on agent '{agent_id}'")

    instance = target_instances[0]
    if instance["entry_type"] != "REAL_DIR":
        raise HTTPException(status_code=400, detail="Can only set source to a real directory")

    result = migrate_source(skill_name, agent_id, instance["path"])
    _refresh_scan_cache()
    return result


@app.post("/api/skills/batch/share")
async def api_batch_enable_share(request: Request):
    body = await request.json()
    skill_names = body.get("skill_names", [])
    target_agent_id = body.get("agent_id")
    if not target_agent_id or not skill_names:
        raise HTTPException(status_code=400, detail="agent_id and skill_names required")

    agents_list = get_all_agents()
    target_agent = next((a for a in agents_list if a["id"] == target_agent_id), None)
    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    results = []
    for name in skill_names:
        source = get_source_selection(name)
        if not source:
            results.append({"skill": name, "success": False, "error": "No source selected"})
            continue
        result = enable_sharing(name, source["source_path"], target_agent["skill_root"], target_agent_id)
        results.append({"skill": name, "success": result.get("success", False), "message": result.get("error") or result.get("message", "")})

    _refresh_scan_cache()
    return {"success": True, "results": results}


@app.post("/api/skills/batch/unshare")
async def api_batch_disable_share(request: Request):
    body = await request.json()
    skill_names = body.get("skill_names", [])
    target_agent_id = body.get("agent_id")
    if not target_agent_id or not skill_names:
        raise HTTPException(status_code=400, detail="agent_id and skill_names required")

    agents_list = get_all_agents()
    target_agent = next((a for a in agents_list if a["id"] == target_agent_id), None)
    if not target_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    results = []
    for name in skill_names:
        source = get_source_selection(name)
        source_path = source["source_path"] if source else ""
        result = disable_sharing(name, source_path, target_agent["skill_root"], target_agent_id)
        results.append({"skill": name, "success": result.get("success", False), "message": result.get("error") or result.get("message", "")})

    _refresh_scan_cache()
    return {"success": True, "results": results}


@app.get("/api/browse")
async def api_browse(path: str = ""):
    try:
        if not path:
            if os.name == "nt":
                import string
                roots = sorted([f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")])
            else:
                roots = ["/"]
            return {"roots": roots}

        if not os.path.isdir(path):
            return {"path": path, "exists": False, "subdirs": [], "parent": os.path.dirname(path) if path else ""}
        subdirs = sorted([
            d for d in os.listdir(path)
            if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")
        ])
        parent = os.path.dirname(path) if path else ""
        # Don't go above root (e.g. C:\ has no parent, / has no parent)
        if parent == path:
            parent = ""
        return {"path": path, "exists": True, "subdirs": subdirs, "parent": parent}
    except PermissionError:
        return {"path": path, "error": "无权限访问", "subdirs": [], "parent": os.path.dirname(path) if path else ""}
    except Exception as e:
        return {"path": path, "error": str(e), "subdirs": [], "parent": os.path.dirname(path) if path else ""}


@app.post("/api/pick-folder")
async def api_pick_folder():
    try:
        if sys.platform == "darwin":
            script = 'tell application "System Events" to choose folder with prompt "Select a skill directory"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            folder = stdout.decode("utf-8", errors="replace").strip().rstrip(":")
        else:
            def _pick():
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                folder = filedialog.askdirectory(title="选择 Skill 目录")
                root.destroy()
                return folder or ""
            folder = await asyncio.to_thread(_pick)
        return {"path": folder}
    except Exception as e:
        return {"path": "", "error": str(e)}


@app.get("/api/operations")
async def api_get_operations():
    return get_operations()


@app.post("/api/operations/{op_id}/rollback")
async def api_rollback_operation(op_id: int):
    return rollback_operation(op_id)
