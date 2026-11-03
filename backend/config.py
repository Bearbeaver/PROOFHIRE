"""Application configuration (env-driven; nothing secret is hard-coded)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    instance_dir: Path = ROOT / "instance"
    db_path: Path | None = None
    upload_dir: Path | None = None
    secret: str | None = None
    engine_url: str = "http://127.0.0.1:5001"
    engine_key: str = "dev-engine-key"
    engine_timeout_s: float = 45.0
    scorer: str = "http"                 # http | mock
    seed_demo: bool = True
    start_worker: bool = True
    token_ttl_min: int = 60
    file_url_ttl_s: int = 300
    max_retries: int = 5
    backoff_base_s: float = 2.0
    max_upload_mb: int = 5
    default_max_resubmissions: int = 2
    assessment_valid_days: int = 180
    assessment_due_soon_days: int = 14
    assessment_pass_ratio: float = 0.75
    login_max_failures: int = 5
    login_window_s: int = 900

    @classmethod
    def from_env(cls) -> "Config":
        c = cls()
        c.instance_dir = Path(os.environ.get("PROOFHIRE_INSTANCE", str(c.instance_dir)))
        c.engine_url = os.environ.get("ENGINE_URL", c.engine_url)
        c.engine_key = os.environ.get("ENGINE_KEY", c.engine_key)
        c.scorer = os.environ.get("PROOFHIRE_SCORER", c.scorer)
        c.seed_demo = _flag("PROOFHIRE_SEED_DEMO", True)
        c.secret = os.environ.get("PROOFHIRE_SECRET")
        c.token_ttl_min = int(os.environ.get("PROOFHIRE_TOKEN_TTL_MIN", c.token_ttl_min))
        return c

    def finalize(self) -> "Config":
        self.instance_dir = Path(self.instance_dir)
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self.db_path or self.instance_dir / "proofhire.db")
        self.upload_dir = Path(self.upload_dir or self.instance_dir / "uploads")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if not self.secret:  # persisted so restarts do not invalidate every session
            keyfile = self.instance_dir / "secret.key"
            if not keyfile.exists():
                keyfile.write_text(secrets.token_hex(32))
                try:
                    keyfile.chmod(0o600)
                except OSError:
                    pass
            self.secret = keyfile.read_text().strip()
        return self
