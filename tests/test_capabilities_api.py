from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from agent_hub.agents import AgentRegistry
from agent_hub.bootstrap import AgentHubRuntime
from agent_hub.capabilities.inventory import CapabilityInventory
from agent_hub.capabilities.models import CapabilityLocation, CapabilityType
from agent_hub.capabilities.service import SkillShareService
from agent_hub.demo.seed import events as seed_events
from agent_hub.demo.seed import profiles as seed_profiles
from agent_hub.demo.seed import sessions as seed_sessions
from agent_hub.main import create_app
from agent_hub.operations.audit import InMemoryAuditLog
from agent_hub.operations.manager import CapabilityOperationManager
from agent_hub.platform.links import (
    DirectoryEntryKind,
    current_directory_link_adapter,
)
from agent_hub.sessions import SessionEventLog
from agent_hub.sessions.adapters import MockSessionAdapter
from agent_hub.sessions.hub import SessionHub


class SkillShareApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.source_root = root / "agents" / "codex" / "skills"
        self.target_root = root / "agents" / "claude" / "skills"
        self.source_root.mkdir(parents=True)
        self.target_root.mkdir(parents=True)
        skill_dir = self.source_root / "demo-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: 演示 Skill\n---\n",
            encoding="utf-8",
        )
        self.locations = [
            CapabilityLocation(
                agent_id="codex",
                agent_name="Codex",
                capability_type=CapabilityType.SKILL,
                root=self.source_root,
            ),
            CapabilityLocation(
                agent_id="claude_code",
                agent_name="Claude Code",
                capability_type=CapabilityType.SKILL,
                root=self.target_root,
            ),
        ]
        adapter = current_directory_link_adapter()
        self.runtime = self._runtime_with_service(
            adapter,
            root / "backups",
        )
        self.client = TestClient(create_app(self.runtime))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def _runtime_with_service(
        self,
        adapter,
        backup_root: Path,
    ) -> AgentHubRuntime:
        profiles = seed_profiles()
        session_map = seed_sessions()
        adapters = {
            profile.id: MockSessionAdapter(profile, session_map.get(profile.id, []))
            for profile in profiles
        }
        agents = AgentRegistry(profiles)
        events = SessionEventLog(seed_events())
        sessions = SessionHub(agents, adapters, events)
        runtime = AgentHubRuntime(agents=agents, sessions=sessions, events=events)
        runtime.capability_locations = self.locations
        runtime.skill_service = SkillShareService(
            CapabilityInventory(adapter),
            CapabilityOperationManager(
                link_adapter=adapter,
                audit_log=InMemoryAuditLog(),
                allowed_roots=[location.root for location in self.locations],
                protected_roots=[location.root for location in self.locations],
                backup_root=backup_root,
            ),
            self.locations,
        )
        return runtime

    def _skill_by_name(self, payload: dict) -> dict:
        return next(
            item for item in payload["capabilities"] if item["name"] == "demo-skill"
        )

    def test_matrix_reports_source_and_missing_installations(self) -> None:
        response = self.client.get("/api/skills")

        self.assertEqual(response.status_code, 200)
        capability = self._skill_by_name(response.json())
        installations = {
            item["agent_id"]: item for item in capability["installations"]
        }
        self.assertEqual(installations["codex"]["state"], "source")
        self.assertEqual(installations["claude_code"]["state"], "missing")

    def test_share_plan_confirm_and_unshare_flow(self) -> None:
        plan = self.client.post(
            "/api/skills/demo-skill/plan",
            json={"agent_id": "claude_code", "operation_type": "share"},
        )
        self.assertEqual(plan.status_code, 200, plan.text)
        plan_body = plan.json()
        self.assertTrue(plan_body["ready"])
        self.assertEqual(plan_body["confirmation_type"], "installation_change")
        self.assertIn(
            "create_directory_link",
            [step["step_type"] for step in plan_body["steps"]],
        )

        result = self.client.post(
            "/api/skills/confirm",
            json={
                "plan_id": plan_body["id"],
                "confirmation_type": plan_body["confirmation_type"],
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["status"], "succeeded")
        self.assertEqual(
            current_directory_link_adapter()
            .inspect(self.target_root / "demo-skill")
            .kind,
            DirectoryEntryKind.DIRECTORY_LINK,
        )

        matrix = self.client.get("/api/skills").json()
        installations = {
            item["agent_id"]: item
            for item in self._skill_by_name(matrix)["installations"]
        }
        self.assertEqual(installations["claude_code"]["state"], "shared")

        again = self.client.post(
            "/api/skills/demo-skill/plan",
            json={"agent_id": "claude_code", "operation_type": "share"},
        )
        self.assertTrue(again.json()["ready"])
        self.assertEqual(again.json()["steps"], [])

        unshare_plan = self.client.post(
            "/api/skills/demo-skill/plan",
            json={"agent_id": "claude_code", "operation_type": "unshare"},
        )
        unshare_result = self.client.post(
            "/api/skills/confirm",
            json={
                "plan_id": unshare_plan.json()["id"],
                "confirmation_type": unshare_plan.json()["confirmation_type"],
            },
        )
        self.assertEqual(unshare_result.json()["status"], "succeeded")
        self.assertFalse((self.target_root / "demo-skill").exists())

    def test_plan_rejects_unknown_agent(self) -> None:
        response = self.client.post(
            "/api/skills/demo-skill/plan",
            json={"agent_id": "missing-agent", "operation_type": "share"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持的 Agent", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
