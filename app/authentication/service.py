import hashlib
import hmac
import secrets
import time
from app.database.connection import connection
from app.utils.errors import ServiceError

SESSION_COOKIE = "market_session"
CSRF_COOKIE = "market_csrf"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class SessionService:
    def __init__(self, settings): self.settings = settings

    def issue(self, person_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with connection(self.settings.database_path, write=True) as conn:
            conn.execute("DELETE FROM customer_sessions WHERE expires_at<=?", (int(time.time()),))
            conn.execute("INSERT INTO customer_sessions VALUES(?,?,?,?)", (digest(token), person_id, digest(csrf), int(time.time())+self.settings.session_ttl_seconds))
        return token, csrf

    def authenticate(self, token, csrf=None, write=False):
        if not token: raise ServiceError(401, "Sign in to continue")
        with connection(self.settings.database_path) as conn:
            row = conn.execute("SELECT * FROM customer_sessions WHERE token_hash=? AND expires_at>?", (digest(token), int(time.time()))).fetchone()
        if not row: raise ServiceError(401, "Session expired; sign in again")
        if write and (not csrf or not hmac.compare_digest(digest(csrf), row["csrf_hash"])):
            raise ServiceError(403, "Invalid request confirmation token")
        return row["person_id"]

    def revoke(self, token):
        with connection(self.settings.database_path, write=True) as conn:
            conn.execute("DELETE FROM customer_sessions WHERE token_hash=?", (digest(token),))

    def cookies(self, response, person_id):
        token, csrf = self.issue(person_id)
        options = {"secure": self.settings.session_cookie_secure, "samesite": "strict", "max_age": self.settings.session_ttl_seconds, "path": "/"}
        response.set_cookie(SESSION_COOKIE, token, httponly=True, **options)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=False, **options)
