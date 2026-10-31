"""Super-admin agent linking and lifecycle operations."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (BadRequestError, ConflictError, NotFoundError)
from app.models.agent import Agent
from app.models.client import Client
from app.models.enums import AgentStatus
from app.models.user import User
from app.repositories.agent_repository import get_by_provider_ref
from app.schemas.agent_link import AdminAgentCreate, AdminAgentUpdate
from app.services.audit_service import record_audit
from app.utils.validators import normalize_phone


class AdminAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _phone_key(value: str) -> str:
        return "".join(character for character in value if character.isdigit())

    def _phone_in_use(self, phone_number: str, exclude_id: int | None = None) -> bool:
        key = self._phone_key(phone_number)
        agents = self.db.scalars(
            select(Agent).where(Agent.phone_number.is_not(None))
        ).all()
        for agent in agents:
            if agent.id == exclude_id:
                continue
            try:
                existing = normalize_phone(agent.phone_number)
            except ValueError:
                continue
            if self._phone_key(existing) == key:
                return True
        return False

    def _raise_agent_conflict(self, exc: IntegrityError) -> None:
        diag = getattr(exc.orig, "diag", None)
        constraint = getattr(diag, "constraint_name", "") or str(exc.orig)
        if "uq_agents_phone_number" in constraint:
            raise ConflictError(
                "This phone number is already linked to an agent",
                error_code="PHONE_IN_USE",
            ) from exc
        if "uq_agents_provider_ref" in constraint:
            raise ConflictError(
                "This provider agent id is already linked to an agent",
                error_code="AGENT_ID_IN_USE",
            ) from exc
        raise exc

    def _commit_agent(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            self._raise_agent_conflict(exc)

    def _flush_agent(self) -> None:
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            self._raise_agent_conflict(exc)

    def create(
        self, client_id: int, data: AdminAgentCreate, actor: User, ip: str | None,
    ) -> Agent:
        client = self.db.get(Client, client_id)
        if client is None:
            raise NotFoundError("Client not found", error_code="CLIENT_NOT_FOUND")
        if data.provider_agent_id and get_by_provider_ref(
            self.db, data.provider, data.provider_agent_id
        ):
            raise ConflictError(
                "This provider agent id is already linked to an agent",
                error_code="AGENT_ID_IN_USE",
            )
        if data.phone_number and self._phone_in_use(data.phone_number):
            raise ConflictError(
                "This phone number is already linked to an agent",
                error_code="PHONE_IN_USE",
            )

        agent = Agent(
            client_id=client_id,
            name=data.name,
            provider=data.provider,
            provider_agent_id=data.provider_agent_id,
            phone_number=data.phone_number,
            description=data.description,
            configuration=data.configuration,
            status=AgentStatus.ACTIVE,
            is_active=True,
        )
        self.db.add(agent)
        self._flush_agent()
        record_audit(
            self.db, "admin.agent.link", user_id=actor.id, client_id=client_id,
            entity_type="agent", entity_id=agent.id,
            details={"fields": [
                "client_id", "configuration", "description", "is_active", "name",
                "phone_number", "provider", "provider_agent_id", "status",
            ]},
            ip_address=ip,
        )
        self._commit_agent()
        self.db.refresh(agent)
        return agent

    def update(
        self, agent_id: int, data: AdminAgentUpdate, actor: User, ip: str | None,
    ) -> Agent:
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent not found", error_code="AGENT_NOT_FOUND")
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise BadRequestError("Provide at least one field to update",
                                  error_code="NO_FIELDS_TO_UPDATE")

        provider = changes.get("provider", agent.provider)
        provider_agent_id = changes.get("provider_agent_id", agent.provider_agent_id)
        if provider_agent_id and (provider, provider_agent_id) != (
            agent.provider, agent.provider_agent_id
        ) and get_by_provider_ref(self.db, provider, provider_agent_id, exclude_id=agent.id):
            raise ConflictError(
                "This provider agent id is already linked to an agent",
                error_code="AGENT_ID_IN_USE",
            )
        phone_number = changes.get("phone_number", agent.phone_number)
        if phone_number and phone_number != agent.phone_number and self._phone_in_use(
            phone_number, exclude_id=agent.id
        ):
            raise ConflictError(
                "This phone number is already linked to an agent",
                error_code="PHONE_IN_USE",
            )

        for field, value in changes.items():
            setattr(agent, field, value)
        if "status" in changes:
            agent.is_active = changes["status"] == AgentStatus.ACTIVE
        record_audit(
            self.db, "admin.agent.update", user_id=actor.id, client_id=agent.client_id,
            entity_type="agent", entity_id=agent.id,
            details={"fields": sorted(
                set(changes) | ({"is_active"} if "status" in changes else set())
            )},
            ip_address=ip,
        )
        self._commit_agent()
        self.db.refresh(agent)
        return agent

    def unlink(self, agent_id: int, actor: User, ip: str | None) -> Agent:
        agent = self.db.get(Agent, agent_id)
        if agent is None:
            raise NotFoundError("Agent not found", error_code="AGENT_NOT_FOUND")
        changed = []
        if agent.status != AgentStatus.INACTIVE:
            agent.status = AgentStatus.INACTIVE
            changed.append("status")
        if agent.is_active:
            agent.is_active = False
            changed.append("is_active")
        record_audit(
            self.db, "admin.agent.unlink", user_id=actor.id, client_id=agent.client_id,
            entity_type="agent", entity_id=agent.id,
            details={"fields": changed}, ip_address=ip,
        )
        self.db.commit()
        self.db.refresh(agent)
        return agent
