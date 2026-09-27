"""The team password, for a Scout that other computers can reach (a server, or behind Vercel).

Set SCOUT_PASSWORD in .env: everyone who opens Scout logs in with it once, and a signed cookie keeps the browser
logged in for 30 days. Without a password Scout only answers this computer (http://localhost), so a server can't
be left open to the internet by mistake.
"""
import hashlib
import hmac
import os
import secrets
import time

from .config import DATA_DIR

COOKIE = "scout_session"
ADMIN_HEADER = "x-scout-admin"
ADMIN_TOKEN_PATH = DATA_DIR / ".admin_token"
MAX_AGE = 30 * 24 * 3600
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")  # set by Vercel, Caddy, nginx...


def password() -> str:
    return os.getenv("SCOUT_PASSWORD", "").strip()


def enabled() -> bool:
    return bool(password())


def _sign(pw: str, expires: int) -> str:
    # The key comes from the password, so changing the password logs every browser out.
    key = hashlib.sha256(b"scout-session\0" + pw.encode()).digest()
    return hmac.new(key, str(expires).encode(), hashlib.sha256).hexdigest()


def new_session() -> str:
    expires = int(time.time()) + MAX_AGE
    return f"{expires}.{_sign(password(), expires)}"


def valid_session(token: str | None) -> bool:
    pw = password()
    expires, _, sig = (token or "").partition(".")
    if not pw or not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(sig, _sign(pw, int(expires)))


def check_password(given: str) -> bool:
    pw = password()
    return bool(pw) and hmac.compare_digest(given.encode(), pw.encode())


def is_local(request) -> bool:
    """A request from this computer itself, not one a proxy passed on."""
    host = request.client.host if request.client else ""
    return host in LOCAL_HOSTS and not any(h in request.headers for h in PROXY_HEADERS)


def admin_token() -> str:
    """A random token in the data folder (readable only by whoever runs Scout). Scripts on the server itself send it
    as X-Scout-Admin to use the API without the team password, e.g. over SSH: curl -H "X-Scout-Admin: $(cat
    data/.admin_token)" http://127.0.0.1:8002/api/..."""
    if not ADMIN_TOKEN_PATH.exists():
        ADMIN_TOKEN_PATH.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            os.chmod(ADMIN_TOKEN_PATH, 0o600)
        except OSError:
            pass
    return ADMIN_TOKEN_PATH.read_text(encoding="utf-8").strip()


def is_admin(request) -> bool:
    given = request.headers.get(ADMIN_HEADER) or ""
    return bool(given) and is_local(request) and hmac.compare_digest(given.encode(), admin_token().encode())
