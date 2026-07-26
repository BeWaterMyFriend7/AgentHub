from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_hub.agents.models import AgentProfile, SessionIntegrationCapabilities
from agent_hub.sessions.adapters import OpenCodeSessionAdapter
from agent_hub.sessions.models import AgentSession


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证真实 OpenCode 多会话接入能力")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--username", default="opencode")
    parser.add_argument("--executable", default="opencode")
    parser.add_argument("--resume-session", help="可选：实际启动并恢复指定原生会话 ID")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    password = os.getenv("OPENCODE_SERVER_PASSWORD")
    if not password:
        raise SystemExit("请通过 OPENCODE_SERVER_PASSWORD 环境变量提供本地 Server 密码。")

    profile = AgentProfile(
        id="opencode",
        name="OpenCode",
        adapter_type="OpenCode Server API + CLI Resume",
        enabled=True,
        connected=False,
        endpoint=args.endpoint,
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
        username=args.username,
        password=password,
        executable=args.executable,
    )
    try:
        first = await adapter.list_sessions()
        second = await adapter.list_sessions()
        probe = await adapter.probe()
        stable = [item.id for item in first] == [item.id for item in second]
        samples_by_directory: dict[str, AgentSession] = {}
        for session in first:
            directory = session.working_directory or ""
            if not directory:
                continue
            previous = samples_by_directory.get(directory)
            if previous is None or len(session.plan_items) > len(previous.plan_items):
                samples_by_directory[directory] = session
        independent = list(samples_by_directory.values())[:3]

        print(
            f"sessions={len(first)} stable_ids={stable} "
            f"independent_projects={len(independent)} probe_ok={probe.ok}"
        )
        for session in first[:10]:
            print(
                f"{session.native_session_id} | {session.status.value} | "
                f"todos={len(session.plan_items)} | {session.working_directory} | {session.title}"
            )

        print("independent_samples:")
        for session in independent:
            print(
                f"- {session.native_session_id} | {session.status.value} | "
                f"todos={len(session.plan_items)} | {session.working_directory}"
            )

        if len(first) < 3 or len(independent) < 3 or not stable or not probe.ok:
            return 1

        if args.resume_session:
            target = next(
                (item for item in first if item.native_session_id == args.resume_session),
                None,
            )
            if target is None:
                print("指定的原生会话 ID 不在列表中。", file=sys.stderr)
                return 1
            result = await adapter.open_session(target.id)
            print(f"resume_ok={result.ok} target={result.resume_target}")
            return 0 if result.ok else 1
        print("resume=not_requested")
        return 0
    finally:
        await adapter.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
