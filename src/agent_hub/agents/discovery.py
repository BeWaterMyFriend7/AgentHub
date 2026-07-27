"""Agent 自动探测：发现本地已安装的 Agent。"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class AgentCandidate(BaseModel):
    """Agent 候选配置。"""

    agent_type: Literal["claude_code", "codex", "opencode", "hermes"]
    adapter_kind: str
    name: str
    description: str
    data_path: str | None = None
    endpoint: str | None = None
    executable: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    check_details: list[str] = []


class AgentDiscovery:
    """Agent 自动探测器。"""

    @staticmethod
    def discover_all() -> list[AgentCandidate]:
        """探测所有支持的 Agent。"""
        candidates: list[AgentCandidate] = []
        candidates.extend(AgentDiscovery._discover_claude_code())
        candidates.extend(AgentDiscovery._discover_codex())
        candidates.extend(AgentDiscovery._discover_opencode())
        candidates.extend(AgentDiscovery._discover_hermes())
        return candidates

    @staticmethod
    def _discover_claude_code() -> list[AgentCandidate]:
        """探测 Claude Code Desktop 和 CLI。"""
        candidates: list[AgentCandidate] = []
        system = platform.system()

        # Claude Code Desktop
        if system == "Windows":
            appdata = os.getenv("APPDATA")
            if appdata:
                claude_dir = Path(appdata) / "Claude"
                if claude_dir.exists():
                    candidates.append(
                        AgentCandidate(
                            agent_type="claude_code",
                            adapter_kind="claude_desktop",
                            name="Claude Code Desktop",
                            description="通过本地数据文件读取会话",
                            data_path=str(claude_dir),
                            confidence="high" if (claude_dir / "sessions").exists() else "medium",
                            check_details=[
                                f"发现目录: {claude_dir}",
                                "建议：验证是否存在会话数据",
                            ],
                        )
                    )
        elif system == "Darwin":
            home = Path.home()
            claude_dir = home / "Library" / "Application Support" / "Claude"
            if claude_dir.exists():
                candidates.append(
                    AgentCandidate(
                        agent_type="claude_code",
                        adapter_kind="claude_desktop",
                        name="Claude Code Desktop",
                        description="通过本地数据文件读取会话",
                        data_path=str(claude_dir),
                        confidence="high" if (claude_dir / "sessions").exists() else "medium",
                        check_details=[
                            f"发现目录: {claude_dir}",
                            "建议：验证是否存在会话数据",
                        ],
                    )
                )

        # Claude Code CLI
        claude_cli = shutil.which("claude")
        if claude_cli:
            candidates.append(
                AgentCandidate(
                    agent_type="claude_code",
                    adapter_kind="claude_cli",
                    name="Claude Code CLI",
                    description="通过 CLI 命令行工具",
                    executable=claude_cli,
                    confidence="high",
                    check_details=[f"发现可执行文件: {claude_cli}"],
                )
            )

        return candidates

    @staticmethod
    def _discover_codex() -> list[AgentCandidate]:
        """探测 Codex Desktop。"""
        candidates: list[AgentCandidate] = []
        system = platform.system()

        if system == "Windows":
            appdata = os.getenv("LOCALAPPDATA")
            if appdata:
                codex_dir = Path(appdata) / "Codex"
                state_file = codex_dir / "state_5.sqlite"
                if state_file.exists():
                    candidates.append(
                        AgentCandidate(
                            agent_type="codex",
                            adapter_kind="codex_desktop",
                            name="Codex Desktop",
                            description="通过本地 SQLite 读取会话",
                            data_path=str(codex_dir),
                            confidence="high",
                            check_details=[
                                f"发现数据库: {state_file}",
                                "支持深链恢复: codex://threads/<id>",
                            ],
                        )
                    )
        elif system == "Darwin":
            home = Path.home()
            codex_dir = home / "Library" / "Application Support" / "Codex"
            state_file = codex_dir / "state_5.sqlite"
            if state_file.exists():
                candidates.append(
                    AgentCandidate(
                        agent_type="codex",
                        adapter_kind="codex_desktop",
                        name="Codex Desktop",
                        description="通过本地 SQLite 读取会话",
                        data_path=str(codex_dir),
                        confidence="high",
                        check_details=[
                            f"发现数据库: {state_file}",
                            "支持深链恢复: codex://threads/<id>",
                        ],
                    )
                )

        return candidates

    @staticmethod
    def _discover_opencode() -> list[AgentCandidate]:
        """探测 OpenCode Desktop、CLI 和 Server。"""
        candidates: list[AgentCandidate] = []
        system = platform.system()

        # OpenCode Desktop
        if system == "Windows":
            appdata = os.getenv("LOCALAPPDATA")
            if appdata:
                opencode_dir = Path(appdata) / "OpenCode"
                db_file = opencode_dir / "sessions.db"
                if db_file.exists():
                    candidates.append(
                        AgentCandidate(
                            agent_type="opencode",
                            adapter_kind="opencode_desktop",
                            name="OpenCode Desktop",
                            description="通过本地 SQLite 读取会话",
                            data_path=str(opencode_dir),
                            confidence="high",
                            check_details=[
                                f"发现数据库: {db_file}",
                                "支持 CLI 恢复",
                            ],
                        )
                    )
        elif system == "Darwin":
            home = Path.home()
            opencode_dir = home / "Library" / "Application Support" / "OpenCode"
            db_file = opencode_dir / "sessions.db"
            if db_file.exists():
                candidates.append(
                    AgentCandidate(
                        agent_type="opencode",
                        adapter_kind="opencode_desktop",
                        name="OpenCode Desktop",
                        description="通过本地 SQLite 读取会话",
                        data_path=str(opencode_dir),
                        confidence="high",
                        check_details=[
                            f"发现数据库: {db_file}",
                            "支持 CLI 恢复",
                        ],
                    )
                )

        # OpenCode CLI
        opencode_cli = shutil.which("opencode")
        if opencode_cli:
            candidates.append(
                AgentCandidate(
                    agent_type="opencode",
                    adapter_kind="opencode_cli",
                    name="OpenCode CLI",
                    description="通过 CLI 命令行工具",
                    executable=opencode_cli,
                    confidence="high",
                    check_details=[f"发现可执行文件: {opencode_cli}"],
                )
            )

        # OpenCode Server (需要手动配置)
        candidates.append(
            AgentCandidate(
                agent_type="opencode",
                adapter_kind="opencode_server",
                name="OpenCode Server",
                description="通过 Server API 访问（需手动配置地址和密码）",
                endpoint="http://127.0.0.1:4096",
                confidence="low",
                check_details=[
                    "默认端口: 4096",
                    "需要配置密码环境变量",
                ],
            )
        )

        return candidates

    @staticmethod
    def _discover_hermes() -> list[AgentCandidate]:
        """探测 Hermes Desktop 和 CLI。"""
        candidates: list[AgentCandidate] = []
        system = platform.system()

        # Hermes Desktop
        if system == "Windows":
            appdata = os.getenv("LOCALAPPDATA")
            if appdata:
                hermes_dir = Path(appdata) / "Hermes"
                if hermes_dir.exists():
                    candidates.append(
                        AgentCandidate(
                            agent_type="hermes",
                            adapter_kind="hermes_desktop",
                            name="Hermes Desktop",
                            description="通过本地数据文件读取会话",
                            data_path=str(hermes_dir),
                            confidence="medium",
                            check_details=[f"发现目录: {hermes_dir}"],
                        )
                    )
        elif system == "Darwin":
            home = Path.home()
            hermes_dir = home / "Library" / "Application Support" / "Hermes"
            if hermes_dir.exists():
                candidates.append(
                    AgentCandidate(
                        agent_type="hermes",
                        adapter_kind="hermes_desktop",
                        name="Hermes Desktop",
                        description="通过本地数据文件读取会话",
                        data_path=str(hermes_dir),
                        confidence="medium",
                        check_details=[f"发现目录: {hermes_dir}"],
                    )
                )

        # Hermes CLI
        hermes_cli = shutil.which("hermes")
        if hermes_cli:
            candidates.append(
                AgentCandidate(
                    agent_type="hermes",
                    adapter_kind="hermes_cli",
                    name="Hermes CLI",
                    description="通过 CLI 命令行工具",
                    executable=hermes_cli,
                    confidence="high",
                    check_details=[f"发现可执行文件: {hermes_cli}"],
                )
            )

        return candidates
