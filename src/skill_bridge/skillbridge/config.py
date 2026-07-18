import os
from pathlib import Path

APP_NAME = "SkillBridge"
HOST = "127.0.0.1"
PORT = 17890
DB_PATH = Path.home() / ".skillbridge" / "skillbridge.db"
BACKUP_DIR_NAME = "skillbridge-backups"

DEFAULT_AGENTS = [
    {
        "id": "codex",
        "name": "Codex",
        "skill_root": str(Path.home() / ".codex" / "skills"),
        "icon": "codex",
        "enabled": True,
        "ignore_patterns": [".system", ".internal"],
    },
    {
        "id": "opencode",
        "name": "OpenCode",
        "skill_root": str(Path.home() / ".config" / "opencode" / "skills"),
        "icon": "opencode",
        "enabled": True,
        "ignore_patterns": [],
    },
]
