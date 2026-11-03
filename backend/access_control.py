"""AccessControlFilter: authentication (JWT) + role-based authorisation on every protected request (FR10, NFR2)."""
from __future__ import annotations

from functools import wraps

from flask import current_app, g, request

from .errors import ApiError, forbidden


def require_auth(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer ") or len(header) < 20:
                raise ApiError("UNAUTHENTICATED", "Please log in to continue.", 401)
            claims = current_app.extensions["proofhire"].tokens.verify(header[7:])
            user = g.svc.users.find(claims["sub"])
            if not user:
                raise ApiError("UNAUTHENTICATED", "Please log in to continue.", 401)
            if user["status"] != "ACTIVE":
                raise ApiError("ACCOUNT_" + user["status"], "This account has been " + user["status"].lower() + ".", 403)
            if claims.get("role") != user["role"]:
                raise ApiError("TOKEN_INVALID", "Invalid authentication token.", 401)
            if roles and user["role"] not in roles:
                raise forbidden("Your role cannot use this feature.")
            g.user = user
            return fn(*args, **kwargs)
        return wrapper
    return deco
