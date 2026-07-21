"""兼容旧导入路径。"""

from agent_hub.agents.models import AgentProfile
from agent_hub.sessions.adapters.base import SessionAdapter


class AgentAdapter(SessionAdapter):
    @property
    def tool(self) -> AgentProfile:
        """旧调用方的兼容名称；新代码统一使用 profile。"""
        return self.profile

__all__ = ["AgentAdapter"]
