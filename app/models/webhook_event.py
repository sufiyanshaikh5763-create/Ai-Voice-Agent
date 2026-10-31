from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import JsonType, str_enum
from app.models.enums import WebhookEventStatus


class WebhookEvent(Base):
    """Received provider events; the unique key makes webhook processing idempotent."""

    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        Index("ix_webhook_events_status_created_at", "status", "created_at"),
        Index("ix_webhook_events_client_created_at", "client_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    payload: Mapped[dict] = mapped_column(JsonType, nullable=False)
    status: Mapped[WebhookEventStatus] = mapped_column(
        str_enum(WebhookEventStatus, "webhook_event_status"),
        default=WebhookEventStatus.RECEIVED, nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
