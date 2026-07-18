import os
import secrets
from skillbridge.config import BACKUP_DIR_NAME

_session_token: str = ""


def generate_session_token() -> str:
    global _session_token
    _session_token = secrets.token_hex(32)
    return _session_token


def get_session_token() -> str:
    return _session_token


def normalize_path(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def is_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    normalized = normalize_path(path)
    for root in allowed_roots:
        norm_root = normalize_path(root)
        if normalized == norm_root or normalized.startswith(norm_root + os.sep):
            return True
    return False


def is_inside_backup_dir(path: str, agent_root: str) -> bool:
    backup_dir = os.path.join(normalize_path(agent_root), BACKUP_DIR_NAME)
    norm_path = normalize_path(path)
    return norm_path.startswith(backup_dir + os.sep)
