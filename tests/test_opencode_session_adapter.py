from __future__ import annotations

import unittest
import sys
import tempfile
from pathlib import Path

import httpx

from agent_hub.agents.models import AgentProfile, SessionIntegrationCapabilities
from agent_hub.sessions.adapters.opencode import OpenCodeSessionAdapter
from agent_hub.sessions.models import SessionStatus
from tests.test_session_adapter_contract import assert_session_adapter_contract


def profile() -> AgentProfile:
    return AgentProfile(
        id="opencode",
        name="OpenCode",
        adapter_type="OpenCode Server API + CLI Resume",
        enabled=True,
        connected=False,
        endpoint="http://127.0.0.1:4096",
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


class OpenCodeSessionAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.launched: list[tuple[list[str], dict[str, str]]] = []
        self.fail_todo_for: str | None = None
        self.fail_status = False

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/global/health":
                return httpx.Response(200, json={"healthy": True, "version": "1.18.4"})
            if request.url.path == "/api/session":
                return httpx.Response(200, json={"data": self._native_sessions(), "cursor": {}})
            if request.url.path.startswith("/api/session/ses_"):
                native_id = request.url.path.rsplit("/", 1)[-1]
                native = next(item for item in self._native_sessions() if item["id"] == native_id)
                return httpx.Response(200, json={"data": native})
            if request.url.path == "/api/session/active":
                if self.fail_status:
                    return httpx.Response(503)
                return httpx.Response(200, json={"data": {"ses_running": {"type": "running"}}})
            if request.url.path == "/session/status":
                if self.fail_status:
                    return httpx.Response(503)
                return httpx.Response(200, json={})
            if request.url.path.endswith("/todo"):
                native_id = request.url.path.split("/")[2]
                if native_id == self.fail_todo_for:
                    return httpx.Response(404)
                return httpx.Response(
                    200,
                    json=[
                        {"content": f"完成接口 {native_id}", "status": "completed", "priority": "high"},
                        {"content": f"运行测试 {native_id}", "status": "in_progress", "priority": "high"},
                        {"content": f"取消旧方案 {native_id}", "status": "cancelled", "priority": "low"},
                    ],
                )
            if request.url.path.endswith("/message"):
                native_id = request.url.path.split("/")[2]
                return httpx.Response(
                    200,
                    json=[{"parts": [{"type": "text", "text": f"正在运行测试 {native_id}"}]}],
                )
            return httpx.Response(404)

        self.client = httpx.AsyncClient(
            base_url="http://127.0.0.1:4096",
            transport=httpx.MockTransport(handler),
        )
        self.adapter = OpenCodeSessionAdapter(
            profile(),
            password="secret",
            executable=sys.executable,
            client=self.client,
            resume_launcher=lambda command, env: self.launched.append((command, dict(env))),
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _native_sessions() -> list[dict[str, object]]:
        return [
            {
                "id": native_id,
                "title": title,
                "location": {"directory": rf"D:\Projects\{native_id}"},
                "time": {"updated": 1_784_000_000_000 + index},
            }
            for index, (native_id, title) in enumerate(
                [("ses_running", "运行会话"), ("ses_idle", "空闲会话"), ("ses_other", "历史会话")]
            )
        ]

    async def test_maps_multiple_sessions_status_todos_and_activity(self) -> None:
        sessions = await self.adapter.list_sessions()

        self.assertEqual(len(sessions), 3)
        self.assertEqual(sessions[0].id, "opencode:ses_running")
        self.assertEqual(sessions[0].status, SessionStatus.EXECUTING)
        self.assertEqual(
            [item.status for item in sessions[0].plan_items],
            ["done", "current", "cancelled"],
        )
        self.assertEqual(sessions[0].last_activity, "正在运行测试 ses_running")
        self.assertEqual(sessions[1].status, SessionStatus.UNKNOWN)
        self.assertNotEqual(sessions[0].plan_items[0].title, sessions[1].plan_items[0].title)

    async def test_repeated_scan_keeps_stable_identity(self) -> None:
        first = await self.adapter.list_sessions()
        second = await self.adapter.list_sessions()

        self.assertEqual([item.id for item in first], [item.id for item in second])

    async def test_resume_launch_uses_native_id_without_password_in_command(self) -> None:
        result = await self.adapter.open_session("opencode:ses_running")

        self.assertTrue(result.ok)
        command, env = self.launched[0]
        self.assertIn("ses_running", command)
        self.assertNotIn("secret", command)
        self.assertEqual(env["OPENCODE_SERVER_PASSWORD"], "secret")
        self.assertNotIn("secret", result.resume_target or "")

    async def test_probe_validates_three_sessions_and_todo_support(self) -> None:
        result = await self.adapter.probe()

        self.assertTrue(result.ok)
        self.assertTrue(self.adapter.profile.connected)
        self.assertTrue(any("3 个内部会话" in item for item in result.checks))

    async def test_implements_shared_adapter_contract(self) -> None:
        await assert_session_adapter_contract(self, self.adapter)

    async def test_one_missing_todo_does_not_hide_other_sessions(self) -> None:
        self.fail_todo_for = "ses_idle"

        sessions = await self.adapter.list_sessions()

        self.assertEqual(len(sessions), 3)
        idle = next(item for item in sessions if item.native_session_id == "ses_idle")
        self.assertEqual(idle.plan_items, [])

    async def test_status_transport_failure_is_not_reported_as_inactive(self) -> None:
        self.fail_status = True

        sessions = await self.adapter.list_sessions()

        idle = next(item for item in sessions if item.native_session_id == "ses_idle")
        self.assertEqual(idle.status, SessionStatus.UNKNOWN)
        self.assertEqual(idle.confidence, "low")
        self.assertIn("暂时不可用", idle.status_reason)

    def test_windows_npm_shim_resolves_to_native_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "opencode.cmd"
            launcher.write_text("@echo off\n", encoding="ascii")
            native = Path(directory) / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
            native.parent.mkdir(parents=True)
            native.write_bytes(b"")

            command = OpenCodeSessionAdapter._resolve_command_prefix(str(launcher))

        self.assertEqual(command, [str(native)])

    def test_unrecognized_script_shim_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "opencode.cmd"
            launcher.write_text("@echo off\n", encoding="ascii")

            command = OpenCodeSessionAdapter._resolve_command_prefix(str(launcher))

        self.assertEqual(command, [])


if __name__ == "__main__":
    unittest.main()
