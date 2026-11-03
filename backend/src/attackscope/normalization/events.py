import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    IPvAnyAddress,
    StrictInt,
    TypeAdapter,
    field_validator,
)

from attackscope.core.errors import ServiceError
from attackscope.core.time import detail_cutoff, from_us, to_us

SourceKind = Literal["ssh", "http", "firewall"]
Category = Literal["ssh_authentication", "ssh_connection", "http_request", "firewall_packet"]
Severity = Literal["info", "low", "medium", "high"]


def clean_text(value: str, limit: int) -> str:
    value = "".join(char for char in value if not unicodedata.category(char).startswith("C"))
    return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")


def canonical_ip(value: IPv4Address | IPv6Address | None) -> str | None:
    if isinstance(value, IPv6Address):
        if value.scope_id is not None:
            raise ValueError("Scoped IPv6 is unsupported")
        if value.ipv4_mapped:
            return str(value.ipv4_mapped)
    return str(value) if value is not None else None


def timestamp_input(value: object) -> object:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    ):
        raise ValueError("RFC3339 timestamp required")
    return value


def stable_reference(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9:._/\-]{1,512}", value):
        raise ValueError("Invalid stable reference")
    return value


Timestamp = Annotated[AwareDatetime, BeforeValidator(timestamp_input)]


def canonical_address(value: IPv4Address | IPv6Address) -> IPv4Address | IPv6Address:
    canonical_ip(value)  # reject zone IDs before storage or serialization
    if isinstance(value, IPv6Address) and value.ipv4_mapped:
        return value.ipv4_mapped
    return value


Address = Annotated[IPvAnyAddress, AfterValidator(canonical_address)]
Port = Annotated[StrictInt, Field(ge=0, le=65535)]
Protocol = Literal["tcp", "udp", "icmp", "icmpv6", "http", "https"]


class Payload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_max_length=8192, allow_inf_nan=False)
    timestamp: Timestamp
    src_ip: Address | None = None
    dst_ip: Address | None = None
    src_port: Port | None = None
    dst_port: Port | None = None
    protocol: Protocol | None = None


class HttpPayload(Payload):
    remote_addr: Address
    request_method: Annotated[
        str, Field(pattern=r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,32}$", max_length=32)
    ]
    path: str = Field(max_length=8192)
    status: Annotated[StrictInt, Field(ge=100, le=599)]
    hostname: str | None = None
    user_agent: str | None = None
    duration_ms: float | None = Field(default=None, ge=0, le=86_400_000, strict=True)
    path_truncated: bool | None = Field(default=None, strict=True)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = value.split("?", 1)[0].split("#", 1)[0]
        if not path.startswith("/") or len(path.encode("utf-8")) > 2048:
            raise ValueError("Invalid path")
        return clean_text(path, 2048)


class SshPayload(Payload):
    outcome: Literal["success", "failure", "invalid_user", "disconnect"]
    username: str | None = None


class FirewallPayload(Payload):
    action: Literal["accept", "drop", "reject"] | None = None
    interface: str | None = None


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transport_version: Literal[1]
    schema_version: Literal[1] = 1
    host_id: UUID | None = None
    source_reference: Annotated[str, AfterValidator(stable_reference)] | None = None

    @field_validator("transport_version", "schema_version", mode="before")
    @classmethod
    def version_is_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Integer version required")
        return value


class HttpEnvelope(Envelope):
    source: Literal["http"]
    payload: HttpPayload


class SshEnvelope(Envelope):
    source: Literal["ssh"]
    payload: SshPayload


class FirewallEnvelope(Envelope):
    source: Literal["firewall"]
    payload: FirewallPayload


EventEnvelope = Annotated[
    HttpEnvelope | SshEnvelope | FirewallEnvelope, Field(discriminator="source")
]
batch_adapter = TypeAdapter(list[EventEnvelope])


@dataclass(frozen=True)
class Normalized:
    values: dict[str, Any]
    reference: str | None


def normalize(envelope: EventEnvelope, host_id: str, kind: str, now: int, days: int) -> Normalized:
    if envelope.host_id is not None and str(envelope.host_id) != host_id:
        raise ServiceError(403, "host_mismatch", "Source does not belong to the claimed host")
    if envelope.source != kind:
        raise ServiceError(403, "source_mismatch", "Source kind is not permitted")
    payload = envelope.payload
    timestamp = to_us(payload.timestamp)
    if timestamp < detail_cutoff(now, days) or timestamp > now + 300_000_000:
        raise ServiceError(422, "timestamp_range", "Timestamp outside the accepted range")
    attributes: dict[str, Any] = {}
    projection = payload.model_dump(mode="json", exclude_none=True)
    projection["timestamp"] = from_us(timestamp)
    # A minimal safe projection, never a dump of the caller's unknown fields.
    for key in ("user_agent", "username", "interface", "hostname"):
        value = projection.get(key)
        if isinstance(value, str):
            limit = {"user_agent": 512, "username": 128, "interface": 64, "hostname": 253}[key]
            cleaned = clean_text(value, limit)
            projection[key] = cleaned
            if cleaned != value:
                attributes.setdefault("sanitized_fields", []).append(key)
    values: dict[str, Any] = {
        "schema_version": 1,
        "timestamp": timestamp,
        "host_id": host_id,
        "source": envelope.source,
        "src_ip": canonical_ip(payload.src_ip),
        "dst_ip": canonical_ip(payload.dst_ip),
        "src_port": payload.src_port,
        "dst_port": payload.dst_port,
        "protocol": payload.protocol,
        "classification": None,
        "severity": "info",
        "http_path": None,
        "http_status": None,
        "ssh_outcome": None,
        "source_reference": envelope.source_reference,
    }
    if isinstance(payload, HttpPayload):
        values.update(
            src_ip=canonical_ip(payload.remote_addr),
            event_type="http.request",
            category="http_request",
            http_path=payload.path,
            http_status=payload.status,
        )
        attributes.update(
            {
                key: projection[key]
                for key in (
                    "request_method",
                    "path",
                    "status",
                    "user_agent",
                    "duration_ms",
                    "hostname",
                    "path_truncated",
                )
                if key in projection
            }
        )
        # Ignore a second claimed HTTP source IP; remote_addr is the contract's authority.
        projection.pop("src_ip", None)
    elif isinstance(payload, SshPayload):
        values.update(
            event_type={
                "success": "ssh.auth_success",
                "failure": "ssh.auth_failure",
                "invalid_user": "ssh.invalid_user",
                "disconnect": "ssh.disconnect",
            }[payload.outcome],
            category="ssh_connection" if payload.outcome == "disconnect" else "ssh_authentication",
            ssh_outcome=payload.outcome,
        )
        if payload.outcome in ("failure", "invalid_user"):
            values["severity"] = "low"
        attributes.update(
            {key: projection[key] for key in ("outcome", "username") if key in projection}
        )
    else:
        values.update(event_type="firewall.packet", category="firewall_packet")
        attributes.update(
            {key: projection[key] for key in ("action", "interface") if key in projection}
        )
    values.update(attributes=attributes, safe_original=projection)
    return Normalized(values, envelope.source_reference)
