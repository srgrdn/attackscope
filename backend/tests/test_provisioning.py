import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from attackscope.api.runtime import Runtime
from attackscope.cli import provision_source
from attackscope.core.errors import ServiceError
from attackscope.storage.schema import sources


def test_generated_secret_file_is_private_and_digest_only(runtime: Runtime, tmp_path: Path) -> None:
    path = tmp_path / "secrets" / "http.token"
    source_id = provision_source(runtime.store, runtime.test_host_id, "http", path)
    token = path.read_text().strip()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert runtime.store.authenticate(f"Bearer {token}").id == source_id
    with runtime.store.engine.connect() as connection:
        row = dict(
            connection.execute(select(sources).where(sources.c.id == source_id)).mappings().one()
        )
    assert token not in json.dumps(row)
    assert len(row["token_digest"]) == 64
    runtime.store.disable_source(source_id)
    with pytest.raises(ServiceError):
        runtime.store.authenticate(f"Bearer {token}")


def test_source_file_cannot_be_overwritten_or_symlinked(runtime: Runtime, tmp_path: Path) -> None:
    existing = tmp_path / "existing.token"
    existing.write_text("keep this")
    alias = tmp_path / "alias.token"
    alias.symlink_to(existing)
    for path in (existing, alias):
        with pytest.raises(FileExistsError):
            provision_source(runtime.store, runtime.test_host_id, "http", path)
    assert existing.read_text() == "keep this"


def test_failed_provision_leaves_no_token_or_source(runtime: Runtime, tmp_path: Path) -> None:
    path = tmp_path / "invalid-host.token"
    with pytest.raises(ValueError):
        provision_source(runtime.store, str(uuid4()), "http", path)
    assert not path.exists()
    with runtime.store.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(sources)).scalar() == 3


def test_cli_output_does_not_expose_secret(runtime: Runtime, tmp_path: Path) -> None:
    path = tmp_path / "cli.token"
    dbpath = runtime.store.engine.url.database
    environment = {**os.environ, "ATTACKSCOPE_DATABASE_PATH": str(dbpath)}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "attackscope.cli",
            "create-source",
            "--host-id",
            runtime.test_host_id,
            "--kind",
            "http",
            "--token-file",
            str(path),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    token = path.read_text().strip()
    assert token not in result.stdout + result.stderr
    assert json.loads(result.stdout)["source_id"] == token.split(".")[0]
