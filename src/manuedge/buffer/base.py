"""Buffer interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from ..contract import Event, Segment

Record = Segment | Event


@dataclass(slots=True)
class Batch:
    id: int
    records: list[Record]


class Buffer(ABC):
    @abstractmethod
    def append(self, records: Sequence[Record]) -> None:
        """Enqueue records. Must be thread-safe (sampler thread calls this)."""

    @abstractmethod
    def drain(self, max_records: int) -> Batch | None:
        """Remove up to ``max_records`` into an in-flight batch, or None if empty."""

    @abstractmethod
    def ack(self, batch_id: int) -> None:
        """Confirm a batch was delivered; drop it permanently."""

    @abstractmethod
    def nack(self, batch_id: int) -> None:
        """Delivery failed; return the batch to the front of the queue."""

    @abstractmethod
    def pending(self) -> int:
        """Records waiting (queued + in-flight)."""
