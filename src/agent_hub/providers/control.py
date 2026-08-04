from __future__ import annotations

import os
import re
import threading
from pathlib import Path

from agent_hub.providers.models import (
    ClientKind,
    DefaultRoute,
    DefaultRouteInput,
    ProviderInput,
    ProviderProfile,
    ProviderView,
    ResolvedRoute,
    SessionRoute,
    SessionRouteInput,
    SessionRouteView,
)
from agent_hub.providers.registry import ProviderRegistry
from agent_hub.providers.secrets import SecretStore
from agent_hub.providers.session_routes import SessionRouteStore


class ProviderControl:
    def __init__(
        self,
        registry: ProviderRegistry,
        session_routes: SessionRouteStore,
        secrets: SecretStore | None = None,
    ) -> None:
        self._registry = registry
        self._session_routes = session_routes
        self._secrets = secrets or SecretStore(registry.path.parent / "secrets.json")
        self._save_lock = threading.RLock()

    @classmethod
    def from_paths(
        cls,
        *,
        registry_path: str | Path,
        session_routes_path: str | Path,
        secrets_path: str | Path | None = None,
    ) -> "ProviderControl":
        root = Path(registry_path).expanduser().parent
        return cls(
            ProviderRegistry(registry_path),
            SessionRouteStore(session_routes_path),
            SecretStore(secrets_path or root / "secrets.json"),
        )

    def list_providers(self) -> list[ProviderView]:
        return [self._view(item) for item in self._registry.list_providers()]

    def get_provider(self, provider_id: str) -> ProviderProfile | None:
        """Return a provider profile without exposing the persistence repository."""
        return self._registry.get(provider_id)

    def save_provider(self, payload: ProviderInput) -> ProviderView:
        with self._save_lock:
            values = payload.model_dump(exclude={"api_key"})
            provider_id = values["id"] or self._generate_provider_id(values["name"])
            values["id"] = provider_id
            profile = ProviderProfile.model_validate(values)
            if payload.api_key and payload.api_key.strip():
                self._secrets.save(provider_id, payload.api_key)
            return self._view(self._registry.upsert(profile))

    def delete_provider(self, provider_id: str) -> bool:
        deleted = self._registry.delete(provider_id)
        if deleted:
            self._secrets.delete(provider_id)
        return deleted

    def api_key_stored(self, provider_id: str) -> bool:
        return self._secrets.has(provider_id)

    def refresh_models(self, provider_id: str, models: list[str]) -> ProviderView:
        provider = self._require_provider(provider_id)
        updated = provider.model_copy(
            update={
                "models": models,
                "hidden_models": [
                    model for model in provider.hidden_models if model in models
                ],
            }
        )
        return self._view(self._registry.upsert(updated))

    def set_model_visibility(
        self,
        provider_id: str,
        model: str,
        visible: bool,
    ) -> ProviderView:
        provider = self._require_provider(provider_id)
        hidden = set(provider.hidden_models)
        if visible:
            hidden.discard(model)
        elif model in provider.models:
            hidden.add(model)
        updated = provider.model_copy(update={"hidden_models": sorted(hidden)})
        return self._view(self._registry.upsert(updated))

    def has_provider(self, provider_id: str) -> bool:
        return self._registry.get(provider_id) is not None

    def list_default_routes(self) -> list[DefaultRoute]:
        return self._registry.list_defaults()

    def set_default_route(self, client: ClientKind, payload: DefaultRouteInput) -> DefaultRoute:
        provider = self._require_provider(payload.provider_id)
        self._validate_model(provider, payload.model)
        return self._registry.set_default(
            DefaultRoute(client=client, provider_id=provider.id, model=payload.model)
        )

    def bind_session(self, payload: SessionRouteInput, *, source: str = "manual") -> SessionRoute:
        provider = self._require_provider(payload.provider_id)
        self._validate_model(provider, payload.model)
        return self._session_routes.upsert(
            SessionRoute(**payload.model_dump(), source=source, mode="fixed")
        )

    def follow_default(
        self,
        client: ClientKind,
        agent_id: str,
        native_session_id: str,
    ) -> bool:
        default = self._registry.default_for(client)
        if default is None:
            raise ValueError(f"尚未配置 {client.value} 的默认模型路由。")
        self._session_routes.upsert(
            SessionRoute(
                client=client,
                agent_id=agent_id,
                native_session_id=native_session_id,
                provider_id=default.provider_id,
                model=default.model,
                source="manual",
                mode="follow_default",
            )
        )
        return True

    def route_view_for_session(
        self,
        client: ClientKind,
        agent_id: str,
        native_session_id: str,
    ) -> SessionRouteView:
        bound = self._session_routes.get(agent_id, native_session_id)
        if bound is None:
            bound = self._session_routes.find_by_native(client, native_session_id)
        if bound and bound.mode == "fixed":
            return SessionRouteView(
                provider_id=bound.provider_id,
                model=bound.model,
                source="session",
                follows_default=False,
            )
        if bound and bound.mode == "unresolved":
            return SessionRouteView(source="unbound", follows_default=False)
        default = self._registry.default_for(client)
        if default:
            return SessionRouteView(
                provider_id=default.provider_id,
                model=default.model,
                source="default",
                follows_default=True,
            )
        return SessionRouteView()

    def route_views_for_sessions(
        self,
        client: ClientKind,
        sessions: list[tuple[str, str]],
    ) -> dict[tuple[str, str], SessionRouteView]:
        routes = self._session_routes.list_routes()
        default = self._registry.default_for(client)
        result: dict[tuple[str, str], SessionRouteView] = {}
        for agent_id, native_session_id in sessions:
            bound = next(
                (
                    route
                    for route in routes
                    if route.client == client
                    and route.native_session_id == native_session_id
                    and route.agent_id == agent_id
                ),
                None,
            ) or next(
                (
                    route
                    for route in routes
                    if route.client == client and route.native_session_id == native_session_id
                ),
                None,
            )
            if bound and bound.mode == "fixed":
                result[(agent_id, native_session_id)] = SessionRouteView(
                    provider_id=bound.provider_id,
                    model=bound.model,
                    source="session",
                    follows_default=False,
                )
            elif bound and bound.mode == "unresolved":
                result[(agent_id, native_session_id)] = SessionRouteView(
                    source="unbound",
                    follows_default=False,
                )
            elif default:
                result[(agent_id, native_session_id)] = SessionRouteView(
                    provider_id=default.provider_id,
                    model=default.model,
                    source="default",
                    follows_default=True,
                )
            else:
                result[(agent_id, native_session_id)] = SessionRouteView()
        return result

    def register_existing_sessions(
        self,
        client: ClientKind,
        sessions: list[tuple[str, str]],
    ) -> None:
        known = {
            (route.client, route.native_session_id)
            for route in self._session_routes.list_routes()
        }
        discovered = [
            SessionRoute(
                client=client,
                agent_id=agent_id,
                native_session_id=native_session_id,
                provider_id="",
                model="",
                source="discovered",
                mode="unresolved",
            )
            for agent_id, native_session_id in sessions
            if (client, native_session_id) not in known
        ]
        self._session_routes.upsert_many(discovered)

    def resolve_route(
        self,
        client: ClientKind,
        *,
        requested_model: str | None = None,
        agent_id: str | None = None,
        native_session_id: str | None = None,
    ) -> ResolvedRoute:
        if agent_id and native_session_id:
            route = self._session_routes.get(agent_id, native_session_id)
            if route is None:
                route = self._session_routes.find_by_native(client, native_session_id)
            if route and route.mode == "unresolved":
                raise ValueError(
                    "历史会话的原模型路由尚未确认，请先在 AgentHub 会话页选择 Provider/模型，或明确设为跟随默认。"
                )
            if route and route.mode == "follow_default":
                route = None
            if route:
                return ResolvedRoute(
                    provider=self._require_enabled_provider(route.provider_id),
                    model=route.model,
                    source="session",
                )

        explicit = self._parse_explicit_model(client, requested_model)
        if explicit:
            provider_id, model = explicit
            provider = self._require_enabled_provider(provider_id)
            self._validate_model(provider, model)
            return ResolvedRoute(provider=provider, model=model, source="explicit")

        default = self._registry.default_for(client)
        if default is None:
            raise ValueError(f"尚未配置 {client.value} 的默认模型路由。")
        return ResolvedRoute(
            provider=self._require_enabled_provider(default.provider_id),
            model=default.model,
            source="default",
        )

    def record_observed_route(
        self,
        *,
        client: ClientKind,
        agent_id: str,
        native_session_id: str,
        provider_id: str,
        model: str,
    ) -> SessionRoute:
        current = self._session_routes.find_by_native(client, native_session_id)
        if current is not None:
            return current
        return self.bind_session(
            SessionRouteInput(
                client=client,
                agent_id=agent_id,
                native_session_id=native_session_id,
                provider_id=provider_id,
                model=model,
            ),
            source="observed",
        )

    def credential_for(self, provider: ProviderProfile) -> str | None:
        stored = self._secrets.get(provider.id)
        if stored:
            return stored
        return os.environ.get(provider.secret_env) if provider.secret_env else None

    def find_session_route(
        self,
        client: ClientKind,
        native_session_id: str,
    ) -> SessionRoute | None:
        """Look up an observed route through the control-plane interface."""
        return self._session_routes.find_by_native(client, native_session_id)

    def _require_provider(self, provider_id: str) -> ProviderProfile:
        provider = self._registry.get(provider_id)
        if provider is None:
            raise ValueError(f"Provider 不存在：{provider_id}")
        return provider

    def _require_enabled_provider(self, provider_id: str) -> ProviderProfile:
        provider = self._require_provider(provider_id)
        if not provider.enabled:
            raise ValueError(f"Provider 已停用：{provider_id}")
        return provider

    @staticmethod
    def _validate_model(provider: ProviderProfile, model: str) -> None:
        if provider.models and model not in provider.models:
            raise ValueError(f"Provider {provider.id} 未声明模型：{model}")

    def _parse_explicit_model(
        self,
        client: ClientKind,
        requested_model: str | None,
    ) -> tuple[str, str] | None:
        if not requested_model or "/" not in requested_model:
            return None
        provider_id, model = requested_model.split("/", 1)
        if not provider_id or not model:
            return None
        if self._registry.get(provider_id) is None:
            default = self._registry.default_for(client)
            default_provider = self._registry.get(default.provider_id) if default else None
            declared_plain_model = bool(
                default
                and default_provider
                and (
                    requested_model == default.model
                    or requested_model in default_provider.models
                )
            )
            if declared_plain_model:
                return None
            raise ValueError(f"显式路由引用了不存在的 Provider：{provider_id}")
        return provider_id, model

    def _view(self, provider: ProviderProfile) -> ProviderView:
        return ProviderView(
            **provider.model_dump(exclude={"api_key"}),
            credential_available=bool(self.credential_for(provider)),
            api_key_stored=self._secrets.has(provider.id),
        )

    def _generate_provider_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "provider"
        existing = {item.id for item in self._registry.list_providers()}
        candidate = base
        suffix = 2
        while candidate in existing:
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate
