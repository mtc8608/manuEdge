"""manuEdge entry point — wires the agent together and runs it.

Layout:
  * the **sampler** runs the (blocking) driver in its own thread, appending
    completed segments to the buffer;
  * **uplink** and **heartbeat** run as asyncio tasks, draining the buffer and
    reporting health.

systemd manages the process (Restart=always); ``sd_notify`` tells systemd we're
ready and keeps the watchdog happy if WatchdogSec is set.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket

from .buffer import build_buffer
from .config import KNOWN_PI_MODELS, AgentConfig
from .config_agent import ConfigAgent
from .drivers import build_driver
from .heartbeat import Heartbeat
from .sampler import Sampler
from .uplink import Uplink

log = logging.getLogger("manuedge")


def _sd_notify(state: str) -> None:
    """Minimal sd_notify (no python-systemd dependency)."""
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr.startswith("@"):  # abstract namespace
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(state.encode())
    except OSError:
        pass


async def amain(config_path: str | None) -> None:
    config = AgentConfig.from_file(config_path)
    config = await ConfigAgent(config).pull()

    if config.pi_model not in KNOWN_PI_MODELS:
        log.warning(
            "unrecognized pi_model %r (expected one of %s) — proceeding anyway",
            config.pi_model, sorted(KNOWN_PI_MODELS),
        )
    # RAM-only buffer: a Pi 3B+ has only ~1 GB RAM vs 2-8 GB on a Pi 4 — flag an
    # unrealistic ceiling now rather than let it OOM mid-shift.
    max_records = config.buffer.get("max_records", 500_000)
    if config.pi_model == "pi3" and max_records > 150_000:
        log.warning(
            "buffer.max_records=%d may be too high for a Pi 3B+'s 1 GB RAM; "
            "consider lowering it in agent.toml", max_records,
        )

    if not config.drivers:
        raise SystemExit("no drivers configured; add a [[drivers]] block to agent.toml")

    buffer = build_buffer(config.buffer)

    # P0/P1: a single driver. The loop is ready for more.
    driver_cfg = config.drivers[0]
    driver = build_driver(driver_cfg["name"], driver_cfg)
    sampler = Sampler(driver, buffer, **config.sampler)
    sampler.start()
    log.info("sampler started: %s", [s.stream_id for s in driver.describe()])

    uplink = Uplink(config, buffer)
    heartbeat = Heartbeat(config, sampler, buffer)

    _sd_notify("READY=1")
    log.info("manuEdge node %s online → %s", config.node_id, config.server.url)
    try:
        await asyncio.gather(uplink.run(), heartbeat.run())
    finally:
        sampler.stop()


def run() -> None:
    parser = argparse.ArgumentParser(prog="manuedge")
    parser.add_argument("-c", "--config", default=os.environ.get("MANUEDGE_CONFIG"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(amain(args.config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run()
