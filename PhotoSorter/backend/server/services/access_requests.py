"""Public access requests and atomic owner moderation."""
import re
import secrets
from fastapi import HTTPException
from ..auth import hash_password
from ..database import connect
from ..db.repositories import access_requests as repository

EMAIL = re.compile(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+")


def submit(email, password, confirmation, comment):
    email, comment = email.strip().lower(), comment.strip()
    if len(email) > 254 or not EMAIL.fullmatch(email):
        raise HTTPException(422, "Укажите корректный адрес электронной почты")
    if password != confirmation:
        raise HTTPException(422, "Пароли не совпадают")
    if not comment:
        raise HTTPException(422, "Расскажите, кто вы и к каким результатам нужен доступ")
    if any("\x00" in value for value in (email, comment)):
        raise HTTPException(422, "В заявке есть недопустимые символы")
    salt = secrets.token_bytes(16)
    verifier = hash_password(password, salt)
    with connect() as db:
        repository.create(db, email, comment, salt.hex(), verifier)


def page(status, limit, offset):
    with connect() as db:
        records = repository.page(db, status, limit + 1, offset)
    return {"items": records[:limit], "has_more": len(records) > limit}


def available_results(db, run_ids):
    chosen = list(dict.fromkeys(run_ids))
    if not chosen:
        return chosen
    rows = db.execute("""SELECT j.id FROM jobs j JOIN batches b ON b.id=j.batch_id
        WHERE j.id=ANY(%s) AND j.status IN ('completed','completed_with_errors') AND b.delete_state='active'""",
        (chosen,)).fetchall()
    if len(rows) != len(chosen):
        raise HTTPException(409, "Один из выбранных результатов уже недоступен")
    return chosen


def decide(request_id, approved, run_ids=()):
    with connect() as db:
        application = repository.pending_for_update(db, request_id)
        if application is None:
            raise HTTPException(404, "Заявка не найдена")
        if application["status"] != "pending":
            raise HTTPException(409, "Заявка уже рассмотрена")
        if approved:
            chosen = available_results(db, run_ids)
            user = repository.create_viewer(db, application)
            if user is None:
                raise HTTPException(409, "Аккаунт с этой почтой уже существует")
            if chosen:
                repository.grant_results(db, user["id"], chosen)
        return repository.decide(db, request_id, "approved" if approved else "rejected")


def grants(request_id, run_ids=None):
    with connect() as db:
        application = repository.pending_for_update(db, request_id)
        if application is None or application["status"] != "approved":
            raise HTTPException(404, "Одобренная заявка не найдена")
        email = application["email"]
        if run_ids is not None and not repository.replace_grants(db, email, available_results(db, run_ids)):
            raise HTTPException(404, "Аккаунт не найден")
        return {"items": repository.list_grants(db, email)}
