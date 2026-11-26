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
from .security.roles import effective

SESSION_DAYS = 7
COOKIE_NAME = 'photosorter_session'


def hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=2**14,r=8,p=1,dklen=32).hex()


def bootstrap_admin():
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not 16 <= len(password) <= 256:
        raise RuntimeError('Set ADMIN_PASSWORD in .env (16–256 characters)')
    with connect() as db:
        owner_id=db.execute("""INSERT INTO users(username,access_role,role_id) VALUES ('admin','owner','owner')
            ON CONFLICT (username) DO UPDATE SET access_role='owner',role_id='owner',blocked=false RETURNING id""").fetchone()['id']
        marker=db.execute("SELECT salt,fingerprint FROM owner_session_credential WHERE user_id=%s",
                          (owner_id,)).fetchone()
        if marker and hmac.compare_digest(marker['fingerprint'],hash_password(password,bytes.fromhex(marker['salt']))):
            return
        # Existing, unmarked sessions cannot be tied to a particular password.
        # Revoke them on first upgrade, then revoke only on rotation.
        salt=secrets.token_bytes(16)
        db.execute("""INSERT INTO owner_session_credential(user_id,salt,fingerprint) VALUES (%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET salt=EXCLUDED.salt,fingerprint=EXCLUDED.fingerprint""",
            (owner_id,salt.hex(),hash_password(password,salt)))
        db.execute("DELETE FROM sessions WHERE user_id=%s",(owner_id,))


def login(username: str, password: str, client_key: str = "") -> str:
    username = username.strip()
    if '@' in username:
        username = username.lower()
    limiter.check(username, client_key)
    with connect() as db:
        user=db.execute('SELECT * FROM users WHERE username=%s FOR UPDATE',(username,)).fetchone()
        if username == 'admin':
            configured = os.environ.get('ADMIN_PASSWORD', '')
            # Login compares fixed-length digests only in memory and uses .env as its source of truth.
            matches = hmac.compare_digest(hashlib.sha256(password.encode()).digest(),
                                          hashlib.sha256(configured.encode()).digest())
            valid = 16 <= len(configured) <= 256 and matches
        else:
            # Preserve any other existing accounts and avoid timing based on their existence.
            salt=bytes.fromhex(user['password_salt']) if user and user['password_salt'] else b'0'*16
            candidate=hash_password(password,salt)
            stored = user['password_hash'] if user else None
            valid = hmac.compare_digest(candidate, stored or '0'*64) and bool(stored and user['password_salt'])
        if not user or not valid or user['blocked']:
            limiter.fail(username,client_key)
            raise HTTPException(401,'Неправильный логин или пароль')
        token=secrets.token_urlsafe(40)
        db.execute('DELETE FROM sessions WHERE expires_at < now()')
        db.execute('INSERT INTO sessions(token_hash,user_id,expires_at,created_at) VALUES (%s,%s,%s,now())',
                   (hashlib.sha256(token.encode()).hexdigest(),user['id'],
                    datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)))
        db.execute('UPDATE users SET last_login_at=now() WHERE id=%s',(user['id'],))
        limiter.succeed(username,client_key)
        return token


def authenticate(request:Request):
    token=request.cookies.get(COOKIE_NAME)
    if not token: raise HTTPException(401,'Необходим вход')
    with connect() as db:
        row=db.execute('SELECT u.id,u.username,u.access_role,u.role_id,u.display_name,u.permission_overrides,r.permissions AS role_permissions '
                       'FROM sessions s JOIN users u ON u.id=s.user_id JOIN account_roles r ON r.id=u.role_id '
                       'WHERE s.token_hash=%s AND s.expires_at>now() AND NOT u.blocked',
                       (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row: raise HTTPException(401,'Сессия истекла')
        row['permissions']=effective(row.pop('role_permissions'),row.pop('permission_overrides'))
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
