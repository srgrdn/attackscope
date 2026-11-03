"""Explainable deterministic findings."""

import sqlalchemy as sa
from alembic import op

revision = "0003_findings"
down_revision = "0002_event_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("rule_name", sa.String(128), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("host_id", sa.String(36), sa.ForeignKey("hosts.id"), nullable=False),
        sa.Column("src_ip", sa.String(45), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("window_end", sa.BigInteger(), nullable=False),
        sa.Column("event_count", sa.BigInteger(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("reason", sa.JSON(), nullable=False),
    )
    op.create_index("ix_findings_time", "findings", ["timestamp"])
    op.create_index("ix_findings_ip_time", "findings", ["src_ip", "timestamp"])


def downgrade() -> None:
    op.drop_table("findings")
