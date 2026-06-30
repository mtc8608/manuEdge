from manuedge.contract import Group
from manuedge.drivers.base import RawSample, StreamSpec
from manuedge.quality import Q
from manuedge.sampler import SegmentAssembler

SPEC = StreamSpec(
    stream_id="t:ain0", modality="bench_pot", hz=10.0, group=Group.WAVES, units="V"
)


def _sample(t_us, value=1.0, flags=0):
    return RawSample("t:ain0", value, t_us, flags)


def test_flush_on_max_samples():
    asm = SegmentAssembler(SPEC, max_samples=3, max_seconds=999)
    interval = 100_000  # 10 Hz
    out = [asm.feed(_sample(i * interval)) for i in range(3)]
    assert out[0] is None and out[1] is None
    seg = out[2]
    assert seg is not None
    assert seg.duration == 3
    assert seg.seq == 0
    assert seg.start_time_us == 0
    assert seg.group is Group.WAVES


def test_gap_starts_new_segment():
    asm = SegmentAssembler(SPEC, max_samples=100, max_seconds=999, gap_factor=2.0)
    interval = 100_000
    assert asm.feed(_sample(0)) is None
    assert asm.feed(_sample(interval)) is None
    # big gap (10x interval) -> closes the previous segment before this sample
    seg = asm.feed(_sample(interval + interval * 10))
    assert seg is not None
    assert seg.duration == 2  # the two contiguous samples
    # the gap sample begins a fresh segment with the next seq
    seg2 = asm.flush()
    assert seg2 is not None
    assert seg2.seq == 1
    assert seg2.duration == 1


def test_quality_transitions_recorded():
    asm = SegmentAssembler(SPEC, max_samples=10, max_seconds=999)
    interval = 100_000
    asm.feed(_sample(0, flags=Q.OK))
    asm.feed(_sample(interval, flags=Q.CLIP))
    asm.feed(_sample(2 * interval, flags=Q.CLIP))
    seg = asm.flush()
    assert seg is not None
    # transitions: OK at 0, CLIP at offset 1 (no repeat at offset 2)
    assert [(q.sample_offset, q.code) for q in seg.quality] == [(0, Q.OK), (1, Q.CLIP)]
