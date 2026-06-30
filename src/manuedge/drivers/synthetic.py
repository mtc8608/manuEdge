"""Synthetic driver — generates sine waveforms for testing the whole pipeline.

No hardware needed. Lets you exercise sampler → buffer → uplink → heartbeat on
any machine. Each configured stream emits a continuous sine (phase derived from
wall clock so segments stitch seamlessly across gaps).
"""

from __future__ import annotations

import math
import time
from typing import Iterator

from ..modality import get as get_modality
from .base import Driver, RawSample, StreamSpec


def _now_us() -> int:
    return time.time_ns() // 1000


class SyntheticDriver(Driver):
    name = "synthetic"

    def __init__(self, config: dict):
        self.cfg = config
        self.loop_hz = float(config.get("loop_hz", 50.0))
        # streams: [{modality, amplitude, offset, cycle_s, stream_id?}]
        self.streams = config.get("streams", [])
        self._open = False

    def describe(self) -> list[StreamSpec]:
        specs: list[StreamSpec] = []
        for s in self.streams:
            m = get_modality(s["modality"])
            specs.append(
                StreamSpec(
                    stream_id=s.get("stream_id", f"{self.name}:{m.modality}"),
                    modality=m.modality,
                    hz=self.loop_hz,
                    group=m.group,
                    units=m.units,
                    metric=m.metric,
                    source=self.name,
                )
            )
        return specs

    def start(self) -> None:
        self._open = True

    def stop(self) -> None:
        self._open = False

    def read(self) -> Iterator[RawSample]:
        if not self._open:
            raise RuntimeError("call start() before read()")
        specs = self.describe()
        period = 1.0 / self.loop_hz
        while self._open:
            cycle_start = time.perf_counter()
            t_us = _now_us()
            t_s = t_us / 1e6
            for cfg, spec in zip(self.streams, specs):
                amp = float(cfg.get("amplitude", 1.0))
                offset = float(cfg.get("offset", 0.0))
                cycle_s = float(cfg.get("cycle_s", 1.0))
                value = offset + amp * math.sin(2 * math.pi * (t_s % cycle_s) / cycle_s)
                yield RawSample(spec.stream_id, value, t_us)
            elapsed = time.perf_counter() - cycle_start
            if elapsed < period:
                time.sleep(period - elapsed)
