from datetime import UTC, datetime, timedelta

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
HOUR_US = 3_600_000_000
DAY_US = 24 * HOUR_US


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone required")
    delta = value.astimezone(UTC) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def from_us(value: int) -> str:
    return (EPOCH + timedelta(microseconds=value)).isoformat().replace("+00:00", "Z")


def detail_cutoff(now: int, days: int) -> int:
    return ((now - days * DAY_US) // HOUR_US) * HOUR_US
