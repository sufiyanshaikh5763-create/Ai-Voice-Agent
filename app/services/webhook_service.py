"""Sarvam webhook event processing.

Idempotent: `(provider, event_id)` is unique, so a retried delivery is detected before any
side effect runs. The tenant is resolved ONLY from the agent id in the payload — never from
anything else in it — so a malformed or malicious payload can't target another tenant.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.sarvam.schemas import SarvamWebhookEnvelope
from app.models.agent import Agent
from app.models.client import Client
from app.models.enums import CallDirection, CallStatus, WebhookEventStatus
from app.models.webhook_event import WebhookEvent
from app.repositories.call_repository import CallRepository
from app.repositories.customer_repository import CustomerRepository
from app.schemas.webhook import WebhookOutcome
from app.services.agent_request_service import AgentRequestService

PROVIDER = "sarvam"

_CALL_STATUS = {
    "initiated": CallStatus.INITIATED, "in_progress": CallStatus.IN_PROGRESS,
    "completed": CallStatus.COMPLETED, "failed": CallStatus.FAILED, "missed": CallStatus.MISSED,
}


class WebhookProcessingError(Exception):
    """Business-rule failure while applying an already-authenticated, well-formed event."""

    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class WebhookService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ----- idempotency -----
    def _claim_event(self, envelope: SarvamWebhookEnvelope, raw_payload: dict,
                     request_id: str | None = None) -> WebhookEvent | None:
        """Inserts the event row; returns None if this event_id was already seen."""
        event = WebhookEvent(provider=PROVIDER, event_id=envelope.event_id,
                             event_type=envelope.event_type, payload=raw_payload,
                             request_id=request_id[:255] if request_id else None)
        self.db.add(event)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return None
        return event

    def _resolve_agent(self, provider_agent_id: str) -> Agent | None:
        return self.db.scalar(select(Agent).where(
            Agent.provider == PROVIDER, Agent.provider_agent_id == provider_agent_id))

    def _metadata_client_id(self, raw_payload: dict) -> int | None:
        metadata = raw_payload.get("metadata")
        if not isinstance(metadata, dict):
            config = raw_payload.get("webhook_config")
            metadata = config.get("metadata") if isinstance(config, dict) else None
        if not isinstance(metadata, dict):
            return None
        raw_client_id = metadata.get("client_id", metadata.get("tenant_id"))
        try:
            client_id = int(raw_client_id) if raw_client_id is not None else None
        except (TypeError, ValueError):
            return None
        return client_id if client_id is not None and self.db.get(Client, client_id) else None

    # ----- dispatch -----
    def process(self, envelope: SarvamWebhookEnvelope, raw_payload: dict,
                request_id: str | None = None) -> WebhookOutcome:
        now = datetime.now(timezone.utc)
        event = self._claim_event(envelope, raw_payload, request_id)
        if event is None:
            event = self.db.scalar(select(WebhookEvent).where(
                WebhookEvent.provider == PROVIDER,
                WebhookEvent.event_id == envelope.event_id,
            ))
            if event is not None:
                event.status = WebhookEventStatus.DUPLICATE
                event.error_message = "Duplicate event"
                event.processed_at = now
                event.request_id = request_id[:255] if request_id else None
            self.db.commit()
            return WebhookOutcome(event_id=envelope.event_id, status=WebhookEventStatus.DUPLICATE,
                                  message="Event already processed")

        agent = self._resolve_agent(envelope.agent_id)
        if agent is None:
            event.status = WebhookEventStatus.FAILED
            event.error_message = f"Unknown agent_id: {envelope.agent_id}"
            event.client_id = self._metadata_client_id(raw_payload)
            event.processed_at = now
            self.db.commit()
            return WebhookOutcome(event_id=envelope.event_id, status=WebhookEventStatus.FAILED,
                                  message="Unknown agent")

        try:
            self._dispatch(envelope, agent)
        except (AppError, WebhookProcessingError) as exc:
            self.db.rollback()
            # Re-fetch: the rollback above also undid the WebhookEvent insert.
            event = self._claim_event(envelope, raw_payload, request_id)
            message = getattr(exc, "message", str(exc))
            if event is not None:
                event.status = WebhookEventStatus.FAILED
                event.error_message = message
                event.client_id = agent.client_id
                event.processed_at = datetime.now(timezone.utc)
            self.db.commit()
            return WebhookOutcome(event_id=envelope.event_id, status=WebhookEventStatus.FAILED,
                                  message=message)
        except Exception:
            self.db.rollback()
            event = self._claim_event(envelope, raw_payload, request_id)
            if event is not None:
                event.status = WebhookEventStatus.FAILED
                event.error_message = "Webhook processing error"
                event.client_id = agent.client_id
                event.processed_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

        event.status = WebhookEventStatus.PROCESSED
        event.client_id = agent.client_id
        event.processed_at = datetime.now(timezone.utc)
        self.db.commit()
        return WebhookOutcome(event_id=envelope.event_id, status=WebhookEventStatus.PROCESSED,
                              message="Event processed")

    def _dispatch(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        handler = {
            "call_started": self._handle_call_started,
            "call_completed": self._handle_call_completed,
            "appointment_created": self._handle_appointment_created,
            "appointment_cancelled": self._handle_appointment_cancelled,
            "appointment_rescheduled": self._handle_appointment_rescheduled,
        }[envelope.event_type]
        handler(envelope, agent)

    # ----- calls -----
    def _handle_call_started(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        from app.models.call import Call
        from app.utils.validators import normalize_phone

        data = envelope.call
        calls = CallRepository(self.db, agent.client_id)
        if calls.get_by_provider_call_id(data.provider_call_id) is not None:
            return  # already recorded (e.g. a retried call_started)
        customer = CustomerRepository(self.db, agent.client_id).get_by_phone(
            normalize_phone(data.phone_number))
        calls.add(Call(
            agent_id=agent.id, customer_id=customer.id if customer else None,
            provider_call_id=data.provider_call_id, phone_number=normalize_phone(data.phone_number),
            direction=CallDirection(data.direction),
            status=_CALL_STATUS.get(data.status, CallStatus.IN_PROGRESS),
            started_at=data.started_at or envelope.occurred_at))
        self.db.flush()

    def _handle_call_completed(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        from app.models.call import Call
        from app.utils.validators import normalize_phone

        data = envelope.call
        calls = CallRepository(self.db, agent.client_id)
        call = calls.get_by_provider_call_id(data.provider_call_id)
        if call is None:
            # call_completed arrived without a prior call_started: record it directly.
            customer = CustomerRepository(self.db, agent.client_id).get_by_phone(
                normalize_phone(data.phone_number))
            call = calls.add(Call(
                agent_id=agent.id, customer_id=customer.id if customer else None,
                provider_call_id=data.provider_call_id,
                phone_number=normalize_phone(data.phone_number),
                direction=CallDirection(data.direction), started_at=data.started_at))
        call.status = _CALL_STATUS.get(data.status, CallStatus.COMPLETED)
        call.duration = data.duration
        call.recording_url = data.recording_url
        call.transcript = data.transcript
        call.ended_at = data.ended_at or envelope.occurred_at
        self.db.flush()

    # ----- appointments -----
    def _handle_appointment_created(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        data = envelope.appointment
        if data.appointment_date is None or data.appointment_time is None:
            raise WebhookProcessingError(
                "APPOINTMENT_DATE_REQUIRED", "appointment_date and appointment_time are required")
        AgentRequestService(self.db, agent.client_id).book(
            customer_phone=data.customer_phone, customer_name=data.customer_name,
            appointment_date=data.appointment_date, appointment_time=data.appointment_time,
            notes=data.notes)

    def _handle_appointment_cancelled(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        data = envelope.appointment
        AgentRequestService(self.db, agent.client_id).cancel(
            customer_phone=data.customer_phone, appointment_id=data.appointment_id,
            day=data.appointment_date, at=data.appointment_time, reason=data.reason)

    def _handle_appointment_rescheduled(self, envelope: SarvamWebhookEnvelope, agent: Agent) -> None:
        data = envelope.appointment
        AgentRequestService(self.db, agent.client_id).reschedule(
            customer_phone=data.customer_phone, new_date=data.new_date, new_time=data.new_time,
            appointment_id=data.appointment_id, day=data.appointment_date,
            at=data.appointment_time, reason=data.reason)
