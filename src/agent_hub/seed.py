"""第一阶段迁移兼容层；Demo 数据位于 agent_hub.demo.seed。"""

from agent_hub.demo.seed import dt, events, profiles, sessions


def tools():
    return profiles()


__all__ = ["dt", "events", "sessions", "tools"]
