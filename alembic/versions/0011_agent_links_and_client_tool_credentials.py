"""add agent phone uniqueness and per-client Sarvam credentials

Revision ID: 0011
Revises: 0010
"""
import re

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def _normalize_existing_agent_phones(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, phone_number FROM agents "
            "WHERE phone_number IS NOT NULL ORDER BY id"
        )
    ).all()
    seen: set[str] = set()
    for agent_id, phone_number in rows:
        normalized = re.sub(r"[\s\-().]", "", phone_number)
        digits = re.sub(r"\D", "", normalized)
        replacement = None if digits in seen else normalized
        if replacement != phone_number:
            bind.execute(
                sa.text(
                    "INSERT INTO agent_phone_number_migration_backup "
                    "(agent_id, original_phone_number) VALUES (:id, :phone)"
                ),
                {"id": agent_id, "phone": phone_number},
            )
        if digits in seen:
            bind.execute(
                sa.text("UPDATE agents SET phone_number = NULL WHERE id = :id"),
                {"id": agent_id},
            )
            continue
        seen.add(digits)
        if normalized != phone_number:
            bind.execute(
                sa.text("UPDATE agents SET phone_number = :phone WHERE id = :id"),
                {"phone": normalized, "id": agent_id},
            )


def upgrade() -> None:
    bind = op.get_bind()
    op.create_table(
        "agent_phone_number_migration_backup",
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("original_phone_number", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id"),
    )
    _normalize_existing_agent_phones(bind)
    op.create_index(
        "uq_agents_phone_number",
        "agents",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("phone_number IS NOT NULL"),
    )
    op.create_table(
        "client_tool_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_client_tool_credentials_token_hash"),
    )
    op.create_index(
        "ix_client_tool_credentials_client_id",
        "client_tool_credentials",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        "uq_client_tool_credentials_active_client",
        "client_tool_credentials",
        ["client_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_client_tool_credentials_active_client",
        table_name="client_tool_credentials",
    )
    op.drop_index(
        "ix_client_tool_credentials_client_id",
        table_name="client_tool_credentials",
    )
    op.drop_table("client_tool_credentials")
    op.drop_index("uq_agents_phone_number", table_name="agents")
    bind = op.get_bind()
    backup_rows = bind.execute(
        sa.text(
            "SELECT agent_id, original_phone_number "
            "FROM agent_phone_number_migration_backup"
        )
    ).all()
    for agent_id, original_phone_number in backup_rows:
        normalized = re.sub(r"[\s\-().]", "", original_phone_number)
        bind.execute(
            sa.text(
                "UPDATE agents SET phone_number = :original "
                "WHERE id = :id AND (phone_number IS NULL OR phone_number = :normalized)"
            ),
            {
                "original": original_phone_number,
                "id": agent_id,
                "normalized": normalized,
            },
        )
    op.drop_table("agent_phone_number_migration_backup")
