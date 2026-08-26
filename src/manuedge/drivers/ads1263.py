"""Waveshare High-Precision AD HAT (ADS1263, 10-ch 32-bit dual-ADC SPI ADC) driver.

v1 scope is ADC1 only (10 single-ended channels, AIN0-AIN9). The auxiliary
low-speed ADC2 is out of scope for now — see docs/pi3-ads1263-migration-plan.md;
add a separate ``ads1263_adc2`` driver later if it's needed.

The command bytes, register addresses, and read sequence below are ported from
Waveshare's own reference driver for this HAT
(github.com/waveshareteam/High-Pricision_AD_HAT, python/ADS1263.py) rather than
re-derived from the TI SBAS925 datasheet from memory — hand-transcribing ADC
command bytes is exactly the kind of thing that produces plausible-looking-but-
wrong voltage readings (see the migration plan). Still, none of this has been
run against real hardware:
  * pin numbers (cs_pin/drdy_pin/rst_pin) default to the same values as the
    ADS1256 HAT (same physical connector) but are NOT bench-confirmed for this
    chip/board revision;
  * REFMUX is set to 0x00 (onboard +-2.5V reference) to match the VREF=2.5
    assumption in the voltage formula below — Waveshare's own demo instead
    uses VDD/VSS as reference (0x24), so confirm which one this HAT actually
    needs before trusting a reading.
Run the bench validation checklist in the migration plan before trusting any
value this driver produces.

``spidev``/``RPi.GPIO`` import lazily so this module is importable on a dev box.
"""

from __future__ import annotations

import time
from typing import Iterator

from ..contract import Group
from ..modality import get as get_modality
from ..quality import Q
from .base import Driver, RawSample, StreamSpec

# --- ADS1263 command set (ADC1 only; ADC2's START2/STOP2/RDATA2 are out of v1 scope) ---
CMD_START1 = 0x08
CMD_STOP1 = 0x0A
CMD_RDATA1 = 0x12
CMD_RREG = 0x20
CMD_WREG = 0x40

# --- registers (subset used by v1; the full map has 27 registers) ---
REG_ID = 0x00
REG_MODE2 = 0x05
REG_INPMUX = 0x06
REG_REFMUX = 0x0F

VREF = 2.5
FULL_SCALE = 0x7FFFFFFF
AINCOM = 0x0A  # single-ended: negative input = AINCOM (ADS1256 uses 0x08 here, not this)

# MODE2 gain field (bits 6:4); bit 7 bypasses the PGA entirely when gain == 1.
GAIN_CODES = {1: 0, 2: 1, 4: 2, 8: 3, 16: 4, 32: 5}


def _now_us() -> int:
    """Source timestamp, µs since 1/1/1970. Trustworthy time needs the RTC."""
    return time.time_ns() // 1000


class ADS1263Driver(Driver):
    name = "ads1263"

    def __init__(self, config: dict):
        # config example:
        #   spi_bus = 0, spi_device = 0, cs_pin = 22, drdy_pin = 17, rst_pin = 18
        #   loop_hz = 50, gain = 1
        #   channels = [ {ain = 0, modality = "bench_pot"}, ... ]  # ain in 0..9
        self.cfg = config
        self.spi_bus = config.get("spi_bus", 0)
        self.spi_device = config.get("spi_device", 0)
        self.cs_pin = config.get("cs_pin", 22)
        self.drdy_pin = config.get("drdy_pin", 17)
        self.rst_pin = config.get("rst_pin", 18)
        self.loop_hz = float(config.get("loop_hz", 50.0))
        self.gain = int(config.get("gain", 1))
        if self.gain not in GAIN_CODES:
            raise ValueError(f"ads1263 gain must be one of {sorted(GAIN_CODES)}, got {self.gain}")
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
                "ADS1263 hardware libs missing. On the Pi: pip install '.[pi]' "
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
        self._spi.max_speed_hz = 2_000_000
        self._spi.mode = 0b01  # SPI mode 1

        self._reset()
        chip_id = self._read_reg(REG_ID) >> 5
        if chip_id != 0x01:
            raise RuntimeError(f"ADS1263 chip-ID check failed (got {chip_id:#x}, want 0x1)")

        self._send_cmd(CMD_STOP1)
        mode2 = (0x80 if self.gain == 1 else 0x00) | (GAIN_CODES[self.gain] << 4)
        self._write_reg(REG_MODE2, mode2)
        self._write_reg(REG_REFMUX, 0x00)  # onboard +-2.5V reference (matches VREF above)
        self._send_cmd(CMD_START1)

        self._open = True

    def stop(self) -> None:
        if self._spi is not None:
            try:
                self._send_cmd(CMD_STOP1)
            except Exception:
                pass
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
                if raw is None:
                    continue  # checksum mismatch: skip, gap shows up as a dropout
                value = raw * (2 * VREF) / FULL_SCALE / self.gain
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
        # ADS1263's reference driver resets via the RST pin (not the CMD_RESET
        # SPI command) — port that known-working sequence rather than guessing.
        self._gpio.output(self.rst_pin, self._gpio.HIGH)
        time.sleep(0.2)
        self._gpio.output(self.rst_pin, self._gpio.LOW)
        time.sleep(0.2)
        self._gpio.output(self.rst_pin, self._gpio.HIGH)
        time.sleep(0.2)

    def _wait_drdy(self, timeout_s: float = 0.5) -> None:
        deadline = time.perf_counter() + timeout_s
        while self._gpio.input(self.drdy_pin):
            if time.perf_counter() > deadline:
                raise TimeoutError("ADS1263 DRDY timeout")

    def _send_cmd(self, cmd: int) -> None:
        self._cs(False)
        self._spi.xfer2([cmd])
        self._cs(True)

    def _write_reg(self, reg: int, value: int) -> None:
        self._cs(False)
        self._spi.xfer2([CMD_WREG | reg, 0x00, value])
        self._cs(True)

    def _read_reg(self, reg: int) -> int:
        self._cs(False)
        self._spi.xfer2([CMD_RREG | reg, 0x00])
        value = self._spi.readbytes(1)[0]
        self._cs(True)
        return value

    def _read_channel(self, ain: int) -> int | None:
        inpmux = ((ain & 0x0F) << 4) | AINCOM
        self._write_reg(REG_INPMUX, inpmux)
        self._wait_drdy()
        self._cs(False)
        self._spi.xfer2([CMD_RDATA1])
        b = self._spi.readbytes(5)  # 4 data bytes + 1 checksum byte (chip's default interface mode)
        self._cs(True)
        if not self._checksum_ok(b):
            return None
        raw = (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]
        if raw & 0x80000000:  # 32-bit two's complement -> signed
            raw -= 1 << 32
        return raw

    @staticmethod
    def _checksum_ok(b: list[int]) -> bool:
        # Chip's default "checksum" interface mode: sum of the 4 data bytes + 0x9B,
        # low byte XORed against the 5th (checksum) byte, should come out 0.
        total = (b[0] + b[1] + b[2] + b[3] + 0x9B) & 0xFF
        return (total ^ b[4]) == 0
