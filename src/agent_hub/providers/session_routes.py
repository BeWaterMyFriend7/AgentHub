from __future__ import annotations

import json
import threading
from pathlib import Path

from agent_hub.providers.models import ClientKind, SessionRoute


class SessionRouteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    def get(self, agent_id: str, native_session_id: str) -> SessionRoute | None:
        key = self._key(agent_id, native_session_id)
        item = self._read().get(key)
        return SessionRoute.model_validate(item) if item else None

    def upsert(self, route: SessionRoute) -> SessionRoute:
        self.upsert_many([route])
        return route

    def upsert_many(self, routes: list[SessionRoute]) -> None:
        if not routes:
            return
        with self._lock:
            payload = self._read()
            for route in routes:
                self._remove_same_native(payload, route)
                payload[self._key(route.agent_id, route.native_session_id)] = route.model_dump(mode="json")
            self._write(payload)

    @staticmethod
    def _remove_same_native(payload: dict[str, object], route: SessionRoute) -> None:
        for key, item in list(payload.items()):
            current = SessionRoute.model_validate(item)
            if (
                current.client == route.client
                and current.native_session_id == route.native_session_id
            ):
                del payload[key]

    def find_by_native(self, client: ClientKind, native_session_id: str) -> SessionRoute | None:
        for item in self._read().values():
            route = SessionRoute.model_validate(item)
            if route.client == client and route.native_session_id == native_session_id:
                return route
        return None

    def list_routes(self) -> list[SessionRoute]:
        return [SessionRoute.model_validate(item) for item in self._read().values()]

    def delete_for_session(
        self,
        client: ClientKind,
        agent_id: str,
        native_session_id: str,
    ) -> bool:
        with self._lock:
            payload = self._read()
            keys = []
            for key, item in payload.items():
                route = SessionRoute.model_validate(item)
                if route.client == client and route.native_session_id == native_session_id:
                    keys.append(key)
            exact = self._key(agent_id, native_session_id)
            if exact in payload and exact not in keys:
                keys.append(exact)
            for key in keys:
                del payload[key]
            if keys:
                self._write(payload)
            return bool(keys)

    def delete(self, agent_id: str, native_session_id: str) -> bool:
        with self._lock:
            payload = self._read()
            key = self._key(agent_id, native_session_id)
            if key not in payload:
                return False
            del payload[key]
            self._write(payload)
            return True

    def _read(self) -> dict[str, object]:
        if not self.path.is_file():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        routes = payload.get("routes", {}) if isinstance(payload, dict) else {}
        if not isinstance(routes, dict):
            raise ValueError("Session Route Store 格式无效。")
        return routes

    def _write(self, routes: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": 1, "routes": routes}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _key(agent_id: str, native_session_id: str) -> str:
        return f"{agent_id}\u001f{native_session_id}"
