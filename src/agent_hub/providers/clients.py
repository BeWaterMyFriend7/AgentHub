from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import tomli
import tomli_w

from agent_hub.providers.models import ClientIntegrationStatus, ClientKind, ResolvedRoute


class UnsafeClientConfigPath(RuntimeError):
    pass


class ClientConfigChanged(RuntimeError):
    pass


class ClientIntegrationManager:
    def __init__(
        self,
        *,
        data_dir: str | Path,
        codex_config_path: str | Path | None = None,
        claude_settings_path: str | Path | None = None,
        proxy_base_url: str = "http://127.0.0.1:17860",
        allow_user_config_writes: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser()
        self.codex_config_path = Path(
            codex_config_path or Path.home() / ".codex" / "config.toml"
        ).expanduser()
        self.claude_settings_path = Path(
            claude_settings_path or Path.home() / ".claude" / "settings.json"
        ).expanduser()
        self.proxy_base_url = proxy_base_url.rstrip("/")
        self.allow_user_config_writes = allow_user_config_writes
        self._lock = threading.RLock()

    def enable(self, client: ClientKind, route: ResolvedRoute) -> ClientIntegrationStatus:
        with self._lock:
            path = self._path_for(client)
            self._guard(path)
            journal_path = self._journal_path(client)
            path_existed = path.is_file()
            current = path.read_bytes() if path_existed else b""
            journal = self._read_journal(client)
            if journal:
                if self._sha256(current) != journal["injected_sha256"]:
                    raise ClientConfigChanged("客户端配置在 AgentHub 接管后被外部修改，请先手工确认。")
                backup_path = journal.get("backup_path")
                original_exists = bool(journal.get("original_exists"))
            else:
                original_exists = path_existed
                backup_path = self._backup(client, current) if original_exists else None

            transformed = self._transform(client, current, route)
            try:
                self._atomic_write(path, transformed)
                self._write_json_atomic(
                    journal_path,
                    {
                        "version": 1,
                        "client": client.value,
                        "config_path": str(path),
                        "original_exists": original_exists,
                        "backup_path": str(backup_path) if backup_path else None,
                        "injected_sha256": self._sha256(transformed),
                        "enabled_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception:
                if path_existed:
                    self._atomic_write(path, current)
                else:
                    path.unlink(missing_ok=True)
                raise
            return self.status(client)

    def disable(self, client: ClientKind) -> ClientIntegrationStatus:
        with self._lock:
            path = self._path_for(client)
            self._guard(path)
            journal = self._read_journal(client)
            if journal is None:
                return self.status(client)
            current = path.read_bytes() if path.is_file() else b""
            if self._sha256(current) != journal["injected_sha256"]:
                raise ClientConfigChanged("客户端配置已被外部修改，AgentHub 拒绝覆盖这些新改动。")

            backup = journal.get("backup_path")
            if journal.get("original_exists"):
                if not backup or not Path(backup).is_file():
                    raise FileNotFoundError("找不到客户端配置备份，已停止恢复。")
                self._atomic_write(path, Path(backup).read_bytes())
            elif path.exists():
                path.unlink()
            self._journal_path(client).unlink(missing_ok=True)
            return self.status(client)

    def status(self, client: ClientKind) -> ClientIntegrationStatus:
        with self._lock:
            return self._status_unlocked(client)

    def _status_unlocked(self, client: ClientKind) -> ClientIntegrationStatus:
        path = self._path_for(client)
        journal = self._read_journal(client)
        if journal is None:
            return ClientIntegrationStatus(
                client=client,
                active=False,
                config_path=str(path),
                message="未启用 AgentHub 模型代理。",
            )
        current = path.read_bytes() if path.is_file() else b""
        changed = self._sha256(current) != journal.get("injected_sha256")
        return ClientIntegrationStatus(
            client=client,
            active=not changed,
            config_path=str(path),
            changed_externally=changed,
            message=(
                "配置接管有效。重启客户端后生效。"
                if not changed
                else "配置接管后发生外部改动，已暂停自动恢复。"
            ),
        )

    def _transform(self, client: ClientKind, current: bytes, route: ResolvedRoute) -> bytes:
        if client == ClientKind.CODEX:
            payload = tomli.loads(current.decode("utf-8")) if current else {}
            payload["model_provider"] = "openai"
            payload["openai_base_url"] = f"{self.proxy_base_url}/v1"
            payload["model"] = route.model
            return tomli_w.dumps(payload).encode("utf-8")

        payload = json.loads(current.decode("utf-8")) if current else {}
        if not isinstance(payload, dict):
            raise ValueError("Claude Code settings.json 必须是 JSON 对象。")
        environment = payload.setdefault("env", {})
        if not isinstance(environment, dict):
            raise ValueError("Claude Code settings.json 的 env 必须是对象。")
        environment.update(
            {
                "ANTHROPIC_BASE_URL": self.proxy_base_url,
                "ANTHROPIC_AUTH_TOKEN": "agenthub-local",
                "ANTHROPIC_MODEL": route.model,
            }
        )
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def _backup(self, client: ClientKind, content: bytes) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        suffix = ".toml" if client == ClientKind.CODEX else ".json"
        path = self.data_dir / "backups" / client.value / f"config-{timestamp}{suffix}"
        self._atomic_write(path, content)
        return path

    def _read_journal(self, client: ClientKind) -> dict[str, object] | None:
        path = self._journal_path(client)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("客户端接管 journal 格式无效。")
        return payload

    def _path_for(self, client: ClientKind) -> Path:
        return self.codex_config_path if client == ClientKind.CODEX else self.claude_settings_path

    def _journal_path(self, client: ClientKind) -> Path:
        return self.data_dir / "client-integrations" / f"{client.value}.json"

    def _guard(self, path: Path) -> None:
        if self.allow_user_config_writes:
            return
        home = Path.home()
        lexical = path.absolute()
        resolved = path.resolve()
        inside_home = False
        for candidate, root in ((lexical, home.absolute()), (resolved, home.resolve())):
            try:
                candidate.relative_to(root)
                inside_home = True
            except ValueError:
                continue
        if not inside_home:
            return
        raise UnsafeClientConfigPath(
            "未显式授权写入真实用户配置；测试必须注入临时配置路径。"
        )

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, path)

    @classmethod
    def _write_json_atomic(cls, path: Path, payload: dict[str, object]) -> None:
        cls._atomic_write(
            path,
            (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
