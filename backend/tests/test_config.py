from pathlib import Path

import pytest
from pydantic import ValidationError

from attackscope.core.config import Settings


def test_environment_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ATTACKSCOPE_DATABASE_PATH", str(tmp_path / "custom.db"))
    monkeypatch.setenv("ATTACKSCOPE_READ_PORT", "8100")
    settings = Settings()
    assert settings.database_path == tmp_path / "custom.db"
    assert settings.read_port == 8100


@pytest.mark.parametrize(
    "values",
    [
        {"database_path": "relative.db"},
        {"read_port": 80},
        {"read_port": 65536},
        {"read_port": 8001, "ingest_port": 8001},
        {"log_level": "verbose"},
        {"sqlite_busy_timeout_ms": 0},
    ],
)
def test_invalid_settings(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)
