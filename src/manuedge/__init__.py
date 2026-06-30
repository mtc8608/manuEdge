"""manuEdge — bedside telemetry edge agent for manuBeat.

Reads medical devices (ADS1256 ADC first), assembles contiguous *segments*
(= HDF5 Index Table rows), buffers them locally, and dials home to the manuBeat
server. See README.md and manuBeat's docs/telemetry-bedside-plan.md.
"""

__version__ = "0.1.0"
