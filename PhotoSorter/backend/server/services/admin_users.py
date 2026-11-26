"""Owner-managed viewer accounts using the same grants as approved applications."""
import secrets
import re

from fastapi import HTTPException

from ..auth import hash_password
from ..database import connect
from ..db.repositories import access_requests as repository
from .access_requests import available_results, credentials


def list_users(limit, offset):
    with connect() as db:
        rows = repository.list_users(db, limit + 1, offset)
    return {"items": rows[:limit], "has_more": len(rows) > limit}


def create(email, password, confirmation, run_ids, *, role_id='observer',display_name='',storage_limit_bytes=None,overrides=None,actor='admin'):
    email=email.strip()
    if '@' in email:email=credentials(email,password,confirmation)
    else:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,119}',email) or email.lower()=='admin':raise HTTPException(422,'Некорректный или зарезервированный логин')
        if password!=confirmation or not 12<=len(password)<=256 or '\x00' in password:raise HTTPException(422,'Проверьте пароль и подтверждение')
    salt = secrets.token_bytes(16)
    verifier = hash_password(password, salt)
    from . import accounts
    with connect() as db:
        accounts.lock(db)
        acting=accounts.authority(db,actor,'accounts.create')
        if run_ids:accounts.require(acting,'accounts.grants')
        if run_ids and not accounts.is_owner(acting) and not all(acting['permissions'].get(k)=='all' for k in ('results.view','results.media','results.zip')):raise HTTPException(403,'Нельзя выдавать чужие отчёты')
        repository.lock_email(db, email)
        # Same row-before-user order as approval. Never reuse an applicant's
        # password or allow approval to overwrite the owner's chosen password.
        pending = repository.pending_by_email(db, email)
        chosen = available_results(db, run_ids)
        user = repository.create_viewer(db, email, salt.hex(), verifier)
        if user is None:
            raise HTTPException(409, "Аккаунт с этой почтой уже существует")
        accounts.configure_new(db,user['id'],role_id,display_name,storage_limit_bytes,overrides or {},acting=acting)
        accounts.audit(db,actor,user['id'],'account_created',{'role':role_id,'limit':storage_limit_bytes})
        if chosen:
            repository.grant_results(db, user["id"], chosen)
        if pending:
            repository.decide(db, pending["id"], "approved")
            accounts.audit(db,actor,pending['id'],'application_approved',{'user_id':user['id']})
        return user


def grants(user_id, run_ids=None,*,actor='admin'):
    from . import accounts
    with connect() as db:
        accounts.lock(db)
        acting=accounts.authority(db,actor,'accounts.grants')
        accounts.target(db,user_id,acting)
        if not accounts.is_owner(acting) and not all(acting['permissions'].get(k)=='all' for k in ('results.view','results.media','results.zip')):raise HTTPException(403,'Недостаточно прав на результаты')
        email = repository.user_email(db, user_id)
        if email is None:
            raise HTTPException(404, "Пользователь не найден")
        if run_ids is not None and not repository.replace_grants(db, email, available_results(db, run_ids)):
            raise HTTPException(404, "Пользователь не найден")
        if run_ids is not None:accounts.audit(db,actor,user_id,"result_grants_changed",{"count":len(run_ids)})
        return {"items": repository.list_grants(db, email)}
