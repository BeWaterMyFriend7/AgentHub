from __future__ import annotations

import argparse
import asyncio
import os
from collections import Counter
from pathlib import Path

from agent_hub.bootstrap import create_codex_runtime
from agent_hub.sessions.models import SessionStatus


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证本机 Codex Desktop 任务发现与状态检测。")
    parser.add_argument(
        "--codex-home",
        default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")),
        help="Codex 本地状态目录，默认使用 CODEX_HOME 或 ~/.codex。",
    )
    parser.add_argument("--limit", type=int, default=100, help="最多读取的最近任务数量。")
    parser.add_argument("--open-session", help="可选：验证后用原生 Thread ID 在 Codex Desktop 中定位任务。")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    runtime = create_codex_runtime(codex_home=args.codex_home, session_limit=args.limit)
    profile = runtime.agents.profile_for("codex")
    if profile is None:
        raise RuntimeError("Codex Profile 创建失败。")

    probe = await runtime.sessions.probe_agent("codex")
    print(f"probe_ok={probe.ok}")
    for check in probe.checks:
        print(f"check={check}")
    for failure in probe.failures:
        print(f"failure={failure}")
    if not probe.ok:
        raise SystemExit(1)

    first = await runtime.sessions.list_sessions()
    second = await runtime.sessions.list_sessions()
    first_ids = [item.id for item in first]
    if first_ids != [item.id for item in second]:
        raise RuntimeError("两次扫描返回的 Codex 任务身份不稳定。")
    if len(first) < 3:
        raise RuntimeError("真实验证至少需要三个 Codex 任务。")

    counts = Counter(item.status for item in first)
    print(f"profile={profile.name}")
    print(f"sessions={len(first)} stable_ids=true")
    print("status_counts=" + ",".join(f"{status.value}:{counts[status]}" for status in SessionStatus))
    for session in first[:10]:
        print(
            "session="
            f"{session.native_session_id} status={session.status.value} "
            f"project={session.project_name!r} title={session.title!r}"
        )
        print(f"reason={session.status_reason}")

    if not any(item.status == SessionStatus.EXECUTING for item in first):
        raise RuntimeError("未检测到正在执行的 Codex 任务；请在 Codex 正在回复时重新运行。")
    if not any(item.status == SessionStatus.CLOSED for item in first):
        raise RuntimeError("未检测到带 task_complete 证据的历史任务。")

    if args.open_session:
        result = await runtime.sessions.open_session(f"codex:{args.open_session}")
        print(f"open_ok={result.ok} target={result.resume_target}")
        if not result.ok:
            raise RuntimeError(result.message)


if __name__ == "__main__":
    asyncio.run(main())
