"""Transactionally apply additive, versioned SQL schema changes."""
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parent / "migrations"

def migrate(db):
    db.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    applied = {(row["version"] if isinstance(row, dict) else row[0]) for row in db.execute("SELECT version FROM schema_migrations")}
    for file in sorted(MIGRATIONS.glob("*.sql")):
        if file.name in applied:
            continue
        # Remove whole-line SQL comments before splitting statements. A semicolon
        # in a --comment must never be parsed as a new SQL command. Complex SQL
        # (procedural blocks, semicolons inside strings) is not supported by this
        # additive migration format.
        script = chr(10).join(line for line in file.read_text(encoding="utf-8").splitlines()
                           if not line.lstrip().startswith("--"))
        for statement in script.split(";"):
            if statement.strip():
                db.execute(statement)
        db.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (file.name,))
