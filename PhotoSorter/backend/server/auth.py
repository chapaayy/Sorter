"""Environment-backed owner login and server-side hashed sessions."""
from __future__ import annotations
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Request
from .database import connect
from .security.login_throttle import limiter

SESSION_DAYS = 7
COOKIE_NAME = 'photosorter_session'


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=2**14,r=8,p=1,dklen=32).hex()


def bootstrap_admin():
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not 16 <= len(password) <= 256:
        raise RuntimeError('Set ADMIN_PASSWORD in .env (16–256 characters)')
    with connect() as db:
        db.execute("""INSERT INTO users(username,access_role) VALUES ('admin','owner')
            ON CONFLICT (username) DO UPDATE SET access_role='owner'""")
        # One API process serves sessions. Invalidate on boot so a rotation never
        # leaves live owner cookies and no password verifier needs to be persisted.
        db.execute("DELETE FROM sessions USING users WHERE sessions.user_id=users.id AND users.username='admin'")


def login(username: str, password: str, client_key: str = "") -> str:
    username = username.strip()
    if '@' in username:
        username = username.lower()
    limiter.check(username, client_key)
    with connect() as db:
        user=db.execute('SELECT * FROM users WHERE username=%s',(username,)).fetchone()
        if username == 'admin':
            configured = os.environ.get('ADMIN_PASSWORD', '')
            # Compare fixed-length digests in memory only, never store the owner password or digest.
            matches = hmac.compare_digest(hashlib.sha256(password.encode()).digest(),
                                          hashlib.sha256(configured.encode()).digest())
            valid = 16 <= len(configured) <= 256 and matches
        else:
            # Preserve any other existing accounts and avoid timing based on their existence.
            salt=bytes.fromhex(user['password_salt']) if user and user['password_salt'] else b'0'*16
            candidate=hash_password(password,salt)
            stored = user['password_hash'] if user else None
            valid = hmac.compare_digest(candidate, stored or '0'*64) and bool(stored and user['password_salt'])
        if not user or not valid:
            limiter.fail(username,client_key)
            raise HTTPException(401,'Неправильный логин или пароль')
        token=secrets.token_urlsafe(40)
        db.execute('DELETE FROM sessions WHERE expires_at < now()')
        db.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                   (hashlib.sha256(token.encode()).hexdigest(),user['id'],
                    datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)))
        limiter.succeed(username,client_key)
        return token


def authenticate(request:Request):
    token=request.cookies.get(COOKIE_NAME)
    if not token: raise HTTPException(401,'Необходим вход')
    with connect() as db:
        row=db.execute('SELECT u.id,u.username,u.access_role FROM sessions s JOIN users u ON u.id=s.user_id '
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
