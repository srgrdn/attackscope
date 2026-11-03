from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
)

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    }
)
hosts = Table(
    "hosts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    Column("disabled", Boolean, nullable=False, server_default="0"),
)
sources = Table(
    "sources",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("host_id", ForeignKey("hosts.id"), nullable=False, index=True),
    Column("kind", String(16), nullable=False),
    Column("token_digest", String(64), nullable=False),
    Column("enabled", Boolean, nullable=False, server_default="1"),
    Column("created_at", BigInteger, nullable=False),
    CheckConstraint("kind IN ('ssh','http','firewall')", name="kind"),
)
events = Table(
    "events",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("schema_version", Integer, nullable=False),
    Column("timestamp", BigInteger, nullable=False),
    Column("received_at", BigInteger, nullable=False, index=True),
    Column("host_id", ForeignKey("hosts.id"), nullable=False),
    Column("source_id", ForeignKey("sources.id"), nullable=False),
    Column("source", String(16), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("category", String(64), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("src_ip", String(45)),
    Column("dst_ip", String(45)),
    Column("src_port", Integer),
    Column("dst_port", Integer),
    Column("protocol", String(16)),
    Column("classification", JSON(none_as_null=True)),
    Column("attributes", JSON, nullable=False),
    Column("source_reference", String(512)),
    Column("safe_original", JSON, nullable=False),
    Column("http_path", String(2048)),
    Column("http_status", Integer),
    Column("ssh_outcome", String(32)),
    CheckConstraint("schema_version = 1", name="schema_version"),
    CheckConstraint("src_port IS NULL OR src_port BETWEEN 0 AND 65535", name="src_port"),
    CheckConstraint("dst_port IS NULL OR dst_port BETWEEN 0 AND 65535", name="dst_port"),
    CheckConstraint("source IN ('ssh','http','firewall')", name="source"),
    CheckConstraint("severity IN ('info','low','medium','high')", name="severity"),
    CheckConstraint("length(CAST(attributes AS BLOB)) <= 8192", name="attributes_size"),
    CheckConstraint("length(CAST(safe_original AS BLOB)) <= 8192", name="original_size"),
)
Index("ix_events_time_id", events.c.timestamp, events.c.id)
for dimension in ("host_id", "src_ip", "category", "source", "dst_port"):
    Index(f"ix_events_{dimension}_time_id", events.c[dimension], events.c.timestamp, events.c.id)

delivery_keys = Table(
    "delivery_keys",
    metadata,
    Column("source_id", ForeignKey("sources.id"), primary_key=True),
    Column("source_reference", String(512), primary_key=True),
    Column("event_id", ForeignKey("events.id", ondelete="SET NULL")),
    Column("first_received_at", BigInteger, nullable=False),
    Column("expires_at", BigInteger, nullable=False, index=True),
)
event_rollups = Table(
    "event_rollups",
    metadata,
    Column("bucket", BigInteger, primary_key=True),
    Column("host_id", ForeignKey("hosts.id"), primary_key=True),
    Column("src_ip_key", String(45), primary_key=True),
    Column("source", String(16), primary_key=True),
    Column("category", String(64), primary_key=True),
    Column("dst_port_key", Integer, primary_key=True),
    Column("event_count", BigInteger, nullable=False),
    Column("first_seen", BigInteger, nullable=False),
    Column("last_seen", BigInteger, nullable=False),
    CheckConstraint("event_count > 0", name="positive_count"),
)
Index("ix_event_rollups_ip_bucket", event_rollups.c.src_ip_key, event_rollups.c.bucket)
pending_events = Table(
    "pending_events",
    metadata,
    Column("event_id", ForeignKey("events.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", BigInteger, nullable=False, index=True),
)

findings = Table(
    "findings",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("rule_id", String(64), nullable=False),
    Column("rule_name", String(128), nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("host_id", ForeignKey("hosts.id"), nullable=False),
    Column("src_ip", String(45), nullable=False),
    Column("source", String(16), nullable=False),
    Column("category", String(64), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("timestamp", BigInteger, nullable=False),
    Column("window_start", BigInteger, nullable=False),
    Column("window_end", BigInteger, nullable=False),
    Column("event_count", BigInteger, nullable=False),
    Column("evidence_ids", JSON, nullable=False),
    Column("reason", JSON, nullable=False),
)
Index("ix_findings_time", findings.c.timestamp)
Index("ix_findings_ip_time", findings.c.src_ip, findings.c.timestamp)

Index("ix_delivery_keys_event_id", delivery_keys.c.event_id)
Index(
    "ix_events_host_ip_source_time",
    events.c.host_id,
    events.c.src_ip,
    events.c.source,
    events.c.timestamp,
)
