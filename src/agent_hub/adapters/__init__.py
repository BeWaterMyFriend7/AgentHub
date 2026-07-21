"""兼容旧导入路径；新代码使用 agent_hub.sessions.adapters。"""

from agent_hub.adapters.base import AgentAdapter
from agent_hub.adapters.mock import MockAgentAdapter

__all__ = ["AgentAdapter", "MockAgentAdapter"]
