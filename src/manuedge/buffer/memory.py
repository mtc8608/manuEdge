"""RAM-only store-and-forward buffer.

Thread-safe. Volatile by design — the current prototype default. When the buffer
is full (``max_records``) the oldest queued records are dropped to bound memory;
this is logged so silent data loss never looks like full coverage.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Sequence

from .base import Batch, Buffer, Record

log = logging.getLogger(__name__)


class MemoryBuffer(Buffer):
    def __init__(self, max_records: int = 500_000):
        self.max_records = max_records
        self._queue: deque[Record] = deque()
        self._inflight: dict[int, list[Record]] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def append(self, records: Sequence[Record]) -> None:
        with self._lock:
            self._queue.extend(records)
            overflow = len(self._queue) - self.max_records
            if overflow > 0:
                for _ in range(overflow):
                    self._queue.popleft()
                log.warning("buffer full: dropped %d oldest records", overflow)

    def drain(self, max_records: int) -> Batch | None:
        with self._lock:
            if not self._queue:
                return None
            n = min(max_records, len(self._queue))
            records = [self._queue.popleft() for _ in range(n)]
            batch_id = self._next_id
            self._next_id += 1
            self._inflight[batch_id] = records
            return Batch(id=batch_id, records=records)

    def ack(self, batch_id: int) -> None:
        with self._lock:
            self._inflight.pop(batch_id, None)

    def nack(self, batch_id: int) -> None:
        with self._lock:
            records = self._inflight.pop(batch_id, None)
            if records:
                self._queue.extendleft(reversed(records))

    def pending(self) -> int:
        with self._lock:
            return len(self._queue) + sum(len(r) for r in self._inflight.values())
