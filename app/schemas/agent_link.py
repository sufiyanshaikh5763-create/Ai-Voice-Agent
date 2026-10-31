from datetime import datetime
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AgentStatus
from app.utils.validators import normalize_phone


def _normalize_e164(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_phone(value)
    if not normalized.startswith("+"):
        raise ValueError("Phone number must use E.164 format, including the leading +")
    if not re.fullmatch(r"\+[1-9]\d{6,14}", normalized):
        raise ValueError("Phone number must be a valid E.164 number")
    return normalized


class AdminAgentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=150)
    provider: str = Field(default="sarvam", min_length=1, max_length=50)
    provider_agent_id: str | None = Field(default=None, max_length=255)
    phone_number: str | None = None
    description: str | None = Field(default=None, max_length=2000)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _normalize_e164(value)

    @field_validator("provider_agent_id")
    @classmethod
    def _provider_agent_id(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("Provider agent id cannot be blank")
        return value


class AdminAgentUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=150)
    provider: str | None = Field(default=None, min_length=1, max_length=50)
    provider_agent_id: str | None = Field(default=None, max_length=255)
    phone_number: str | None = None
    status: AgentStatus | None = None

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _normalize_e164(value)

    @field_validator("provider_agent_id")
    @classmethod
    def _provider_agent_id(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("Provider agent id cannot be blank")
        return value

    @model_validator(mode="after")
    def _required_values_cannot_be_cleared(self) -> "AdminAgentUpdate":
        for field in ("name", "provider", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class LinkedAgentItem(BaseModel):
    id: int
    name: str
    provider: str
    provider_agent_id: str | None
    phone_number: str | None
    status: AgentStatus


class ClientIntegrationOut(BaseModel):
    signed_event_webhook_url: str
    tool_url_patterns: dict[str, str]
    urls_are_absolute: bool
    credential_exists: bool
    credential_created_at: datetime | None
    credential_rotated_at: datetime | None
    credential_last_used_at: datetime | None
    agents: list[LinkedAgentItem]


class ClientToolTokenOut(BaseModel):
    token: str
    tool_urls: dict[str, str]
    urls_are_absolute: bool
