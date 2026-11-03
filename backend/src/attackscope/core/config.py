from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATTACKSCOPE_", extra="ignore")

    database_path: Path = Path("/data/attackscope.db")
    bind_host: str = "127.0.0.1"
    read_port: int = Field(default=8000, ge=1024, le=65535)
    ingest_port: int = Field(default=8001, ge=1024, le=65535)
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100, le=30000)

    detail_retention_days: int = Field(default=30, ge=1, le=365)
    aggregate_retention_days: int = Field(default=365, ge=1, le=3650)
    dedup_retention_days: int = Field(default=30, ge=1, le=365)
    max_body_bytes: int = Field(default=1_048_576, ge=1024, le=4_194_304)
    max_batch_events: int = Field(default=500, ge=1, le=500)
    max_api_concurrency: int = Field(default=16, ge=1, le=32)
    source_requests_per_second: float = Field(default=5, gt=0, le=100)
    source_burst: int = Field(default=10, ge=1, le=100)
    source_concurrency: int = Field(default=2, ge=1, le=4)
    write_wait_seconds: float = Field(default=0.25, gt=0, le=2)
    query_timeout_seconds: float = Field(default=5, gt=0, le=15)
    body_timeout_seconds: float = Field(default=5, gt=0, le=30)

    ssh_window_seconds: int = Field(default=300, ge=10, le=3600)
    ssh_failure_threshold: int = Field(default=10, ge=2, le=10000)
    web_rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    web_request_threshold: int = Field(default=120, ge=2, le=10000)
    web_paths_window_seconds: int = Field(default=300, ge=10, le=3600)
    web_path_threshold: int = Field(default=30, ge=2, le=10000)
    port_window_seconds: int = Field(default=300, ge=10, le=3600)
    port_threshold: int = Field(default=10, ge=2, le=65535)

    @model_validator(mode="after")
    def validate_paths_and_ports(self) -> "Settings":
        if self.aggregate_retention_days < self.detail_retention_days:
            raise ValueError("Aggregate retention must cover detail retention")
        if not self.database_path.is_absolute():
            raise ValueError("database_path must be absolute")
        if self.read_port == self.ingest_port:
            raise ValueError("read_port and ingest_port must differ")
        return self
