from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class ClientKind(StrEnum):
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


def client_for_agent_type(agent_type: str) -> ClientKind | None:
    if agent_type == "codex":
        return ClientKind.CODEX
    if agent_type == "claude_code":
        return ClientKind.CLAUDE_CODE
    return None


class ProviderProtocol(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"


class ProviderInput(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=120)
    protocol: ProviderProtocol
    base_url: str
    secret_env: str = ""
    models: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Provider Base URL 必须是 http 或 https 地址。")
        return normalized

    @field_validator("models")
    @classmethod
    def normalize_models(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            model = value.strip()
            if model and model not in result:
                result.append(model)
        return result


class ProviderProfile(ProviderInput):
    pass


class ProviderView(ProviderProfile):
    credential_available: bool = False


class DefaultRouteInput(BaseModel):
    provider_id: str
    model: str = Field(min_length=1)


class DefaultRoute(DefaultRouteInput):
    client: ClientKind


class SessionRouteInput(BaseModel):
    client: ClientKind
    agent_id: str
    native_session_id: str
    provider_id: str
    model: str = Field(min_length=1)


class SessionRouteAction(BaseModel):
    provider_id: str | None = None
    model: str | None = None
    follow_default: bool = False


class SessionRoute(SessionRouteInput):
    provider_id: str = ""
    model: str = ""
    source: Literal["manual", "observed", "discovered"] = "manual"
    mode: Literal["fixed", "follow_default", "unresolved"] = "fixed"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionRouteView(BaseModel):
    provider_id: str | None = None
    model: str | None = None
    source: Literal["session", "default", "unbound"] = "unbound"
    follows_default: bool = True


class ClientIntegrationStatus(BaseModel):
    client: ClientKind
    active: bool
    config_path: str
    changed_externally: bool = False
    message: str


class ProviderHealth(BaseModel):
    ok: bool
    provider_id: str
    message: str
    models: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class ResolvedRoute:
    provider: ProviderProfile
    model: str
    source: Literal["session", "explicit", "default"]
