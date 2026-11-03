from pathlib import Path

import pytest
from sqlalchemy import select

from attackscope.backup import create_backup
from attackscope.storage.database import create_database
from attackscope.storage.migrations import schema_is_current, upgrade_database
from attackscope.storage.schema import hosts
from attackscope.storage.store import Store


def test_backup_restore_migration_and_original_unchanged(tmp_path: Path) -> None:
    original = tmp_path / "original.db"
    engine = create_database(original)
    upgrade_database(engine)
    host_id = Store(engine).create_host("backup-test")
    snapshot = tmp_path / "private" / "snapshot.db"
    create_backup(original, snapshot)
    assert snapshot.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        create_backup(original, snapshot)
    restored = create_database(snapshot)
    upgrade_database(restored)
    with restored.connect() as connection:
        assert schema_is_current(connection)
        assert (
            connection.execute(select(hosts.c.name).where(hosts.c.id == host_id)).scalar()
            == "backup-test"
        )
    with engine.connect() as connection:
        assert connection.execute(select(hosts.c.id)).scalar() == host_id
    restored.dispose()
    engine.dispose()
