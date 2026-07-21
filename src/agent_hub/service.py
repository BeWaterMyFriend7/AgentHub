"""第一阶段迁移兼容层；新代码使用 sessions.SessionHub。"""

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.agents.registry import AgentRegistry
from agent_hub.repository import Repository
from agent_hub.sessions.hub import SessionHub
from agent_hub.sessions.adapters.base import SessionAdapter


class SessionHubService(SessionHub):
    def __init__(
        self,
        repository: Repository,
        adapters: dict[str, SessionAdapter],
    ) -> None:
        self.repository = repository
        self.adapters = adapters
        self.agent_registry = AgentRegistry(repository.tools.values())
        super().__init__(self.agent_registry, adapters, repository)

    def list_tools(self) -> list[AgentProfile]:
        return self.agent_registry.list_profiles()

    async def probe_tool(self, tool_id: str) -> ProbeResult:
        return await self.probe_agent(tool_id)
