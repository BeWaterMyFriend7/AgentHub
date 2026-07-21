from __future__ import annotations

from datetime import datetime, timezone

from agent_hub.agents.models import AgentProfile, ProbeResult
from agent_hub.sessions.adapters.base import SessionAdapter
from agent_hub.sessions.models import (
    AgentSession,
    OpenSessionResult,
    PlanItem,
    SessionStatus,
)


def now() -> datetime:
    return datetime.now(timezone.utc)


class MockSessionAdapter(SessionAdapter):
    def __init__(self, profile: AgentProfile, sessions: list[AgentSession]) -> None:
        super().__init__(profile)
        self._sessions = sessions
        self._tick = 0

    async def list_sessions(self) -> list[AgentSession]:
        return [item.model_copy(deep=True) for item in self._sessions]

    async def probe(self) -> ProbeResult:
        checks: list[str] = []
        failures: list[str] = []

        if not self.profile.enabled:
            failures.append("Agent Profile 已被禁用。")
        if not self.profile.endpoint.strip():
            failures.append("未配置连接地址或适配器标识。")

        caps = self.profile.capabilities
        if caps.session_discovery:
            checks.append(f"成功列出 {len(self._sessions)} 个内部会话。")
        else:
            failures.append("适配器不支持内部会话发现。")

        if caps.status_detection:
            checks.append("可以读取每个会话的独立状态。")
        else:
            failures.append("无法读取会话级状态。")

        if caps.exact_resume:
            checks.append("支持根据原生会话 ID 精确恢复。")
        else:
            failures.append("无法精确恢复指定内部会话。")

        if caps.plan_reading:
            checks.append("支持读取规划或 Todo。")
        else:
            checks.append("规划读取为有限支持，仅展示最近活动。")

        if failures:
            self.profile.connected = False
            self.profile.last_probe_message = "；".join(failures)
            return ProbeResult(
                ok=False,
                agent_id=self.profile.id,
                title="接入探测失败",
                message=f"{self.profile.name} 尚未达到完整接入标准。",
                checks=checks,
                failures=failures,
            )

        self.profile.connected = True
        self.profile.last_probe_message = "接入能力校验通过"
        return ProbeResult(
            ok=True,
            agent_id=self.profile.id,
            title="接入探测通过",
            message=f"{self.profile.name} 可以完成会话发现、状态读取和精确恢复。",
            checks=checks,
        )

    async def open_session(self, session_id: str) -> OpenSessionResult:
        session = next((item for item in self._sessions if item.id == session_id), None)
        if session is None:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="none",
                message="没有找到该会话。",
            )

        if not self.profile.capabilities.exact_resume:
            return OpenSessionResult(
                ok=False,
                session_id=session_id,
                agent_id=self.profile.id,
                action="open_tool",
                message="该适配器只能打开工具，不能精确进入内部会话。",
                resume_target=self.profile.endpoint,
            )

        return OpenSessionResult(
            ok=True,
            session_id=session_id,
            agent_id=self.profile.id,
            action="resume_session",
            message=f"Demo：已调用 {self.profile.name} 适配器恢复“{session.title}”。",
            resume_target=f"{self.profile.id}://session/{session.native_session_id}",
        )

    async def advance_demo_state(self) -> list[str]:
        """模拟下一轮 Agent 事件探测。

        第一次：
        - 等待授权 -> 执行中
        - 等待输入 -> 执行中
        第二次：
        - 执行中 -> 等待验收
        - 中断会话 -> 执行中（模拟恢复）
        第三次：
        - 等待验收 -> 已关闭（模拟 Agent 上报归档/完成事件）
        """
        self._tick = (self._tick + 1) % 3
        changes: list[str] = []

        for session in self._sessions:
            if self._tick == 1:
                if session.status in {
                    SessionStatus.WAITING_PERMISSION,
                    SessionStatus.WAITING_INPUT,
                }:
                    old = session.status
                    session.status = SessionStatus.EXECUTING
                    session.status_reason = "已检测到用户完成处理，Agent 恢复执行。"
                    session.current_step = "继续执行当前规划"
                    session.last_activity = "收到用户处理事件，继续调用工具。"
                    session.updated_at = now()
                    changes.append(f"{session.title}: {old.value} -> executing")

            elif self._tick == 2:
                if session.status == SessionStatus.EXECUTING:
                    session.status = SessionStatus.AWAITING_REVIEW
                    session.status_reason = "当前轮次执行完成，等待人工验收。"
                    session.current_step = "等待检查结果"
                    session.last_activity = "Agent 正常停止并输出结果摘要。"
                    for item in session.plan_items:
                        if item.status == "current":
                            item.status = "done"
                    session.updated_at = now()
                    changes.append(f"{session.title}: executing -> awaiting_review")
                elif session.status == SessionStatus.INTERRUPTED:
                    session.status = SessionStatus.EXECUTING
                    session.status_reason = "检测到会话恢复并继续执行。"
                    session.current_step = "恢复中断步骤"
                    session.last_activity = "通过原生会话 ID 恢复执行。"
                    session.updated_at = now()
                    changes.append(f"{session.title}: interrupted -> executing")

            else:
                if session.status == SessionStatus.AWAITING_REVIEW:
                    session.status = SessionStatus.CLOSED
                    session.status_reason = "检测到 Agent 上报完成或归档事件。"
                    session.current_step = "已关闭"
                    session.last_activity = "会话已归档。"
                    session.updated_at = now()
                    changes.append(f"{session.title}: awaiting_review -> closed")

        return changes
