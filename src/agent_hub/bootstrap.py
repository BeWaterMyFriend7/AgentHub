from __future__ import annotations

from dataclasses import dataclass

from agent_hub.agents import AgentRegistry
from agent_hub.demo.controller import DemoSessionController
from agent_hub.demo.seed import events as seed_events
from agent_hub.demo.seed import profiles as seed_profiles
from agent_hub.demo.seed import sessions as seed_sessions
from agent_hub.sessions import SessionEventLog
from agent_hub.sessions.adapters import MockSessionAdapter
from agent_hub.sessions.hub import SessionHub


@dataclass(frozen=True)
class AgentHubRuntime:
    agents: AgentRegistry
    sessions: SessionHub
    events: SessionEventLog
    demo: DemoSessionController | None = None


def create_demo_runtime() -> AgentHubRuntime:
    profiles = seed_profiles()
    session_map = seed_sessions()
    adapters = {
        profile.id: MockSessionAdapter(profile, session_map.get(profile.id, []))
        for profile in profiles
    }
    agents = AgentRegistry(profiles)
    events = SessionEventLog(seed_events())
    sessions = SessionHub(agents, adapters, events)
    demo = DemoSessionController(adapters, events)
    return AgentHubRuntime(agents=agents, sessions=sessions, events=events, demo=demo)
