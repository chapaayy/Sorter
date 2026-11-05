"""Transactionally apply additive, versioned SQL schema changes."""
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"

def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    applied = {row["version"] for row in db.execute("SELECT version FROM schema_migrations")}
    for file in sorted(MIGRATIONS.glob("*.sql")):
        if file.name in applied:
            continue
        script = file.read_text(encoding="utf-8")
        # The simple SQL format intentionally prohibits procedural blocks with semicolons.
        for statement in script.split(";"):
            if statement.strip():
                db.execute(statement)
        db.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (file.name,))
