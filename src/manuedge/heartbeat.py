"""Heartbeat — the frontend's "is it alive" signal.

Periodically posts node health: online, CPU temp, disk free, agent version,
buffer backlog, and last-sample-time per stream. Sent outbound like everything
else.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from pathlib import Path

import httpx

from . import __version__
from .buffer.base import Buffer
from .config import AgentConfig
from .sampler import Sampler

log = logging.getLogger(__name__)

_THERMAL = Path("/sys/class/thermal/thermal_zone0/temp")


def _cpu_temp_c() -> float | None:
    try:
        return int(_THERMAL.read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _disk_free_bytes(path: str = "/") -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return -1


class Heartbeat:
    def __init__(self, config: AgentConfig, sampler: Sampler, buffer: Buffer):
        self.config = config
        self.sampler = sampler
        self.buffer = buffer
        self._endpoint = config.server.url.rstrip("/") + "/api/telemetry/heartbeat"

    def snapshot(self) -> dict:
        return {
            "node_id": self.config.node_id,
            "ts_ms": time.time_ns() // 1_000_000,
            "agent_version": __version__,
            "cpu_temp_c": _cpu_temp_c(),
            "disk_free_bytes": _disk_free_bytes(),
            "buffer_pending": self.buffer.pending(),
            "last_sample_us": self.sampler.last_sample_us(),
        }

    async def run(self) -> None:
        async with httpx.AsyncClient(
            verify=self.config.server.verify_tls, timeout=15.0
        ) as client:
            headers = {}
            if self.config.server.enrollment_token:
                headers["Authorization"] = f"Bearer {self.config.server.enrollment_token}"
            while True:
                try:
                    await client.post(self._endpoint, json=self.snapshot(), headers=headers)
                except Exception as exc:
                    log.debug("heartbeat post failed: %s", exc)
                await asyncio.sleep(self.config.heartbeat.interval_s)
