"""Migration runner safely ignores SQL comments with semicolons."""
from __future__ import annotations
import uuid
import psycopg
from pathlib import Path
from server.database import DB_URL
from server.db import migration_runner

def test_sql_comment_semicolon_is_not_executed(tmp_path,monkeypatch):
    migration=tmp_path/"0001_test.sql"
    migration.write_text("-- Comment about existing data; never execute the second half\n"
      "CREATE TABLE IF NOT EXISTS stage4_comment_test (id int);\n-- final; semicolon\n",
      encoding="utf8")
    monkeypatch.setattr(migration_runner,"MIGRATIONS",tmp_path)
    schema="comment_"+uuid.uuid4().hex[:12]
    with psycopg.connect(DB_URL) as conn:
        conn.execute('CREATE SCHEMA "'+schema+'"')
        try:
            conn.execute('SET search_path TO "'+schema+'"')
            migration_runner.migrate(conn)
            assert conn.execute("SELECT count(*) FROM stage4_comment_test").fetchone()[0]==0
            migration_runner.migrate(conn)
            assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]==1
        finally:
            conn.execute("RESET search_path")
            conn.execute('DROP SCHEMA "'+schema+'" CASCADE')
