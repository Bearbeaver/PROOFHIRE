"""SQLite access with explicit transactions. Sessions run hooks (e.g. queue enqueue) only AFTER commit."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


class Session:
    def __init__(self, db: "Database", write: bool):
        self.conn = db.connect()
        self.write = write
        self.hooks = []
        self.closed = False
        if write:
            self.conn.execute("BEGIN IMMEDIATE")

    def on_commit(self, fn):
        self.hooks.append(fn)

    def commit(self):
        if self.closed:
            return
        if self.write:
            self.conn.execute("COMMIT")
        self.closed = True
        self.conn.close()
        hooks, self.hooks = self.hooks, []
        for fn in hooks:
            fn()

    def rollback(self):
        if self.closed:
            return
        if self.write:
            self.conn.execute("ROLLBACK")
        self.closed = True
        self.conn.close()
        self.hooks = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.rollback() if exc_type else self.commit()
        return False


class Database:
    def __init__(self, path):
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self):
        conn = self.connect()
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA.read_text())
        conn.close()

    def session(self, write: bool = True) -> Session:
        return Session(self, write)
