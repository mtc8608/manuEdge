from manuedge.buffer.memory import MemoryBuffer
from manuedge.contract import Event


def _ev(code):
    return Event(kind="annotation", code=code, ts_ms=0)


def test_drain_ack_roundtrip():
    buf = MemoryBuffer()
    buf.append([_ev("a"), _ev("b"), _ev("c")])
    assert buf.pending() == 3

    batch = buf.drain(2)
    assert batch is not None and len(batch.records) == 2
    assert buf.pending() == 3  # still counted while in-flight

    buf.ack(batch.id)
    assert buf.pending() == 1

    assert buf.drain(10) is not None
    # nothing left queued
    assert buf.drain(10) is None


def test_nack_requeues_in_order():
    buf = MemoryBuffer()
    buf.append([_ev("a"), _ev("b")])
    batch = buf.drain(2)
    buf.nack(batch.id)
    again = buf.drain(2)
    assert [r.code for r in again.records] == ["a", "b"]


def test_overflow_drops_oldest():
    buf = MemoryBuffer(max_records=2)
    buf.append([_ev("a"), _ev("b"), _ev("c")])
    assert buf.pending() == 2
    batch = buf.drain(10)
    assert [r.code for r in batch.records] == ["b", "c"]
