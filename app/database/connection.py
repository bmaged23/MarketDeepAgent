import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connection(database_path, *, write=False):
    conn = sqlite3.connect(str(database_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def migrate(database_path):
    """Apply migrations once, transactionally. Preserve existing product IDs."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path, write=True) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
        for migration in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
            if conn.execute("SELECT 1 FROM schema_migrations WHERE version=?", (migration.name,)).fetchone():
                continue
            # executescript commits implicitly; complete_statement avoids that behavior.
            statement = ""
            for line in migration.read_text().splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ""
            if statement.strip():
                raise ValueError(f"Incomplete SQL in {migration.name}")
            conn.execute("INSERT INTO schema_migrations VALUES (?)", (migration.name,))
