"""add webhook request ids and log query indexes

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


_INDEXES = (
    ("webhook_events", "ix_webhook_events_status_created_at", ["status", "created_at"]),
    ("webhook_events", "ix_webhook_events_client_created_at", ["client_id", "created_at"]),
    ("audit_logs", "ix_audit_logs_action_created_at", ["action", "created_at"]),
)


def upgrade() -> None:
    op.add_column(
        "webhook_events",
        sa.Column("request_id", sa.Text(), nullable=True),
    )
    inspector = sa.inspect(op.get_bind())
    for table_name, index_name, columns in _INDEXES:
        existing = inspector.get_indexes(table_name)
        name_exists = any(index["name"] == index_name for index in existing)
        columns_exist = any(
            tuple(index.get("column_names") or ()) == tuple(columns)
            for index in existing
        )
        if not name_exists and not columns_exist:
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, index_name, _ in reversed(_INDEXES):
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)
    op.drop_column("webhook_events", "request_id")
