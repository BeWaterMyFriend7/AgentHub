from __future__ import annotations

import asyncio
import httpx
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from agent_hub.adapter_factory import AgentAdapterFactory
from agent_hub.agents import AgentProfileStore, AgentRegistry
from agent_hub.agents.models import (
    AgentProfile,
    AgentProfileInput,
    AgentProfilePatch,
    ProbeResult,
    SessionIntegrationCapabilities,
)
from agent_hub.demo.controller import DemoSessionController
from agent_hub.demo.seed import events as seed_events
from agent_hub.demo.seed import profiles as seed_profiles
from agent_hub.demo.seed import sessions as seed_sessions
from agent_hub.providers.clients import ClientIntegrationManager
from agent_hub.providers.control import ProviderControl
from agent_hub.providers.gateway import ProviderGateway
from agent_hub.providers.models import (
    SessionRouteAction,
    SessionRouteInput,
    SessionRouteView,
    client_for_agent_type,
)
from agent_hub.sessions import SessionEventLog
from agent_hub.sessions.adapters import CodexSessionAdapter, MockSessionAdapter, OpenCodeSessionAdapter
from agent_hub.sessions.hub import SessionHub


@dataclass
class AgentHubRuntime:
    agents: AgentRegistry
    sessions: SessionHub
    events: SessionEventLog
    demo: DemoSessionController | None = None
    closers: tuple[Callable[[], Awaitable[None]], ...] = ()
    profile_store: AgentProfileStore | None = None
    adapter_factory: AgentAdapterFactory | None = None
    providers: ProviderControl | None = None
    client_integrations: ClientIntegrationManager | None = None
    gateway: ProviderGateway | None = None
    _reload_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def aclose(self) -> None:
        close_actions = [close() for close in self.closers]
        if self.gateway is not None:
            close_actions.append(self.gateway.aclose())
        await asyncio.gather(*close_actions)

    async def reload_profiles(self) -> None:
        if self.profile_store is None or self.adapter_factory is None:
            raise RuntimeError("当前 Runtime 不支持 Agent Profile 配置。")
        async with self._reload_lock:
            profiles, adapters, closers = _build_configured_components(
                self.profile_store,
                self.adapter_factory,
            )
            previous_closers = self.closers
            self.agents = AgentRegistry(profiles)
            self.sessions = SessionHub(
                self.agents,
                adapters,
                self.events,
                provider_control=self.providers,
            )
            self.closers = closers
            await asyncio.gather(*(close() for close in previous_closers))

    async def create_profile(self, payload: AgentProfileInput) -> AgentProfile:
        self._require_configuration()
        assert self.profile_store is not None
        assert self.adapter_factory is not None
        if payload.id and any(item.id == payload.id for item in self.profile_store.list_profiles()):
            raise ValueError(f"Agent Profile ID 已存在：{payload.id}")
        profile = self.adapter_factory.create_profile(payload)
        self.profile_store.upsert(profile)
        await self.reload_profiles()
        return self.agents.profile_for(profile.id) or profile

    async def update_profile(self, profile_id: str, patch: AgentProfilePatch) -> AgentProfile | None:
        self._require_configuration()
        assert self.profile_store is not None
        assert self.adapter_factory is not None
        current = next(
            (item for item in self.profile_store.list_profiles() if item.id == profile_id),
            None,
        )
        if current is None:
            return None
        profile = self.adapter_factory.update_profile(current, patch)
        self.profile_store.upsert(profile)
        await self.reload_profiles()
        return self.agents.profile_for(profile_id)

    async def delete_profile(self, profile_id: str) -> bool:
        self._require_configuration()
        assert self.profile_store is not None
        deleted = self.profile_store.delete(profile_id)
        if deleted:
            await self.reload_profiles()
        return deleted

    async def probe_agent(self, profile_id: str) -> ProbeResult:
        result = await self.sessions.probe_agent(profile_id)
        if self.profile_store is not None:
            profile = self.agents.profile_for(profile_id)
            if profile is not None:
                self.profile_store.upsert(profile)
        return result

    async def set_session_route(
        self,
        session_id: str,
        payload: SessionRouteAction,
    ) -> SessionRouteView | None:
        if self.providers is None:
            raise RuntimeError("Provider 控制面未启用。")
        session = next(
            (item for item in await self.sessions.list_sessions() if item.id == session_id),
            None,
        )
        if session is None:
            return None
        profile = self.agents.profile_for(session.agent_id)
        client = client_for_agent_type(profile.agent_type if profile else "")
        if client is None:
            raise ValueError("该 Agent 不支持模型路由绑定。")
        if payload.follow_default:
            self.providers.follow_default(
                client,
                session.agent_id,
                session.native_session_id,
            )
        else:
            if not payload.provider_id or not payload.model:
                raise ValueError("绑定会话需要 provider_id 和 model。")
            self.providers.bind_session(
                SessionRouteInput(
                    client=client,
                    agent_id=session.agent_id,
                    native_session_id=session.native_session_id,
                    provider_id=payload.provider_id,
                    model=payload.model,
                )
            )
        return self.providers.route_view_for_session(
            client,
            session.agent_id,
            session.native_session_id,
        )

    def adapter_definitions(self):
        return self.adapter_factory.definitions() if self.adapter_factory is not None else []

    def _require_configuration(self) -> None:
        if self.profile_store is None or self.adapter_factory is None:
            raise RuntimeError("当前 Runtime 不支持 Agent Profile 配置。")


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


def create_opencode_runtime(
    *,
    endpoint: str,
    password: str,
    username: str = "opencode",
    executable: str = "opencode",
) -> AgentHubRuntime:
    profile = AgentProfile(
        id="opencode",
        name="OpenCode",
        adapter_type="OpenCode Server API + CLI Resume",
        enabled=True,
        connected=False,
        endpoint=endpoint,
        capabilities=SessionIntegrationCapabilities(
            session_discovery=True,
            status_detection=True,
            plan_reading=True,
            exact_resume=False,
            event_stream=False,
            resume_launch=True,
        ),
        status_source="OpenCode Server API polling",
    )
    adapter = OpenCodeSessionAdapter(
        profile,
        username=username,
        password=password,
        executable=executable,
    )
    agents = AgentRegistry([profile])
    events = SessionEventLog()
    sessions = SessionHub(agents, {profile.id: adapter}, events)
    return AgentHubRuntime(
        agents=agents,
        sessions=sessions,
        events=events,
        closers=(adapter.aclose,),
    )


def create_codex_runtime(
    *,
    codex_home: str | None = None,
    session_limit: int = 100,
) -> AgentHubRuntime:
    profile = AgentProfile(
        id="codex",
        name="Codex",
        adapter_type="Codex local state + Desktop deep link",
        enabled=True,
        connected=False,
        endpoint=codex_home or "local://codex",
        capabilities=SessionIntegrationCapabilities(
            session_discovery=True,
            status_detection=True,
            plan_reading=True,
            exact_resume=True,
            event_stream=False,
            resume_launch=True,
        ),
        status_source="Codex local state polling",
    )
    adapter = CodexSessionAdapter(profile, codex_home=codex_home, session_limit=session_limit)
    agents = AgentRegistry([profile])
    events = SessionEventLog()
    sessions = SessionHub(agents, {profile.id: adapter}, events)
    return AgentHubRuntime(agents=agents, sessions=sessions, events=events)


def create_configured_runtime(
    config_path: str | Path | None = None,
    *,
    data_dir: str | Path | None = None,
    codex_config_path: str | Path | None = None,
    claude_settings_path: str | Path | None = None,
    proxy_base_url: str = "http://127.0.0.1:17860",
    allow_user_config_writes: bool | None = None,
    gateway_transport: httpx.AsyncBaseTransport | None = None,
) -> AgentHubRuntime:
    store = AgentProfileStore(config_path)
    factory = AgentAdapterFactory()
    profiles, adapters, closers = _build_configured_components(store, factory)
    agents = AgentRegistry(profiles)
    events = SessionEventLog()
    root = Path(data_dir).expanduser() if data_dir else store.path.parent
    providers = ProviderControl.from_paths(
        registry_path=root / "providers.json",
        session_routes_path=root / "session-routes.json",
    )
    sessions = SessionHub(
        agents,
        adapters,
        events,
        provider_control=providers,
    )
    integrations = ClientIntegrationManager(
        data_dir=root,
        codex_config_path=codex_config_path,
        claude_settings_path=claude_settings_path,
        proxy_base_url=proxy_base_url,
        allow_user_config_writes=(
            store.path.absolute() == (Path.home() / ".agenthub" / "agents.json").absolute()
            if allow_user_config_writes is None
            else allow_user_config_writes
        ),
    )
    gateway = ProviderGateway(providers, transport=gateway_transport)
    return AgentHubRuntime(
        agents=agents,
        sessions=sessions,
        events=events,
        closers=closers,
        profile_store=store,
        adapter_factory=factory,
        providers=providers,
        client_integrations=integrations,
        gateway=gateway,
    )


def _build_configured_components(
    store: AgentProfileStore,
    factory: AgentAdapterFactory,
) -> tuple[
    list[AgentProfile],
    dict[str, object],
    tuple[Callable[[], Awaitable[None]], ...],
]:
    profiles = store.list_profiles()
    adapters = {}
    closers: list[Callable[[], Awaitable[None]]] = []
    for profile in profiles:
        profile.connected = False
        if not profile.enabled:
            profile.last_probe_message = "Profile 已停用"
            continue
        try:
            adapter = factory.build(profile)
        except (OSError, ValueError) as error:
            failure = str(error)
            if profile.last_probe_message != "尚未探测":
                failure = f"{profile.last_probe_message}；{failure}"
            profile.last_probe_message = failure
            continue
        adapters[profile.id] = adapter
        close = getattr(adapter, "aclose", None)
        if callable(close):
            closers.append(close)
    return profiles, adapters, tuple(closers)
