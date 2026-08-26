# ADS1263 / Pi 3B+ bench testing — resume notes

Status as of 2026-07-04: code for the ADS1263 driver + pi_model/ADC config
selection is done on the `playground` branch (uncommitted). Nothing has been
tested on real hardware yet. This file is the step-by-step to pick back up.

See `docs/pi3-ads1263-migration-plan.md` for the original design plan this was
implemented from.

## What's already done (playground branch, not committed)

- `src/manuedge/drivers/ads1263.py` — new driver, ADC1 only (10 ch), ported
  from Waveshare's reference driver (github.com/waveshareteam/High-Pricision_AD_HAT).
- `src/manuedge/drivers/__init__.py` — `build_driver("ads1263", ...)` registered.
- `src/manuedge/config.py` + `src/manuedge/main.py` — `pi_model` field
  ("pi3"/"pi4", defaults "pi4"); warns if `buffer.max_records` looks too big
  for a Pi 3B+'s 1 GB RAM.
- `config/agent.example.toml` — `pi_model` field + commented ADS1263 example
  block (Option B, alongside the default ADS1256 Option A).
- `scripts/flash.sh` — prompts for Pi model + ADC HAT, generates the right
  `[[drivers]]` block and `max_records` default.
- `tests/test_drivers.py` — new, all green. Full suite: 11/11 passing
  (ran via `.venv/Scripts/python.exe -m pytest -q` since this box is Windows).
- Docs updated: `README.md`, `CLAUDE.md`, `.claude/memory/hardware.md`,
  `.claude/memory/decisions-and-status.md` — all flagged **not bench-validated**.

## Known risk points to check first on the bench

1. **Checksum assumption** — `ADS1263Driver._checksum_ok()` assumes the chip's
   power-on-default `REG_INTERFACE` mode appends a checksum byte (sum of 4
   data bytes + 0x9B, XORed against byte 5, should be 0). This was inferred
   from Waveshare's reference driver behavior, not independently confirmed
   against the TI SBAS925 datasheet. **If every read comes back `None`
   (dropped as checksum-mismatch), this is the first thing to suspect** — try
   temporarily stubbing `_checksum_ok` to always return `True` and see if the
   raw values look sane.
2. **Pins** (cs=22, drdy=17, rst=18) — copied from the ADS1256 HAT (same
   physical connector) but NOT bench-confirmed for the ADS1263 board revision.
3. **REFMUX=0x00** (onboard ±2.5V reference) — Waveshare's own demo actually
   uses VDD/VSS as reference (0x24) instead. Went with ±2.5V to match the
   `VREF=2.5` assumption in the voltage formula; confirm which one this HAT
   actually needs with a known voltage on a channel.

## Step-by-step: getting this onto the Pi 3B+ tomorrow

### 1. Get the code onto the Pi
The `playground` branch only exists on this laptop. Easiest path — rsync,
no git push needed:
```bash
rsync -av --exclude='.venv' --exclude='.run' --exclude='.git' \
  d:/USER_SCRIPTS/manuEdge/ manu@<pi3-hostname>.local:~/manuedge/
```
(Alternative: `git push origin playground` then `git clone -b playground <url>`
on the Pi, if you're fine publishing the branch.)

### 2. Set up the venv on the Pi
```bash
ssh manu@<pi3-hostname>.local
cd ~/manuedge
python3 -m venv .venv && .venv/bin/pip install -e '.[pi,dev]'
```

### 3. Throwaway bench check BEFORE trusting the driver loop
Per the migration plan §3 checklist — confirm chip-ID/pins/one channel's
voltage by hand first:
```python
# quick_check.py, run with .venv/bin/python
from manuedge.drivers.ads1263 import ADS1263Driver
d = ADS1263Driver({"cs_pin": 22, "drdy_pin": 17, "rst_pin": 18,
                    "channels": [{"ain": 0, "modality": "bench_pot"}]})
d.start()          # raises here if chip-ID check fails — first signal to watch
print(next(d.read()))
d.stop()
```
If `start()` raises the chip-ID error: pins or reset sequence need adjusting.
If it passes but the value looks wrong: check the checksum assumption above.

### 4. Full pipeline against a mock server
Once one channel checks out, build a config with `pi_model = "pi3"` and the
`ads1263` driver block (copy Option B out of `config/agent.example.toml`,
uncomment it), then:
```bash
# laptop:
./run mock 8999
# Pi, pointed at the laptop's mock server:
.venv/bin/manuedge -c my-ads1263.toml -v
```
Watch for the `pi_model`/`max_records` warning in the log, and confirm
segments actually arrive at the mock server.

### 5. Only after that — real SD flash / systemd install
`./run flash` and `firstboot.sh` always `git clone` whatever `REPO_URL`'s
default branch is — there's currently no branch parameter. For bench testing
on an already-running Pi, steps 1-4 are enough; no need to touch flashing.
If a full reflash is wanted, either push `playground` and add a `--branch`
flag to `flash.sh`/`firstboot.sh` (not built yet — flagged as a possible
follow-up), or just merge to main first.

## Open follow-up (not started)
- Optionally add a `--branch` flag to `scripts/flash.sh` / `firstboot.sh` so
  testing a branch doesn't require merging first.
- After bench validation succeeds: update `.claude/memory/hardware.md` with
  the *confirmed* ADS1263 facts (pins, chip-ID value, actual reference
  voltage in use, onboard sensor wiring) the same way it documents the 1256.
