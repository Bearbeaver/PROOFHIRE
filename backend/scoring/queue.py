"""Scoring queue: queue-based load levelling with retry/back-off (design Section 8.1, NFR5/NFR6).

In-process worker thread for this deployment. The interface (enqueue / enqueue_with_delay) is what a broker
such as RabbitMQ, SQS or Redis would implement in production. Durability comes from the database: on start-up every
PENDING / QUEUED / RESUBMITTED submission is re-enqueued, so nothing is lost if the process restarts.
"""
from __future__ import annotations

import heapq
import itertools
import logging
import queue
import threading
import time

log = logging.getLogger("proofhire.queue")


class ScoringQueue:
    def __init__(self, handler, start: bool = True):
        self.handler = handler
        self._q: queue.Queue = queue.Queue()
        self._delayed: list = []
        self._seq = itertools.count()
        self._lock = threading.Lock()
        self._queued: set[str] = set()
        self._active = 0
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="scoring-worker", daemon=True)
        if start:
            self.thread.start()

    def enqueue(self, sid: str):
        with self._lock:
            if sid in self._queued:
                return
            self._queued.add(sid)
        self._q.put(sid)

    def enqueue_with_delay(self, sid: str, delay_s: float):
        with self._lock:
            if sid in self._queued:
                return
            self._queued.add(sid)
            heapq.heappush(self._delayed, (time.time() + delay_s, next(self._seq), sid))

    def size(self) -> int:
        with self._lock:
            return len(self._queued)

    def stop(self):
        self._stop.set()

    def _promote_due(self):
        with self._lock:
            while self._delayed and self._delayed[0][0] <= time.time():
                self._q.put(heapq.heappop(self._delayed)[2])

    def _run(self):
        while not self._stop.is_set():
            self._promote_due()
            try:
                sid = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            with self._lock:
                self._queued.discard(sid)  # allow the handler to re-enqueue (retry)
                self._active += 1
            try:
                self.handler(sid)
            except Exception:
                log.exception("scoring handler crashed for %s", sid)
            finally:
                with self._lock:
                    self._active -= 1

    def drain(self, timeout: float = 10.0) -> bool:
        """Test helper: wait until nothing is queued or delayed."""
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                idle = not self._queued and self._q.empty() and self._active == 0
            if idle:
                time.sleep(0.15)
                with self._lock:
                    if not self._queued and self._q.empty() and self._active == 0:
                        return True
            time.sleep(0.05)
        return False
