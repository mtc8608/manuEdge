"""Sampler — turns a driver's raw sample stream into Segments.

A ``SegmentAssembler`` per stream collects contiguous samples and closes a
segment when:
  * a **gap** is detected (inter-sample interval > ``gap_factor`` × expected) —
    this is the store-and-forward / HDF5 Index Table boundary; or
  * the segment hits ``max_samples`` (keeps uplink batches bounded); or
  * the segment spans ``max_seconds`` (flush partial low-rate streams promptly).

The ``Sampler`` owns a background thread that drives the (blocking) driver and
appends completed segments to the buffer. The buffer is the thread boundary.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import field

from .buffer.base import Buffer
from .contract import QualityTransition, Segment
from .drivers.base import Driver, RawSample, StreamSpec

log = logging.getLogger(__name__)


class SegmentAssembler:
    def __init__(
        self,
        spec: StreamSpec,
        max_samples: int = 1000,
        max_seconds: float = 10.0,
        gap_factor: float = 2.5,
    ):
        self.spec = spec
        self.max_samples = max_samples
        self.max_seconds = max_seconds
        self.gap_factor = gap_factor
        self._expected_interval_us = 1_000_000.0 / spec.hz
        self._seq = 0
        self._reset()

    def _reset(self) -> None:
        self._samples: list[float] = []
        self._quality: list[QualityTransition] = []
        self._start_us: int | None = None
        self._last_us: int | None = None
        self._cur_code: int | None = None

    def feed(self, s: RawSample) -> Segment | None:
        """Add a sample; return a completed Segment if one just closed."""
        completed: Segment | None = None

        # Gap → close the current segment before adding this sample.
        if self._last_us is not None:
            if (s.t_us - self._last_us) > self._expected_interval_us * self.gap_factor:
                completed = self._close()

        if self._start_us is None:
            self._start_us = s.t_us

        idx = len(self._samples)
        if s.flags != self._cur_code:
            self._quality.append(QualityTransition(idx, s.flags))
            self._cur_code = s.flags
        self._samples.append(s.value)
        self._last_us = s.t_us

        # Size / age based flush.
        if completed is None:
            span_us = s.t_us - self._start_us
            if len(self._samples) >= self.max_samples or span_us >= self.max_seconds * 1e6:
                completed = self._close()

        return completed

    def flush(self) -> Segment | None:
        return self._close()

    def _close(self) -> Segment | None:
        if not self._samples or self._start_us is None:
            self._reset()
            return None
        seg = Segment(
            stream_id=self.spec.stream_id,
            modality=self.spec.modality,
            group=self.spec.group,
            start_time_us=self._start_us,
            sampling_hz=self.spec.hz,
            seq=self._seq,
            samples=self._samples,
            channel=self.spec.channel,
            quality=self._quality,
            units=self.spec.units,
            metric=self.spec.metric,
            location=self.spec.location,
            source=self.spec.source,
        )
        self._seq += 1
        self._reset()
        return seg


class Sampler:
    def __init__(self, driver: Driver, buffer: Buffer, **assembler_kwargs):
        self.driver = driver
        self.buffer = buffer
        self._assemblers = {
            spec.stream_id: SegmentAssembler(spec, **assembler_kwargs)
            for spec in driver.describe()
        }
        self._last_sample_us: dict[str, int] = {}
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        self.driver.start()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="sampler", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        try:
            for s in self.driver.read():
                if not self._running:
                    break
                asm = self._assemblers.get(s.stream_id)
                if asm is None:
                    continue
                self._last_sample_us[s.stream_id] = s.t_us
                seg = asm.feed(s)
                if seg is not None:
                    self.buffer.append([seg])
        except Exception:  # keep the agent alive; watchdog/restart handles fatal
            log.exception("sampler loop crashed")

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        # flush any partial segments so we don't drop the tail
        for asm in self._assemblers.values():
            seg = asm.flush()
            if seg is not None:
                self.buffer.append([seg])
        self.driver.stop()

    def last_sample_us(self) -> dict[str, int]:
        return dict(self._last_sample_us)
