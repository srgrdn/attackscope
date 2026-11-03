import asyncio
import logging

from sqlalchemy import Engine

from attackscope.core.config import Settings
from attackscope.server import serve
from attackscope.storage.database import create_database
from attackscope.storage.migrations import upgrade_database


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)
    engine: Engine | None = None
    try:
        settings = Settings()
        logging.getLogger().setLevel(settings.log_level.upper())
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_database(settings.database_path, settings.sqlite_busy_timeout_ms)
        upgrade_database(engine)
        asyncio.run(serve(settings, engine))
    except Exception as error:
        # Validation errors may include input values; do not dump them or SQL/paths in logs.
        logging.getLogger("attackscope").error(
            "Startup or runtime failure (%s); check configuration/runtime", type(error).__name__
        )
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
