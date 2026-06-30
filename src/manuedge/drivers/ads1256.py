"""Waveshare High-Precision AD HAT (ADS1256, 8-ch 24-bit SPI ADC) driver.

Working facts confirmed on the bench Pi (see manuBeat memory):
  SPI mode 1, max ~1 MHz. Pins: CS=GPIO22, DRDY=GPIO17, RST=GPIO18. On-board
  2.5 V reference. STATUS chip-ID nibble reads 3 = ADS1256 confirmed.
  Single-ended read: set MUX (ch<<4)|0x08 (AINCOM) → SYNC → WAKEUP → wait DRDY
  low → RDATA → 3 bytes two's-complement. V = raw * 2*Vref / 0x7FFFFF.
  Bench sensors: AIN0 = potentiometer, AIN1 = photoresistor (LDR).

Channel → modality mapping is configuration, so bench sensors map to real
modalities later with no code change. ``spidev`` / ``RPi.GPIO`` import lazily so
this module is importable on a dev box; ``start()`` raises a clear hint if the
hardware libs are missing.
"""

from __future__ import annotations

import time
from typing import Iterator

from ..contract import Group
from ..modality import get as get_modality
from ..quality import Q
from .base import Driver, RawSample, StreamSpec

# --- ADS1256 command set ---
CMD_WAKEUP = 0x00
CMD_RDATA = 0x01
CMD_RREG = 0x10
CMD_WREG = 0x50
CMD_SELFCAL = 0xF0
CMD_SYNC = 0xFC
CMD_RESET = 0xFE

# --- registers ---
REG_STATUS = 0x00
REG_MUX = 0x01
REG_ADCON = 0x02
REG_DRATE = 0x03

VREF = 2.5
FULL_SCALE = 0x7FFFFF
AINCOM = 0x08  # single-ended: negative input = AINCOM


def _now_us() -> int:
    """Source timestamp, µs since 1/1/1970. Trustworthy time needs the RTC."""
    return time.time_ns() // 1000


class ADS1256Driver(Driver):
    name = "ads1256"

    def __init__(self, config: dict):
        # config example:
        #   spi_bus = 0, spi_device = 0, cs_pin = 22, drdy_pin = 17, rst_pin = 18
        #   loop_hz = 50            # round-robin sample rate per channel
        #   channels = [ {ain = 0, modality = "bench_pot"}, ... ]
        self.cfg = config
        self.spi_bus = config.get("spi_bus", 0)
        self.spi_device = config.get("spi_device", 0)
        self.cs_pin = config.get("cs_pin", 22)
        self.drdy_pin = config.get("drdy_pin", 17)
        self.rst_pin = config.get("rst_pin", 18)
        self.loop_hz = float(config.get("loop_hz", 50.0))
        self.channels = config.get("channels", [])  # list of {ain, modality, [stream_id]}
        self._spi = None
        self._gpio = None
        self._open = False

    # --- description -------------------------------------------------------
    def describe(self) -> list[StreamSpec]:
        specs: list[StreamSpec] = []
        for ch in self.channels:
            spec = get_modality(ch["modality"])
            stream_id = ch.get("stream_id", f"{self.name}:ain{ch['ain']}")
            specs.append(
                StreamSpec(
                    stream_id=stream_id,
                    modality=spec.modality,
                    hz=float(ch.get("hz", self.loop_hz)),
                    group=spec.group,
                    units=spec.units,
                    metric=spec.metric,
                    source=self.name,
                )
            )
        return specs

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        try:
            import spidev  # type: ignore
            import RPi.GPIO as GPIO  # type: ignore
        except ImportError as exc:  # pragma: no cover - hardware only
            raise RuntimeError(
                "ADS1256 hardware libs missing. On the Pi: pip install '.[pi]' "
                "(spidev, RPi.GPIO) and ensure SPI is enabled (raspi-config / "
                "dtparam=spi=on)."
            ) from exc

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self.cs_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.rst_pin, GPIO.OUT, initial=GPIO.HIGH)
        GPIO.setup(self.drdy_pin, GPIO.IN)

        self._spi = spidev.SpiDev()
        self._spi.open(self.spi_bus, self.spi_device)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0b01  # SPI mode 1

        self._reset()
        self._open = True

    def stop(self) -> None:
        if self._spi is not None:
            try:
                self._spi.close()
            finally:
                self._spi = None
        if self._gpio is not None:
            try:
                self._gpio.cleanup([self.cs_pin, self.rst_pin, self.drdy_pin])
            finally:
                self._gpio = None
        self._open = False

    # --- sampling ----------------------------------------------------------
    def read(self) -> Iterator[RawSample]:
        if not self._open:
            raise RuntimeError("call start() before read()")
        period = 1.0 / self.loop_hz
        specs = self.describe()
        while True:
            cycle_start = time.perf_counter()
            for ch, spec in zip(self.channels, specs):
                raw = self._read_channel(ch["ain"])
                value = raw * (2 * VREF) / FULL_SCALE
                flags = Q.CLIP if abs(raw) >= FULL_SCALE - 1 else Q.OK
                yield RawSample(spec.stream_id, value, _now_us(), flags)
            # pace the round-robin loop
            elapsed = time.perf_counter() - cycle_start
            if elapsed < period:
                time.sleep(period - elapsed)

    # --- low-level SPI -----------------------------------------------------
    def _cs(self, level: bool) -> None:
        self._gpio.output(self.cs_pin, self._gpio.HIGH if level else self._gpio.LOW)

    def _reset(self) -> None:
        self._cs(False)
        self._spi.xfer2([CMD_RESET])
        self._cs(True)
        time.sleep(0.005)

    def _wait_drdy(self, timeout_s: float = 0.5) -> None:
        deadline = time.perf_counter() + timeout_s
        while self._gpio.input(self.drdy_pin):
            if time.perf_counter() > deadline:
                raise TimeoutError("ADS1256 DRDY timeout")

    def _read_channel(self, ain: int) -> int:
        mux = ((ain & 0x0F) << 4) | AINCOM
        self._cs(False)
        # WREG MUX: write 1 register starting at REG_MUX
        self._spi.xfer2([CMD_WREG | REG_MUX, 0x00, mux])
        self._spi.xfer2([CMD_SYNC])
        self._spi.xfer2([CMD_WAKEUP])
        self._wait_drdy()
        self._spi.xfer2([CMD_RDATA])
        b = self._spi.readbytes(3)
        self._cs(True)
        raw = (b[0] << 16) | (b[1] << 8) | b[2]
        if raw & 0x800000:  # 24-bit two's complement → signed
            raw -= 1 << 24
        return raw
