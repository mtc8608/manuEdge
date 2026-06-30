---
name: hardware
description: Hardware facts & constraints for the manuEdge bedside Pi
type: reference
---

# Bedside Pi hardware

**In hand:** Raspberry Pi 4 Model B Rev 1.2, currently Raspbian 10 (buster) at
`pi@raspberrypi.local` (192.168.0.174 on the LAN). SSH key auth from the dev box is
installed. **buster ships Python 3.7; manuEdge needs 3.11 → reflash to Bookworm 64-bit
before running the agent on hardware** (`./run flash` produces such a card).

**HAT:** Waveshare High-Precision AD HAT = **ADS1256**, 8-ch 24-bit SPI ADC.
- Onboard demo sensors (confirmed by live test): **AIN0 = potentiometer, AIN1 =
  photoresistor (LDR)**; AIN2–AIN7 float ~2 V.
- Pins: **CS=GPIO22, DRDY=GPIO17, RST=GPIO18**, SPI **mode 1**, max ~1 MHz, on-board
  **2.5 V** reference.
- STATUS chip-ID nibble reads 3 = ADS1256 confirmed.
- Single-ended read: set MUX `(ch<<4)|0x08` (AINCOM) → SYNC → WAKEUP → wait DRDY low →
  RDATA → 3 bytes two's-complement; `V = raw * 2*Vref / 0x7FFFFF`.
- Libs present on the Pi: `spidev`, `RPi.GPIO`, `gpiozero`. `i2c-tools` NOT installed;
  I²C bus empty. (These facts are encoded in `src/manuedge/drivers/ads1256.py`.)

**Hardware constraints that shape design:**
- Pi 4 → no NVMe/PCIe (that's Pi 5). "SSD" = **USB 3.0 SSD** (Pi 4 boots from USB).
- 40-pin GPIO header occupied by the ADC HAT → prefer **USB peripherals**; more HATs
  need stacking headers. PoE HAT OK (separate 4-pin header).
- **The real SD-card killer is unclean power-off, not write volume.** Plan: get writes
  off the SD (USB SSD boot + log2ram + noatime + swap off) AND never lose power dirtily
  (UPS with safe-shutdown). The agent's RAM buffer already avoids SD writes for data.

**Hospital must-not-forgets:**
- **RTC module** (DS3231/PCF8523 on I²C, or USB GPS) — Pi 4 has no battery clock; if NTP
  is blocked on the biomed VLAN, timestamps reset on reboot. Trustworthy time underpins
  the HDF5 Index Table.
- **USB galvanic isolator** + **isolated RS-232** — patient safety / leakage current
  (IEC 60601) once wired to patient-connected gear. Genuine **FTDI** (avoid Prolific clones).
- Wired Ethernet / PoE preferred over Wi-Fi. Active cooling for 24/7 + stacked HAT;
  wipeable/mountable enclosure.

**Minimum viable bedside buy:** USB SSD + UPS (safe-shutdown) + official 5V/3A USB-C PSU
+ RTC module + isolated USB-RS232.
