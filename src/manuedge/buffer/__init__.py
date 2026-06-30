"""Store-and-forward buffer — the most important reliability piece.

Swappable backend (config ``buffer.backend``):
  * ``memory``     — RAM-only (current default). Volatile: a power blip loses the
                     unacked window. Fine for bench/prototype.
  * ``sqlite_ssd`` — (future) SQLite WAL on the USB SSD; durable across reboots.

The uplink drains the buffer and acks on success; nack re-queues for retry.
"""

from __future__ import annotations

from .base import Batch, Buffer

__all__ = ["Buffer", "Batch", "build_buffer"]


def build_buffer(config: dict) -> Buffer:
    backend = config.get("backend", "memory")
    if backend == "memory":
        from .memory import MemoryBuffer

        return MemoryBuffer(max_records=config.get("max_records", 500_000))
    if backend in ("sqlite_ssd", "sqlite_sd"):
        raise NotImplementedError(
            f"buffer backend {backend!r} not implemented yet; use 'memory' for now"
        )
    raise ValueError(f"unknown buffer backend {backend!r}")
