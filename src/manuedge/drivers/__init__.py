"""Device drivers — one plugin per device type, common interface.

The driver layer is the part that grows over time. ADS1256 (SPI ADC) is the
first/prototype driver, ADS1263 is a second SPI ADC option (both HATs share
the same config-selected `Driver` registry — see
docs/pi3-ads1263-migration-plan.md); RS-232 (pyserial) and LAN (TCP) drivers
follow.
"""

from __future__ import annotations

from .base import Driver, RawSample, StreamSpec

__all__ = ["Driver", "RawSample", "StreamSpec", "build_driver"]


def build_driver(name: str, config: dict) -> Driver:
    """Instantiate a driver by name from its config block."""
    if name == "ads1256":
        from .ads1256 import ADS1256Driver

        return ADS1256Driver(config)
    if name == "ads1263":
        from .ads1263 import ADS1263Driver

        return ADS1263Driver(config)
    if name == "synthetic":
        from .synthetic import SyntheticDriver

        return SyntheticDriver(config)
    raise ValueError(f"unknown driver {name!r}")
