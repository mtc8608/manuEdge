"""The manuEdge ↔ manuBeat wire records.

Design note — *a segment is an HDF5 Index Table row.* The CENTER-TBI HDF5 format
(Cabeleira et al.) models every dataset as a series of uninterrupted continuous
streams, each described by ``start_index`` / ``start_time`` / ``duration`` /
``sampling_frequency``. A ``Segment`` carries exactly that, so the server's
archival step is nearly mechanical: append samples, add one Index row, append
Quality rows.

Two record kinds cover the whole paper:
  * ``Segment`` → HDF5 ``numerics/`` (<=1 Hz) and ``waves/`` (waveforms).
  * ``Event``   → HDF5 ``episodic/`` and ``annotations/``.

``summaries/``, ``patient.info``, ``presentation`` and ``definitions`` are
server-derived / static and are NOT emitted by the Pi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Bump whenever any record shape below changes. The server rejects batches whose
# schema_version it does not understand.
SCHEMA_VERSION = "0.1.0"


class Group(str, Enum):
    """Top-level HDF5 group a timeseries segment belongs to."""

    NUMERICS = "numerics"  # low temporal resolution, <= 1 Hz
    WAVES = "waves"        # high temporal resolution, waveforms


@dataclass(slots=True)
class QualityTransition:
    """A change in the quality bitset, valid from this sample until the next.

    ``sample_offset`` is the index *within the segment* where the code takes
    effect. The server converts it to an absolute timestamp using the segment's
    ``start_time_us`` and ``sampling_hz`` when writing the HDF5 Quality Table.
    """

    sample_offset: int
    code: int  # bitset; see manuedge.quality.Q

    def to_wire(self) -> list[int]:
        return [self.sample_offset, self.code]


@dataclass(slots=True)
class Segment:
    """One contiguous, uninterrupted run of samples for a single stream.

    Maps 1:1 to an HDF5 Index Table row. A gap (sensor dropout, sampling
    interruption) ends a segment; the next good sample starts a new one.
    """

    stream_id: str            # stable id for this device+channel stream
    modality: str             # e.g. "abp", "ecg", "spo2" (see modality registry)
    group: Group              # numerics | waves
    start_time_us: int        # source timestamp of sample 0, µs since 1/1/1970
    sampling_hz: float
    seq: int                  # monotonic per-stream; (stream_id, seq) dedupes on the server
    samples: list[float]      # float32 values
    channel: str | None = None        # composite channel, e.g. "EEG.O1"
    quality: list[QualityTransition] = field(default_factory=list)
    # Mostly-static metadata mirrored into HDF5 dataset attributes.
    units: str | None = None
    metric: str | None = None
    location: str | None = None
    source: str | None = None

    @property
    def duration(self) -> int:
        """Number of samples — the HDF5 Index Table ``duration`` field."""
        return len(self.samples)

    def to_wire(self) -> dict:
        return {
            "type": "segment",
            "stream_id": self.stream_id,
            "modality": self.modality,
            "group": self.group.value,
            "start_time_us": self.start_time_us,
            "sampling_hz": self.sampling_hz,
            "seq": self.seq,
            "duration": self.duration,
            "samples": self.samples,  # TODO: base64 float32 for waveform-rate streams
            "channel": self.channel,
            "quality": [q.to_wire() for q in self.quality],
            "units": self.units,
            "metric": self.metric,
            "location": self.location,
            "source": self.source,
        }


@dataclass(slots=True)
class Event:
    """An individually timestamped record (episodic measurement or annotation)."""

    kind: str             # "episodic" | "annotation"
    code: str
    ts_ms: int            # timestamp, ms since 1/1/1970
    duration_ms: int | None = None
    comment: str | None = None
    value: float | None = None

    def to_wire(self) -> dict:
        return {
            "type": "event",
            "kind": self.kind,
            "code": self.code,
            "ts_ms": self.ts_ms,
            "duration_ms": self.duration_ms,
            "comment": self.comment,
            "value": self.value,
        }


@dataclass(slots=True)
class Batch:
    """A drained set of records posted to the server in one uplink request."""

    node_id: str
    records: list[Segment | Event]

    def to_wire(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "node_id": self.node_id,
            "records": [r.to_wire() for r in self.records],
        }
