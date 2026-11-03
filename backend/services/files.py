"""Certificate file storage (stand-in for object storage). Files are served only through signed, time-limited URLs."""
from __future__ import annotations

import os
import re
import secrets

from ..errors import ApiError

ALLOWED = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8", ".jpeg": b"\xff\xd8", ".txt": None}


class FileStore:
    def __init__(self, ctx):
        self.c = ctx
        self.max_bytes = ctx.cfg.max_upload_mb * 1024 * 1024

    def read_checked(self, fs):
        """Validate an uploaded werkzeug FileStorage; return (bytes, safe_name, ext)."""
        name = os.path.basename(fs.filename or "")
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED:
            raise ApiError("INVALID_FILE", "Certificate files must be PDF, PNG, JPG or TXT.", 400)
        data = fs.stream.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise ApiError("FILE_TOO_LARGE", f"Files can be at most {self.c.cfg.max_upload_mb} MB.", 413)
        if not data:
            raise ApiError("INVALID_FILE", "The uploaded file is empty.", 400)
        magic = ALLOWED[ext]
        if magic and not data.startswith(magic):
            raise ApiError("INVALID_FILE", "The file content does not match its type.", 400)
        safe = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:120] or "certificate" + ext
        return data, safe, ext

    def save(self, data: bytes, ext: str) -> str:
        ref = secrets.token_hex(16) + ext
        with open(self.c.cfg.upload_dir / ref, "wb") as f:
            f.write(data)
        return ref

    def delete(self, ref: str):
        try:
            os.remove(self.c.cfg.upload_dir / ref)
        except OSError:
            pass

    def path(self, ref: str):
        if not re.fullmatch(r"[0-9a-f]{32}\.(pdf|png|jpg|jpeg|txt)", ref or ""):
            raise ApiError("NOT_FOUND", "File not found.", 404)
        p = self.c.cfg.upload_dir / ref
        if not p.exists():
            raise ApiError("NOT_FOUND", "File not found.", 404)
        return p
