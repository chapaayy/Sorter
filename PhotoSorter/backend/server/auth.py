"""Single-admin password login, server-side hashed sessions, strict cookie boundaries."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from .database import connect

SESSION_DAYS = 7
COOKIE_NAME = 'photosorter_session'


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=2**14,r=8,p=1,dklen=32).hex()


def bootstrap_admin():
    initial = os.environ.get('ADMIN_PASSWORD','')
    if len(initial) < 16: raise RuntimeError('ADMIN_PASSWORD missing or too short')
    with connect() as db:
        if db.execute('SELECT id FROM users LIMIT 1').fetchone(): return
        salt=secrets.token_bytes(16)
        db.execute('INSERT INTO users(username,password_salt,password_hash) VALUES (%s,%s,%s)',
                   ('admin',salt.hex(),hash_password(initial,salt)))


def login(username: str, password: str) -> str:
    with connect() as db:
        user=db.execute('SELECT * FROM users WHERE username=%s',(username,)).fetchone()
        # Match timing regardless of account existence.
        salt=bytes.fromhex(user['password_salt']) if user else b'0'*16
        candidate=hash_password(password,salt)
        if not user or not hmac.compare_digest(candidate,user['password_hash']):
            raise HTTPException(401,'Неправильный логин или пароль')
        token=secrets.token_urlsafe(40)
        db.execute('DELETE FROM sessions WHERE expires_at < now()')
        db.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                   (hashlib.sha256(token.encode()).hexdigest(),user['id'],
                    datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)))
        return token


def authenticate(request:Request):
    token=request.cookies.get(COOKIE_NAME)
    if not token: raise HTTPException(401,'Необходим вход')
    with connect() as db:
        row=db.execute('SELECT u.username FROM sessions s JOIN users u ON u.id=s.user_id '
                       'WHERE s.token_hash=%s AND s.expires_at>now()',
                       (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row: raise HTTPException(401,'Сессия истекла')
        return row


def logout(request:Request):
    token=request.cookies.get(COOKIE_NAME)
    if token:
        with connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=%s',
                       (hashlib.sha256(token.encode()).hexdigest(),))


def check_origin(request:Request):
    """Block cross-site state-changing requests even if browser sends cookies."""
    if request.method in ('GET','HEAD','OPTIONS'): return
    origin=request.headers.get('origin')
    expected='https://'+os.environ['DOMAIN'].lower()
    if origin and origin.lower()!=expected:raise HTTPException(403,'Недопустимый Origin')
    # Browsers send Sec-Fetch-Site for fetch/form requests; reject cross-site.
    if request.headers.get('sec-fetch-site','') == 'cross-site':
        raise HTTPException(403,'Cross-site request blocked')
