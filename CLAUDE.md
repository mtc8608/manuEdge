# CLAUDE.md

Guidance for Claude Code when working in **manuEdge**. These instructions override
default behavior — follow them.

## What this is

manuEdge is the **bedside telemetry edge agent** for
[manuBeat](https://github.com/mtc8608/manuBeat). It runs headless on a Raspberry Pi
at a hospital bedside: reads medical devices, assembles contiguous **segments**,
buffers them locally, and **dials home** to the manuBeat server. The server never
reaches in (hospital VLANs are firewalled; outbound-only).

Two non-negotiable principles:
1. **Edge buffers, never blocks** — a network blip or sensor dropout must not lose
   data or stall sampling. Zero data loss is the bar.
2. **Pi dials out, server never reaches in.**

> First/prototype device: **Waveshare High-Precision AD HAT (ADS1256)** 24-bit SPI
> ADC. Build the whole stack pluggably — more drivers (RS-232, LAN) drop in later.

## The one idea that ties it together

**A segment is an HDF5 Index Table row.** manuBeat archives into the CENTER-TBI HDF5
format (Cabeleira et al.), where every dataset is a series of *uninterrupted
continuous streams* described by `start_time` + `sampling_frequency` + `duration`.
A gap (dropout / interruption) ends a segment and starts a new one — which is exactly
store-and-forward. So the Pi emits segments that are pre-digested index rows, and the
server's archival step is nearly mechanical. Keep this mapping intact end to end.

## Relationship to manuBeat (read this before changing the wire format)

- manuEdge is a **separate repo on purpose**: git-pull onto an SD-only Pi stays small;
  own deps (`spidev`/`RPi.GPIO`) and release cadence; keeps manuBeat's upstream
  (manuSpine framework) merges clean.
- The **wire contract is owned by manuBeat** (source of truth). manuEdge **vendors a
  copy** in [src/manuedge/contract/](src/manuedge/contract/) with a `SCHEMA_VERSION`
  the server's ingest endpoint validates. If you change `Segment`/`Event`/the modality
  registry, bump `SCHEMA_VERSION` and update manuBeat too.
- The **server side** (Node ingest `/api/telemetry/ingest` + `/heartbeat`, registry
  tables, HDF5 archiver in Python, live frontend) lives in **manuBeat**, not here.
  manuBeat sits at `../manuBeat`; its full architecture plan is at
  `../manuBeat/docs/telemetry-bedside-plan.md`.

## Architecture (`src/manuedge/`)

| Module | Role |
|---|---|
| `drivers/` | one plugin per device; common `Driver` interface (`describe`/`start`/`read`/`stop`). `ads1256.py` (hardware), `synthetic.py` (test). Hardware imports are lazy so the package imports on a dev box. |
| `sampler.py` | `SegmentAssembler` turns raw samples into segments: gap → new segment, size/age flush, per-stream `seq`, quality transitions. `Sampler` runs the driver in a thread, appends segments to the buffer. |
| `quality.py` | per-sample quality bitset (clip/saturation/dropout). Mirrored into HDF5 `definitions`. |
| `buffer/` | store-and-forward; `memory` (RAM-only, current default) — `sqlite_ssd` stubbed for the USB SSD later. Swappable via config. |
| `uplink.py` | outbound HTTPS batch POST; idempotent on `(node_id, stream_id, seq)`; exponential backoff; never blocks the sampler. |
| `heartbeat.py` | health/online signal: CPU temp, disk free, buffer backlog, last-sample-time per stream. |
| `config_agent.py` | pulls runtime config from the server registry (stub for now). |
| `modality.py` | the modality registry: `modality → group/hz/units/composite`. Part of the contract. |
| `contract/` | **vendored** wire schema (Segment/Event + `SCHEMA_VERSION`). |
| `main.py` | wires it together; sampler thread + asyncio uplink/heartbeat + `sd_notify`. |

Time bases (from the HDF5 paper — keep exact): Index Table `start_time` = **µs** since
1/1/1970; quality/episodic/annotation = **ms** since 1/1/1970; summaries = Excel days
since 1/1/1990.

## How to run — always use `./run`

```bash
./run dev            # mock server + synthetic agent together (the dev "stack"); Ctrl-C stops both
./run test           # pytest (sampler + buffer logic)
./run mock [port]    # just the stdlib mock ingest server
./run agent [cfg]    # just the agent
./run flash          # LAPTOP: bake an SD card (image + all config). --dry-run to preview
./run clean          # remove venv + generated files
# on the Pi:
./run install        # provision + install the systemd service (sudo)
./run update         # git pull + restart
./run logs | status  # follow log / service status
```

`./run` builds its own venv on first use. A fresh clone needs only Python 3.11.

## Constraints & locked decisions

- **Runtime: native systemd, not Docker.** Docker adds SD wear + SPI/GPIO passthrough
  fuss without removing the host SPI-enable. Reserve Docker for the manuBeat server.
- **Buffer: RAM-only (`memory`) for now** (volatile, fine for prototype). SSD-WAL is the
  production target behind the `buffer.backend` switch.
- **Code delivery: git-pull + `systemctl restart`** (see `./run update`).
- **OS: Raspberry Pi OS Lite Bookworm 64-bit.** The bench Pi is currently on EOL
  *buster* (Python 3.7) — manuEdge needs **Python 3.11**, so it will NOT run there until
  reflashed. `./run flash` produces a Bookworm card.
- **Provisioning:** `./run flash` writes the image and bakes SSH key (key-only login),
  Wi-Fi (Ethernet preferred), SPI, hostname, per-device `agent.toml`, and a first-boot
  hook (`provisioning/firstrun.body.sh` + `scripts/flash.sh`). First boot configures the
  OS; second boot runs `scripts/firstboot.sh` to install the agent.

## Conventions

- Timestamp **at the source** (edge time), never arrival time. A real-time clock
  (DS3231/PCF8523) underpins trustworthy timestamps.
- Drivers declare a modality; everything downstream is looked up in `modality.py`.
  Channel→modality mapping is **config**, not code.
- Secrets (enrollment token, Wi-Fi PSK) never get committed and are never written to
  `.run/flash-profile.env`.
- Keep `.run/` out of git (generated venv, images, build artifacts).

## Status & what's next

Done: full agent skeleton (ADS1256 + synthetic drivers, sampler, RAM buffer, uplink,
heartbeat, config), `./run` orchestrator, `./run flash` SD baker (dry-run verified;
**not yet tested on real hardware/boot**), tests green.

Next: (1) build the manuBeat `telemetry` ingest endpoint so the Pi has a real server;
(2) validate `./run flash` on a real card; (3) base64 float32 sample encoding for
waveform-rate streams; (4) `sqlite_ssd` buffer when the USB SSD arrives.

## More context

Deeper background (hardware facts, server-side design, the HDF5 format, decision
history) is in [.claude/memory/](.claude/memory/) — start with
[.claude/memory/MEMORY.md](.claude/memory/MEMORY.md).
