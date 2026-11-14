"""Persistence for access applications. Never return password fields in the inbox."""
from uuid import uuid4

PUBLIC_FIELDS = "id,email,comment,status,created_at,decided_at"


def create(db, email, comment, salt, verifier):
    db.execute("""INSERT INTO access_requests(id,email,comment,password_salt,password_hash)
        SELECT %s,%s,%s,%s,%s WHERE NOT EXISTS(SELECT 1 FROM users WHERE username=%s)
        ON CONFLICT (email) WHERE status='pending' DO NOTHING""",
        (uuid4(), email, comment, salt, verifier, email))


def page(db, status, limit, offset):
    return db.execute(f"""SELECT {PUBLIC_FIELDS} FROM access_requests WHERE status=%s
        ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s""", (status, limit, offset)).fetchall()


def pending_for_update(db, request_id):
    return db.execute("SELECT * FROM access_requests WHERE id=%s FOR UPDATE", (request_id,)).fetchone()


def create_viewer(db, application):
    return db.execute("""INSERT INTO users(username,password_salt,password_hash,access_role)
        VALUES (%s,%s,%s,'viewer') ON CONFLICT(username) DO NOTHING RETURNING id""",
        (application["email"], application["password_salt"], application["password_hash"])).fetchone()


def grant_results(db, user_id, run_ids):
    with db.cursor() as cur:
        cur.executemany("INSERT INTO result_access_grants(user_id,run_id) VALUES (%s,%s)",
                        [(user_id, run_id) for run_id in run_ids])


def list_grants(db, email):
    return db.execute("""SELECT j.id,j.status,j.finished_at,b.display_name FROM result_access_grants g
        JOIN users u ON u.id=g.user_id JOIN jobs j ON j.id=g.run_id JOIN batches b ON b.id=j.batch_id
        WHERE u.username=%s AND j.status IN ('completed','completed_with_errors') AND b.delete_state='active'
        ORDER BY j.finished_at DESC NULLS LAST,j.id DESC""", (email,)).fetchall()


def replace_grants(db, email, run_ids):
    user = db.execute("""SELECT id FROM users WHERE username=%s AND access_role='viewer' FOR UPDATE""",
                      (email,)).fetchone()
    if user is None:
        return False
    db.execute("DELETE FROM result_access_grants WHERE user_id=%s", (user["id"],))
    if run_ids:
        grant_results(db, user["id"], run_ids)
    return True


def decide(db, request_id, status):
    return db.execute(f"""UPDATE access_requests SET status=%s,decided_at=now(),
        password_salt=NULL,password_hash=NULL WHERE id=%s RETURNING {PUBLIC_FIELDS}""",
        (status, request_id)).fetchone()
