from alembic import context
from sqlalchemy import Connection

from attackscope.core.config import Settings
from attackscope.storage.database import create_database
from attackscope.storage.schema import metadata


def run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


external = context.config.attributes.get("connection")
if external is not None:
    run(external)
elif context.is_offline_mode():
    context.configure(url="sqlite://", target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    settings = Settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database(settings.database_path, settings.sqlite_busy_timeout_ms)
    try:
        with engine.begin() as connection:
            run(connection)
    finally:
        engine.dispose()
