"""Common driver interface.

A driver turns a physical device into a stream of timestamped ``RawSample``s.
The sampler assembles those into ``Segment``s. Drivers must:
  * timestamp **at the source** (edge time, not arrival time);
  * never block the rest of the agent — ``read()`` runs in its own thread;
  * surface dropouts by simply *not* yielding (the gap becomes a new segment).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator

from ..contract import Group


@dataclass(slots=True)
class StreamSpec:
    """Static description of one stream a driver produces."""

    stream_id: str        # stable, unique per device+channel
    modality: str
    hz: float
    group: Group
    channel: str | None = None
    units: str | None = None
    metric: str | None = None
    location: str | None = None
    source: str | None = None


@dataclass(slots=True)
class RawSample:
    """A single sample emitted by a driver."""

    stream_id: str
    value: float
    t_us: int        # source timestamp, µs since 1/1/1970
    flags: int = 0   # quality bitset for this sample (see manuedge.quality.Q)


class Driver(ABC):
    """Base class for all device drivers."""

    name: str = "driver"

    @abstractmethod
    def describe(self) -> list[StreamSpec]:
        """Return the streams this driver produces (from its config)."""

    @abstractmethod
    def start(self) -> None:
        """Open the device. Raise with a clear hint if hardware is unavailable."""

    @abstractmethod
    def read(self) -> Iterator[RawSample]:
        """Yield samples forever (blocking). Runs in a dedicated thread."""

    @abstractmethod
    def stop(self) -> None:
        """Release the device. Must be safe to call more than once."""
