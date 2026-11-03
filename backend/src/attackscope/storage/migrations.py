from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def migration_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def upgrade_database(engine: Engine) -> None:
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def schema_is_current(connection: Connection) -> bool:
    expected = ScriptDirectory.from_config(migration_config()).get_heads()
    actual = MigrationContext.configure(connection).get_current_heads()
    return set(actual) == set(expected)
