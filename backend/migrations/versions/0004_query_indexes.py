"""Indexes for retention FK lookup and classification windows."""

from alembic import op

revision = "0004_query_indexes"
down_revision = "0003_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_delivery_keys_event_id", "delivery_keys", ["event_id"])
    op.create_index(
        "ix_events_host_ip_source_time", "events", ["host_id", "src_ip", "source", "timestamp"]
    )


def downgrade() -> None:
    op.drop_index("ix_events_host_ip_source_time", table_name="events")
    op.drop_index("ix_delivery_keys_event_id", table_name="delivery_keys")
