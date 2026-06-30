"""Wire contract shared between manuEdge (Pi) and the manuBeat server.

This is the single source of truth for what travels over the uplink. It is
*vendored*: the canonical definition lives in manuBeat, and this copy carries a
``SCHEMA_VERSION`` that the server's ingest endpoint validates on every batch.
Bump the version (and update manuBeat) whenever the shape changes.
"""

from .records import (
    SCHEMA_VERSION,
    Group,
    QualityTransition,
    Segment,
    Event,
    Batch,
)

__all__ = [
    "SCHEMA_VERSION",
    "Group",
    "QualityTransition",
    "Segment",
    "Event",
    "Batch",
]
