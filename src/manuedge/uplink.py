"""Uplink — drains the buffer and dials home.

Outbound HTTPS batch POST. Idempotent: the server dedupes on
``(node_id, stream_id, seq)``, so retries and backfill are safe. On failure the
batch is nacked (returned to the queue) and we back off exponentially — the
sampler keeps running and filling the buffer regardless.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .buffer.base import Buffer
from .config import AgentConfig
from .contract import Batch as WireBatch

log = logging.getLogger(__name__)


class Uplink:
    def __init__(self, config: AgentConfig, buffer: Buffer):
        self.config = config
        self.buffer = buffer
        self._endpoint = config.server.url.rstrip("/") + "/api/telemetry/ingest"

    async def run(self) -> None:
        backoff = self.config.uplink.poll_interval_s
        async with httpx.AsyncClient(
            verify=self.config.server.verify_tls, timeout=30.0
        ) as client:
            while True:
                batch = self.buffer.drain(self.config.uplink.batch_records)
                if batch is None:
                    await asyncio.sleep(self.config.uplink.poll_interval_s)
                    continue
                try:
                    await self._post(client, batch.records)
                    self.buffer.ack(batch.id)
                    backoff = self.config.uplink.poll_interval_s  # reset on success
                except Exception as exc:
                    self.buffer.nack(batch.id)
                    log.warning("uplink failed (%s); backing off %.1fs", exc, backoff)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self.config.uplink.max_backoff_s)

    async def _post(self, client: httpx.AsyncClient, records: list) -> None:
        payload = WireBatch(node_id=self.config.node_id, records=records).to_wire()
        headers = {}
        if self.config.server.enrollment_token:
            headers["Authorization"] = f"Bearer {self.config.server.enrollment_token}"
        resp = await client.post(self._endpoint, json=payload, headers=headers)
        resp.raise_for_status()
