"""Tiny synchronous Observer bus: services emit domain events, NotificationService reacts (loose coupling)."""
from __future__ import annotations

import logging

log = logging.getLogger("proofhire.events")


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list] = {}

    def subscribe(self, name: str, fn):
        self._handlers.setdefault(name, []).append(fn)

    def emit(self, name: str, ctx, **payload):
        for fn in self._handlers.get(name, []):
            try:
                fn(ctx, **payload)
            except Exception:  # an observer must never break the action that triggered it
                log.exception("event handler failed for %s", name)
