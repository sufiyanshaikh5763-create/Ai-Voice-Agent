"""Per-client Sarvam tool credentials; raw tokens are returned only during creation/rotation."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.agent import Agent
from app.models.client import Client
from app.models.client_tool_credential import ClientToolCredential
from app.models.user import User
from app.schemas.agent_link import ClientIntegrationOut, ClientToolTokenOut, LinkedAgentItem
from app.services.audit_service import record_audit

_TOOL_ACTIONS = ("check-slot", "book", "reschedule", "cancel")
logger = logging.getLogger(__name__)


def _base_url(value: str) -> tuple[str, bool]:
    base = value.strip().rstrip("/")
    return base, bool(base)


def _tool_url(base: str, client_id: int, token: str, action: str) -> str:
    return (
        f"{base}/api/v1/webhooks/sarvam/{token}/{client_id}"
        f"/appointments/{action}"
    )


class ClientToolCredentialService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_or_rotate(
        self, client_id: int, actor: User, ip: str | None, public_api_base_url: str,
    ) -> ClientToolTokenOut:
        client = self.db.scalar(
            select(Client).where(Client.id == client_id).with_for_update()
        )
        if client is None:
            raise NotFoundError("Client not found", error_code="CLIENT_NOT_FOUND")

        now = datetime.now(timezone.utc)
        current = self.db.scalar(
            select(ClientToolCredential).where(
                ClientToolCredential.client_id == client_id,
                ClientToolCredential.revoked_at.is_(None),
            )
        )
        rotating = current is not None
        if current is not None:
            current.revoked_at = now

        token = secrets.token_urlsafe(32)
        credential = ClientToolCredential(
            client_id=client_id,
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            rotated_at=now if rotating else None,
        )
        self.db.add(credential)
        record_audit(
            self.db,
            "admin.client_tool_token.rotate" if rotating else "admin.client_tool_token.create",
            user_id=actor.id,
            client_id=client_id,
            entity_type="client_tool_credential",
            details={"fields": ["token"], "operation": "rotated" if rotating else "created"},
            ip_address=ip,
        )
        self.db.commit()

        base, absolute = _base_url(public_api_base_url)
        return ClientToolTokenOut(
            token=token,
            tool_urls={
                action: _tool_url(base, client_id, token, action)
                for action in _TOOL_ACTIONS
            },
            urls_are_absolute=absolute,
        )

    def integration(
        self, client_id: int, public_api_base_url: str,
    ) -> ClientIntegrationOut:
        client = self.db.get(Client, client_id)
        if client is None:
            raise NotFoundError("Client not found", error_code="CLIENT_NOT_FOUND")
        credential = self.db.scalar(
            select(ClientToolCredential).where(
                ClientToolCredential.client_id == client_id,
                ClientToolCredential.revoked_at.is_(None),
            )
        )
        agents = self.db.scalars(
            select(Agent).where(Agent.client_id == client_id)
            .order_by(Agent.created_at.desc(), Agent.id.desc())
        ).all()
        base, absolute = _base_url(public_api_base_url)
        return ClientIntegrationOut(
            signed_event_webhook_url=f"{base}/api/v1/webhooks/sarvam",
            tool_url_patterns={
                action: _tool_url(base, client_id, "{TOKEN}", action)
                for action in _TOOL_ACTIONS
            },
            urls_are_absolute=absolute,
            credential_exists=credential is not None,
            credential_created_at=credential.created_at if credential else None,
            credential_rotated_at=credential.rotated_at if credential else None,
            credential_last_used_at=credential.last_used_at if credential else None,
            agents=[
                LinkedAgentItem(
                    id=agent.id,
                    name=agent.name,
                    provider=agent.provider,
                    provider_agent_id=agent.provider_agent_id,
                    phone_number=agent.phone_number,
                    status=agent.status,
                )
                for agent in agents
            ],
        )


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def record_credential_use(credential_id: int) -> None:
    """Best-effort timestamp update isolated from the tool request transaction."""
    from app.core.database import SessionLocal

    try:
        with SessionLocal() as db:
            credential = db.get(ClientToolCredential, credential_id)
            if credential is None:
                return
            credential.last_used_at = datetime.now(timezone.utc)
            db.commit()
    except Exception:
        logger.exception("Could not update Sarvam tool credential use time")
