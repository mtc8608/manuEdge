---
name: decisions-and-status
description: Locked design decisions, current state, and next steps for manuEdge
type: project
---

# Decisions & status

## Locked decisions (2026-06-30 planning sessions)
- **Separate repo** for the agent (this one) — keeps the Pi checkout small, deps isolated,
  and manuBeat's upstream (manuSpine) merges clean. Server-side `telemetry` domain stays in
  manuBeat. Wire contract owned by manuBeat, **vendored** here with `SCHEMA_VERSION`.
- **Native systemd, not Docker** on the Pi (SD wear + SPI/GPIO passthrough fuss; Docker
  stays for the manuBeat server).
- **Buffer: RAM-only (`memory`)** now (volatile, fine for prototype). SSD-WAL is the target
  behind the `buffer.backend` switch once the USB SSD arrives.
- **Code delivery: git-pull + systemctl restart** (`./run update`).
- **OS: Raspberry Pi OS Lite Bookworm 64-bit** (Python 3.11). Bench Pi is on EOL buster
  (3.7) — won't run the agent until reflashed.
- **Provisioning via `./run flash`:** Ethernet preferred + Wi-Fi fallback (baked NM
  connection, low autoconnect priority); SSH key-only (bakes `~/.ssh/*.pub`, locks
  password); prompts per card for node_id/hostname, server URL, enrollment token, Wi-Fi;
  shared defaults remembered in `.run/flash-profile.env` (never secrets).

## Data model insight
A **segment = an HDF5 Index Table row** (contiguous uninterrupted run; a gap → new entry).
Two wire record kinds: **TimeseriesSegment** (→ numerics/waves) and **Event** (→
episodic/annotations). See [hdf5-format.md](hdf5-format.md).

## Built & verified
- Agent skeleton: `ads1256` + `synthetic` drivers, `SegmentAssembler` (gap/size/age flush,
  seq, quality), RAM `MemoryBuffer`, HTTPS `Uplink` (idempotent, backoff), `Heartbeat`,
  config/config_agent, `main` (sampler thread + asyncio + sd_notify).
- `ads1263` driver (10-ch, 32-bit; ADC1 only, ADC2 out of v1 scope) + `pi_model`
  ("pi3"/"pi4") config field, both config-selected alongside `ads1256`/`pi4` so
  existing setups keep working unchanged. `./run flash` prompts for both. Ported
  from Waveshare's reference driver rather than hand-derived — **code only, not
  bench-validated**; see docs/pi3-ads1263-migration-plan.md for the validation
  checklist before trusting a reading from this HAT.
- `./run` orchestrator (dev/test/mock/agent/flash/install/update/logs/status); builds its
  own venv.
- `./run flash` SD baker + `provisioning/firstrun.body.sh` + `scripts/firstboot.sh`.
- Tests green (sampler + buffer). `./run dev` verified end-to-end (synthetic → mock server).
- `./run flash --dry-run` verified (artifacts only). **NOT yet tested on a real card/boot.**

## Next steps
1. Build the manuBeat **`telemetry` ingest endpoint** (`/api/bedside/ingest` +
   `/heartbeat`) matching `src/manuedge/contract/`, so the Pi has a real server. Until then
   the uplink retries forever (expected store-and-forward behavior); for a live test point
   `agent.toml` `server.url` at a laptop running `./run mock 8999` on the LAN.
2. Validate `./run flash` on a real card (logs: `/var/log/manuedge-firstrun.log`,
   `/var/log/manuedge-bootstrap.log`).
3. Base64 float32 sample encoding for waveform-rate streams (currently JSON float list).
4. `sqlite_ssd` buffer backend when the USB SSD arrives.
5. More drivers: RS-232 (isolated FTDI), LAN/TCP devices.
