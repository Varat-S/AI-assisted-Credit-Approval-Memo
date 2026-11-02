"""Local database readiness checks before paid browser work; never migrate or retry."""
from pathlib import Path
import sqlite3

from app.models.base import Base
from app.models import orm  # register all required tables before inspecting metadata


def check_database(database, *, timeout=5):
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError('Analysis database is missing. Initialize/migrate the selected database before starting.')
    connection = None
    try:
        connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=timeout, isolation_level=None)
        for table in Base.metadata.sorted_tables:
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table.name}")')}
            missing = {column.name for column in table.columns} - columns
            if missing:
                raise ValueError(f'Analysis database schema is not ready: {table.name} lacks {", ".join(sorted(missing))}. '
                                 'Run the existing database migration before starting.')
        # Acquire and immediately release the writer reservation. No rows,
        # schema, approval records or analytical content are written.
        connection.execute('BEGIN IMMEDIATE')
        connection.execute('ROLLBACK')
    except sqlite3.Error as exc:
        raise ValueError('Analysis database is not writable or is unavailable/locked. No analysis was started.') from exc
    finally:
        if connection is not None:
            connection.close()
