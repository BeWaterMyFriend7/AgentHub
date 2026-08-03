from __future__ import annotations

import json
import threading
from pathlib import Path

from agent_hub.providers.models import ClientKind, DefaultRoute, ProviderProfile


class ProviderRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    def list_providers(self) -> list[ProviderProfile]:
        payload = self._read()
        return [ProviderProfile.model_validate(item) for item in payload["providers"]]

    def get(self, provider_id: str) -> ProviderProfile | None:
        return next((item for item in self.list_providers() if item.id == provider_id), None)

    def upsert(self, provider: ProviderProfile) -> ProviderProfile:
        with self._lock:
            payload = self._read()
            providers = [ProviderProfile.model_validate(item) for item in payload["providers"]]
            for index, current in enumerate(providers):
                if current.id == provider.id:
                    providers[index] = provider
                    break
            else:
                providers.append(provider)
            payload["providers"] = [item.model_dump(mode="json") for item in providers]
            self._write(payload)
        return provider

    def delete(self, provider_id: str) -> bool:
        with self._lock:
            payload = self._read()
            providers = [item for item in payload["providers"] if item.get("id") != provider_id]
            if len(providers) == len(payload["providers"]):
                return False
            payload["providers"] = providers
            payload["defaults"] = {
                client: route
                for client, route in payload["defaults"].items()
                if route.get("provider_id") != provider_id
            }
            self._write(payload)
            return True

    def list_defaults(self) -> list[DefaultRoute]:
        payload = self._read()
        return [
            DefaultRoute(client=ClientKind(client), **route)
            for client, route in payload["defaults"].items()
        ]

    def default_for(self, client: ClientKind) -> DefaultRoute | None:
        return next((route for route in self.list_defaults() if route.client == client), None)

    def set_default(self, route: DefaultRoute) -> DefaultRoute:
        with self._lock:
            payload = self._read()
            payload["defaults"][route.client.value] = route.model_dump(
                mode="json", exclude={"client"}
            )
            self._write(payload)
        return route

    def _read(self) -> dict[str, object]:
        if not self.path.is_file():
            return {"version": 1, "providers": [], "defaults": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Provider Registry 格式无效。")
        providers = payload.get("providers", [])
        defaults = payload.get("defaults", {})
        if not isinstance(providers, list) or not isinstance(defaults, dict):
            raise ValueError("Provider Registry 缺少 providers 或 defaults。")
        return {"version": 1, "providers": providers, "defaults": defaults}

    def _write(self, payload: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
