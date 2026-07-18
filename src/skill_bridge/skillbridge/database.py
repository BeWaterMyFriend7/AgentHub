import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path
from skillbridge.config import DB_PATH


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(str(get_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                skill_root TEXT NOT NULL,
                icon TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                ignore_patterns TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS scan_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                path TEXT NOT NULL,
                entry_type TEXT NOT NULL,
                resolved_target TEXT DEFAULT '',
                fingerprint TEXT DEFAULT '',
                state TEXT DEFAULT 'UNKNOWN',
                validation_errors TEXT DEFAULT '[]',
                has_skill_md INTEGER DEFAULT 0,
                description TEXT DEFAULT '',
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS source_selections (
                skill_name TEXT PRIMARY KEY,
                source_agent_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                skill_name TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                details TEXT DEFAULT '{}',
                backup_path TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                finished_at TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_scan_cache_agent ON scan_cache(agent_id);
            CREATE INDEX IF NOT EXISTS idx_scan_cache_name ON scan_cache(skill_name);
            CREATE INDEX IF NOT EXISTS idx_operations_action ON operations(action);
        """)


def _parse_agent(row: dict) -> dict:
    row["ignore_patterns"] = json.loads(row.get("ignore_patterns", "[]"))
    row["enabled"] = bool(row.get("enabled", 1))
    return row


def get_all_agents():
    with get_db() as db:
        rows = db.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [_parse_agent(dict(r)) for r in rows]


def get_enabled_agents():
    with get_db() as db:
        rows = db.execute("SELECT * FROM agents WHERE enabled=1 ORDER BY name").fetchall()
        return [_parse_agent(dict(r)) for r in rows]


def upsert_agent(agent: dict):
    with get_db() as db:
        db.execute("""
            INSERT INTO agents (id, name, skill_root, icon, enabled, ignore_patterns, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                skill_root=excluded.skill_root,
                icon=excluded.icon,
                enabled=excluded.enabled,
                ignore_patterns=excluded.ignore_patterns,
                updated_at=excluded.updated_at
        """, (agent["id"], agent["name"], agent["skill_root"], agent.get("icon", ""),
              agent.get("enabled", 1), json.dumps(agent.get("ignore_patterns", []))))


def delete_agent(agent_id: str):
    with get_db() as db:
        db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))


def clear_scan_cache():
    with get_db() as db:
        db.execute("DELETE FROM scan_cache")


def insert_scan_cache(entries: list[dict]):
    with get_db() as db:
        for e in entries:
            db.execute("""
                INSERT INTO scan_cache (agent_id, skill_name, path, entry_type, resolved_target, fingerprint, state, validation_errors, has_skill_md, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (e["agent_id"], e["skill_name"], e["path"], e["entry_type"],
                  e.get("resolved_target", ""), e.get("fingerprint", ""),
                  e.get("state", "UNKNOWN"), json.dumps(e.get("validation_errors", [])),
                  e.get("has_skill_md", 0), e.get("description", "")))


def get_scan_cache():
    with get_db() as db:
        rows = db.execute("SELECT * FROM scan_cache").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["validation_errors"] = json.loads(d.get("validation_errors", "[]"))
            result.append(d)
        return result


def get_source_selection(skill_name: str):
    with get_db() as db:
        row = db.execute("SELECT * FROM source_selections WHERE skill_name = ?", (skill_name,)).fetchone()
        return dict(row) if row else None


def upsert_source_selection(skill_name: str, agent_id: str, source_path: str):
    with get_db() as db:
        db.execute("""
            INSERT INTO source_selections (skill_name, source_agent_id, source_path, created_at)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(skill_name) DO UPDATE SET
                source_agent_id=excluded.source_agent_id,
                source_path=excluded.source_path,
                created_at=excluded.created_at
        """, (skill_name, agent_id, source_path))


def log_operation(action: str, skill_name: str, agent_id: str, status: str = "PENDING",
                  details: dict = None, backup_path: str = "", error: str = "") -> int:
    with get_db() as db:
        cur = db.execute("""
            INSERT INTO operations (action, skill_name, agent_id, status, details, backup_path, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (action, skill_name, agent_id, status, json.dumps(details or {}), backup_path, error))
        return cur.lastrowid


def update_operation_status(op_id: int, status: str, error: str = ""):
    with get_db() as db:
        db.execute("""
            UPDATE operations SET status=?, error=?, finished_at=datetime('now', 'localtime')
            WHERE id=?
        """, (status, error, op_id))


def get_operations(limit: int = 100):
    with get_db() as db:
        rows = db.execute("SELECT * FROM operations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d.get("details", "{}"))
            result.append(d)
        return result
