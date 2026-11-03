"""Password hashing, JWT issuing/verification, time-limited file tokens and login throttling."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

from .errors import ApiError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(pw: str) -> str:
    return generate_password_hash(pw, method="scrypt")  # salted, memory-hard


def verify_password(pw: str, hashed: str) -> bool:
    return check_password_hash(hashed, pw)


def validate_password(pw: str):
    if not isinstance(pw, str) or len(pw) < 8:
        raise ApiError("INVALID_PASSWORD", "Password must be at least 8 characters.", 400, {"field": "password"})
    if len(pw) > 128:
        raise ApiError("INVALID_PASSWORD", "Password is too long.", 400, {"field": "password"})


class TokenService:
    def __init__(self, secret: str, ttl_min: int, file_ttl_s: int):
        self.secret, self.ttl_min, self.file_ttl_s = secret, ttl_min, file_ttl_s

    def issue(self, user_id: str, role: str) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode({"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(minutes=self.ttl_min), "typ": "access"},
                          self.secret, algorithm="HS256")

    def verify(self, token: str, typ: str = "access") -> dict:
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise ApiError("TOKEN_EXPIRED", "Your session has expired. Please log in again.", 401)
        except jwt.InvalidTokenError:
            raise ApiError("TOKEN_INVALID", "Invalid authentication token.", 401)
        if claims.get("typ") != typ:
            raise ApiError("TOKEN_INVALID", "Invalid authentication token.", 401)
        return claims

    def issue_file_token(self, evidence_id: str, file_ref: str, file_name: str) -> str:
        now = datetime.now(timezone.utc)
        return jwt.encode({"typ": "file", "eid": evidence_id, "ref": file_ref, "name": file_name,
                           "exp": now + timedelta(seconds=self.file_ttl_s)}, self.secret, algorithm="HS256")


class LoginThrottle:
    """In-memory brute-force guard: N failures per window per (email, ip)."""

    def __init__(self, max_failures: int, window_s: int):
        self.max, self.window = max_failures, window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key):
        cutoff = time.time() - self.window
        self._fails[key] = [t for t in self._fails.get(key, []) if t > cutoff]

    def check(self, key: str):
        with self._lock:
            self._prune(key)
            if len(self._fails[key]) >= self.max:
                raise ApiError("TOO_MANY_ATTEMPTS", "Too many failed log-in attempts. Try again in a few minutes.", 429)

    def fail(self, key: str):
        with self._lock:
            self._prune(key)
            self._fails[key].append(time.time())

    def reset(self, key: str):
        with self._lock:
            self._fails.pop(key, None)
