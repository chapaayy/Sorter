"""Public access requests and atomic owner moderation."""
import re
import secrets
from fastapi import HTTPException
from ..auth import hash_password
from ..database import connect
from ..db.repositories import access_requests as repository

EMAIL = re.compile(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+")


def credentials(email, password, confirmation):
    email = email.strip().lower()
    if len(email) > 254 or "\x00" in email or not EMAIL.fullmatch(email):
        raise HTTPException(422, "Укажите корректный адрес электронной почты")
    if password != confirmation:
        raise HTTPException(422, "Пароли не совпадают")
    if not 12 <= len(password) <= 256 or "\x00" in password:
        raise HTTPException(422, "Пароль должен содержать от 12 до 256 символов")
    return email


def submit(email, password, confirmation, comment):
    email, comment = credentials(email, password, confirmation), comment.strip()
    if not comment:
        raise HTTPException(422, "Расскажите, кто вы и к каким результатам нужен доступ")
    if any("\x00" in value for value in (email, comment)):
        raise HTTPException(422, "В заявке есть недопустимые символы")
    salt = secrets.token_bytes(16)
    verifier = hash_password(password, salt)
    with connect() as db:
        if not db.execute("SELECT enabled FROM account_registration WHERE singleton FOR SHARE").fetchone()["enabled"]:
            raise HTTPException(403,"Подача заявок отключена")
        repository.lock_email(db, email)
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


def decide(request_id, approved, run_ids=(), *, role_id='observer',display_name='',storage_limit_bytes=None,overrides=None,actor='admin'):
    from . import accounts
    with connect() as db:
        accounts.lock(db)
        acting=accounts.authority(db,actor,'accounts.approve')
        if run_ids:accounts.require(acting,'accounts.grants')
        if run_ids and not accounts.is_owner(acting) and not all(acting['permissions'].get(k)=='all' for k in ('results.view','results.media','results.zip')):raise HTTPException(403,'Нельзя выдавать чужие отчёты')
        application = repository.pending_for_update(db, request_id)
        if application is None:
            raise HTTPException(404, "Заявка не найдена")
        if application["status"] != "pending":
            raise HTTPException(409, "Заявка уже рассмотрена")
        if approved:
            chosen = available_results(db, run_ids)
            user = repository.create_viewer(db, application["email"],
                                            application["password_salt"], application["password_hash"])
            if user is None:
                raise HTTPException(409, "Аккаунт с этой почтой уже существует")
            accounts.configure_new(db,user['id'],role_id,display_name,storage_limit_bytes,overrides or {},acting=acting)
            if chosen:
                repository.grant_results(db, user["id"], chosen)
        accounts.audit(db,actor,request_id,'application_approved' if approved else 'application_rejected',{'role':role_id} if approved else {})
        return repository.decide(db, request_id, "approved" if approved else "rejected")


def grants(request_id, run_ids=None,*,actor='admin'):
    from . import accounts
    with connect() as db:
        accounts.lock(db)
        acting=accounts.authority(db,actor,'accounts.grants')
        if not accounts.is_owner(acting) and not all(acting['permissions'].get(k)=='all' for k in ('results.view','results.media','results.zip')):raise HTTPException(403,'Недостаточно прав на результаты')
        application = repository.pending_for_update(db, request_id)
        if application is None or application["status"] != "approved":
            raise HTTPException(404, "Одобренная заявка не найдена")
        email = application["email"]
        user=db.execute('SELECT id FROM users WHERE username=%s',(email,)).fetchone()
        if not user:raise HTTPException(404,'Аккаунт не найден')
        accounts.target(db,user['id'],acting)
        if run_ids is not None and not repository.replace_grants(db, email, available_results(db, run_ids)):
            raise HTTPException(404, "Аккаунт не найден")
        if run_ids is not None:accounts.audit(db,actor,request_id,"result_grants_changed",{"count":len(run_ids)})
        return {"items": repository.list_grants(db, email)}
