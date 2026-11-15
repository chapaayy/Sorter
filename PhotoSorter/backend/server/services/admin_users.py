"""Owner-managed viewer accounts using the same grants as approved applications."""
import secrets

from fastapi import HTTPException

from ..auth import hash_password
from ..database import connect
from ..db.repositories import access_requests as repository
from .access_requests import available_results, credentials


def list_users(limit, offset):
    with connect() as db:
        rows = repository.list_users(db, limit + 1, offset)
    return {"items": rows[:limit], "has_more": len(rows) > limit}


def create(email, password, confirmation, run_ids):
    email = credentials(email, password, confirmation)
    salt = secrets.token_bytes(16)
    verifier = hash_password(password, salt)
    with connect() as db:
        repository.lock_email(db, email)
        # Same row-before-user order as approval. Never reuse an applicant's
        # password or allow approval to overwrite the owner's chosen password.
        pending = repository.pending_by_email(db, email)
        chosen = available_results(db, run_ids)
        user = repository.create_viewer(db, email, salt.hex(), verifier)
        if user is None:
            raise HTTPException(409, "Аккаунт с этой почтой уже существует")
        if chosen:
            repository.grant_results(db, user["id"], chosen)
        if pending:
            repository.decide(db, pending["id"], "approved")
        return user


def grants(user_id, run_ids=None):
    with connect() as db:
        email = repository.user_email(db, user_id)
        if email is None:
            raise HTTPException(404, "Пользователь не найден")
        if run_ids is not None and not repository.replace_grants(db, email, available_results(db, run_ids)):
            raise HTTPException(404, "Пользователь не найден")
        return {"items": repository.list_grants(db, email)}
