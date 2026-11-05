"""PostgreSQL state for web sessions, uploaded files, reference metadata and jobs."""
from __future__ import annotations
import os
import time
from contextlib import contextmanager
from pathlib import Path
from .db.migration_runner import migrate
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

DB_URL = os.environ.get('DATABASE_URL', '')
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 username TEXT NOT NULL UNIQUE,
 password_salt TEXT NOT NULL,
 password_hash TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY,
 user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
 id UUID PRIMARY KEY,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS uploads (
 id UUID PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('fo', 'reference')),
 batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,
 sam TEXT,
 filename TEXT NOT NULL,
 declared_size BIGINT NOT NULL CHECK(declared_size > 0),
 received BIGINT NOT NULL DEFAULT 0,
 checksum TEXT,
 finalized BOOLEAN NOT NULL DEFAULT FALSE,
 target_path TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_uploads_batch ON uploads(batch_id);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY,
 batch_id UUID NOT NULL REFERENCES batches(id),
 status TEXT NOT NULL,
 snapshot JSONB NOT NULL,
 stop_requested BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE TABLE IF NOT EXISTS reference_cache (
 source_hash TEXT NOT NULL,
 model_signature TEXT NOT NULL,
 cache_path TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(source_hash, model_signature)
);
"""

@contextmanager
def connect():
    if not DB_URL: raise RuntimeError('DATABASE_URL is missing')
    with psycopg.connect(DB_URL, row_factory=dict_row, connect_timeout=8) as db:
        yield db


def initialize():
    with connect() as db:
        db.execute('SELECT pg_advisory_xact_lock(723409134)')
        # psycopg 3 multi statements with params=None, no prepared server statement.
        for statement in SCHEMA.split(';'):
            if statement.strip(): db.execute(statement)
        migrate(db)


def wait_and_initialize(timeout=90):
    start = time.monotonic()
    while True:
        try: return initialize()
        except psycopg.OperationalError:
            if time.monotonic()-start>timeout: raise
            time.sleep(2)


def snapshot(run_id):
    with connect() as db:
        return db.execute('SELECT snapshot FROM jobs WHERE id=%s',(run_id,)).fetchone()


def save_snapshot(info):
    with connect() as db:
        db.execute("""UPDATE jobs SET snapshot=%s,status=%s,updated_at=now(),
             finished_at=CASE WHEN %s IN
               ('completed','completed_with_errors','failed','stopped','interrupted')
                 THEN now() ELSE finished_at END
             WHERE id=%s""",(Jsonb(info),info['status'],info['status'],info['id']))
