# Migration plan: Raspberry Pi 3B+ + Waveshare ADS1263 HAT

Status: **planning only — no code changed yet.** Current code/docs assume the
bench Pi is a **Pi 4** with the **ADS1256** HAT (8-ch, 24-bit). This plan
covers what changes to move to a **Pi 3B+** with the **ADS1263** HAT
(10-ch, 32-bit, dual ADC).

## 1. What's actually different

### Pi 3B+ vs Pi 4
| | Pi 4 (assumed today) | Pi 3B+ (target) |
|---|---|---|
| RAM | 2–8 GB | **1 GB only** — matters for the RAM-only buffer (`agent.toml` currently sets `buffer.max_records = 500000`; likely too high, needs a real budget calc) |
| USB | USB 3.0 | **USB 2.0 only** — "boot off USB SSD" (the SD-wear mitigation in `hardware.md`) still works on 3B+, but slower, and older 3B+ boards may need USB-boot enabled via `raspi-config`/bootloader EEPROM rather than being on by default. Verify on the actual board. |
| CPU/thermal | better sustained clocks | BCM2837, runs hotter under continuous SPI polling + network; active cooling matters more for 24/7 use |
| OS support | Bookworm 64-bit native target | Bookworm 64-bit **does** support Pi 3B+, just tighter on RAM — no change needed to `scripts/flash.sh`'s image choice |
| PoE | PoE HAT via separate header | Pi 3B+ also has the PoE header — no change |

None of this needs code changes per se, but `hardware.md`, `CLAUDE.md`, and
`README.md` all currently say "Pi 4" and should be corrected once you've
actually reflashed, plus `buffer.max_records` should be re-tuned for 1 GB.

### ADS1256 vs ADS1263
| | ADS1256 (current driver) | ADS1263 (target) |
|---|---|---|
| Channels | 8 single-ended / 4 differential | **10** single-ended (AIN0–9) / up to 5 differential, **plus a second, independent low-speed auxiliary ADC ("ADC2")** with its own 2 inputs |
| Resolution | 24-bit | **32-bit** on the primary ADC |
| Command set | `RDATA=0x01`, `WREG=0x50`, `RREG=0x10`, `SYNC=0xFC`, `SELFCAL=0xF0`, `RESET=0xFE` (see `src/manuedge/drivers/ads1256.py`) | **Different opcodes entirely** (e.g. separate `START1`/`STOP1`/`RDATA1` for ADC1, and `START2`/`STOP2`/`RDATA2` for ADC2), a different register map (`MODE0/1/2`, `REFMUX`, `ADC2CFG`, `TDACP/N`, `GPIO`, etc. replace ADS1256's `ADCON`/`DRATE`), and an optional CRC/checksum byte on reads |
| Gain | PGA up to ×64 via `ADCON` | PGA up to ×32 on ADC1 via `MODE2`, separate gain for ADC2 |
| Data rates | up to ~30 kSPS | up to ~38.4 kSPS on ADC1 (much slower on ADC2) |
| Reference | onboard 2.5 V | onboard 2.5 V **or** internal reference selectable via `REFMUX` |

**Do not hand-transcribe the ADS1263 command bytes from memory or from the
ADS1256 pattern** — they are genuinely different, and this is exactly the
kind of bug that produces plausible-looking-but-wrong voltage readings. Pull
the real values from:
- TI datasheet **SBAS925** (ADS1263), register map section, and
- Waveshare's own reference driver for this HAT (they publish a Python/C demo
  for Raspberry Pi in the product wiki / GitHub — porting their known-working
  SPI sequence is safer than re-deriving it from the datasheet alone).

## 2. Files to touch

### New driver: `src/manuedge/drivers/ads1263.py`
Mirror the shape of `ads1256.py` (same `Driver` ABC: `describe`/`start`/
`read`/`stop`), but:
- New command constants (`CMD_RESET`, `CMD_START1`, `CMD_STOP1`,
  `CMD_RDATA1`, `CMD_WREG`, `CMD_RREG`, ... — verify each against SBAS925 §9.5).
- `FULL_SCALE = 0x7FFFFFFF`, read **4 bytes** per sample (not 3), same
  two's-complement sign-extension pattern as `ads1256._read_channel`.
- `V = raw * 2*Vref / FULL_SCALE / gain` — add a `gain` field to config (default 1)
  since ADS1263's usable PGA range differs from the 1256.
- Decide now whether ADC2 (the auxiliary low-speed ADC) is in scope for v1.
  Recommendation: **skip it initially** — same `Driver` interface can't easily
  express "two independent ADCs with different rates" without a second config
  block; treat ADC1's 10 channels as the v1 scope and revisit ADC2 as a
  follow-up driver (`ads1263_adc2`) if you need it.
- Pin numbers (`cs_pin`/`drdy_pin`/`rst_pin`): the Waveshare ADS1263 HAT's PCB
  is laid out similarly to the ADS1256 one (same physical connector), and
  Waveshare's own pin table is usually CS=22, DRDY=17, RST=18 — **but this
  needs bench confirmation** the same way `hardware.md` confirmed it for the
  1256 (STATUS chip-ID nibble, multimeter, known voltage on a channel). Don't
  assume it carries over; different HAT revisions do differ.
- SPI speed: ADS1256 is capped ~1 MHz in the current driver; check the
  ADS1263 datasheet's max SCLK (it's typically higher, but confirm before
  raising `max_speed_hz`).
- Keep the `spidev`/`RPi.GPIO` imports lazy inside `start()`, same pattern as
  `ads1256.py`, so the package still imports cleanly on a dev box.

**Keep `ads1256.py` in the tree** rather than replacing it — the driver
registry is name-based and config-selected, so both can coexist. Only switch
if you're certain the ADS1256 HAT is retired for good.

### `config/agent.example.toml` and `scripts/flash.sh`
Add a `[[drivers]] name = "ads1263"` example block (channels 0–9 instead of
0–1, plus a `gain` field), alongside or in place of the `ads1256` block. Note
`scripts/flash.sh` currently **hardcodes** the `ads1256` block into every
flashed `agent.toml` (lines ~133–148) — this needs updating too, or it will
silently keep provisioning cards for the wrong ADC.

### `src/manuedge/modality.py`
No structural change needed (channel→modality mapping is config, not code),
but the two bench modalities (`bench_pot`, `bench_ldr`) are hardcoded to
"AIN0"/"AIN1" in their descriptions — re-verify the onboard demo sensors are
wired to the same channels on the ADS1263 HAT (Waveshare's boards usually do
ship the same onboard pot + photoresistor demo circuit, but confirm rather
than assume, same as the pin numbers above).

### `.claude/memory/hardware.md`, `CLAUDE.md`, `README.md`
Update the hardware description once the swap is bench-confirmed: Pi model,
HAT model, pin map, chip-ID check value, and the confirmed onboard sensor
wiring. These currently read "Pi 4 Model B" / "ADS1256" throughout.

### `pyproject.toml`
No change expected — `spidev`, `RPi.GPIO`, `gpiozero` all work identically on
Pi 3B+ and with the ADS1263 (same SPI/GPIO kernel interfaces).

### `provisioning/firstrun.body.sh`, `scripts/firstboot.sh`, `systemd/manuedge.service`
No Pi-model-specific logic found in these — should work unchanged on 3B+.
Only exception: if you rely on USB-SSD boot as the SD-wear mitigation
(per `hardware.md`), double check the 3B+ board's bootloader EEPROM has
USB-mass-storage-boot enabled (`raspi-config` → Advanced Options → Boot Order,
or `rpi-eeprom-config`) — this is default-on for Pi 4 but was a later
firmware update for Pi 3B+.

## 3. Bench validation checklist (do this before trusting any reading)

Same process `hardware.md` used for the ADS1256, repeated for the ADS1263:
1. Confirm SPI enabled, chip responds — read a status/ID register and check
   against the datasheet's expected reset value.
2. Confirm CS/DRDY/RST pins actually match what you wired (toggle each from
   a Python REPL with `RPi.GPIO` and watch with a multimeter/scope if you have
   one).
3. Feed a known voltage (bench supply, or the onboard demo pot at a marked
   position) into one channel and confirm the computed `V = raw * 2*Vref/FULL_SCALE`
   matches within expected error.
4. Confirm which physical channel the onboard potentiometer/photoresistor are
   wired to (don't assume AIN0/AIN1 carries over from the 1256 HAT).
5. Only after all four: update `hardware.md` with the confirmed facts, the
   same way it documents the 1256 today.

## 4. Suggested order of work

1. Reflash the 3B+ to Bookworm 64-bit (`./run flash`), confirm it boots and
   `./run dev` (synthetic driver, no hardware) runs the full pipeline — this
   validates the Pi/OS side independent of the new HAT.
2. Wire the ADS1263 HAT, do the bench validation checklist above using a
   throwaway script (not the driver yet) — confirm pins + chip-ID + one
   channel's voltage math by hand.
3. Write `ads1263.py` against confirmed facts, porting Waveshare's reference
   sequence for command bytes rather than re-deriving from the datasheet cold.
4. Wire it into `agent.example.toml` / `scripts/flash.sh`, run `./run dev`
   equivalent with the real driver (`./run agent <cfg>` pointed at
   `./run mock`) end-to-end.
5. Update `hardware.md` / `CLAUDE.md` / `README.md` to reflect the new
   hardware as the bench truth, and re-tune `buffer.max_records` for the 3B+'s
   1 GB RAM.
6. Run `./run test` (existing sampler/buffer tests are hardware-agnostic, so
   should stay green throughout — they're a good regression check after each
   step above).

## 5. Open questions to resolve before/while implementing

- Do you need ADC2 (the auxiliary low-speed ADC) for anything, or is ADC1's
  10 channels enough for v1?
- Do you want differential-pair reads on any channel, or is single-ended
  (matching the current ADS1256 driver's `AINCOM`-referenced approach) enough?
- Is the 1 GB RAM ceiling on the 3B+ a real constraint given `buffer.backend
  = "memory"` is still the only implemented backend (`sqlite_ssd` is stubbed)?
  If store-and-forward needs to survive longer outages than 1 GB of headroom
  allows, that pulls the SSD-backed buffer forward in priority.
