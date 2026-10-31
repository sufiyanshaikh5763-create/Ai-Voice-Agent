from sqlalchemy import (Boolean, ForeignKey, Index, String, Text, UniqueConstraint,
                        text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JsonType, TimestampMixin, str_enum
from app.models.enums import AgentStatus


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        # Target for composite tenant-safe foreign keys (calls -> agents).
        UniqueConstraint("client_id", "id", name="uq_agents_client_id_id"),
        UniqueConstraint("provider", "provider_agent_id", name="uq_agents_provider_ref"),
        Index(
            "uq_agents_phone_number",
            "phone_number",
            unique=True,
            postgresql_where=text("phone_number IS NOT NULL"),
            sqlite_where=text("phone_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    phone_number: Mapped[str | None] = mapped_column(String(32))
    # Plain string (not an enum) so new providers need no migration.
    provider: Mapped[str] = mapped_column(String(50), default="sarvam", nullable=False)
    provider_agent_id: Mapped[str | None] = mapped_column(String(255))
    configuration: Mapped[dict] = mapped_column(JsonType, default=dict, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        str_enum(AgentStatus, "agent_status"), default=AgentStatus.ACTIVE, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    client = relationship("Client", back_populates="agents")
