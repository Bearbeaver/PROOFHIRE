"""One error format for every endpoint: {"error": {"code", "message", "details"}}."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

    def to_dict(self):
        out = {"code": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return {"error": out}


def not_found(what="Resource"):
    return ApiError("NOT_FOUND", f"{what} not found.", 404)


def forbidden(msg="You do not have access to this resource."):
    return ApiError("FORBIDDEN", msg, 403)
