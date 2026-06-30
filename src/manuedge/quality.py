"""Quality bitset.

Codes are a bitset carried per sample by the driver and recorded as Quality
Table transitions on each segment (HDF5 Quality Table: a code valid from a
timestamp until the next entry). ``QUALITY_BITS`` is also what the server writes
into the HDF5 ``definitions`` group so files stay self-describing.
"""

from __future__ import annotations


class Q:
    OK = 0
    CLIP = 1 << 0          # sample at/near ADC full scale
    SATURATION = 1 << 1    # signal pinned at a physiological limit
    DROPOUT = 1 << 2       # sensor disconnected / no signal
    OUT_OF_RANGE = 1 << 3  # outside the modality's plausible range


# bit value -> human label, mirrored into HDF5 definitions/qualityStruct
QUALITY_BITS: dict[int, str] = {
    Q.CLIP: "clip",
    Q.SATURATION: "saturation",
    Q.DROPOUT: "dropout",
    Q.OUT_OF_RANGE: "out_of_range",
}
