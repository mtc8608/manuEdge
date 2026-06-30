# manuEdge

Bedside telemetry **edge agent** for [manuBeat](https://github.com/mtc8608/manuBeat).
It runs headless on a Raspberry Pi at the bedside: reads medical devices, assembles
contiguous **segments**, buffers them locally, and **dials home** to the manuBeat
server. The server never reaches in.

> First/prototype device: **Waveshare High-Precision AD HAT (ADS1256)** 24-bit SPI ADC.
> The whole stack is built pluggably — more drivers (RS-232, LAN) drop in later.

## Design in one paragraph

A **segment is an HDF5 Index Table row.** manuBeat archives into the CENTER-TBI
HDF5 format (Cabeleira et al.), where every dataset is a series of *uninterrupted
continuous streams* described by start-time + sampling-frequency + duration. A
network blip or sensor dropout simply ends a segment and starts a new one — which
is exactly store-and-forward. So the Pi emits segments that are pre-digested index
rows, and the server's archival step is nearly mechanical. See manuBeat
`docs/telemetry-bedside-plan.md` for the full architecture.

## Agent layers (`src/manuedge/`)

| Module | Role |
|---|---|
| `drivers/` | one plugin per device; `ads1256.py` is the prototype. Common `Driver` interface. |
| `sampler.py` | assembles raw samples into segments; gap → new segment; size/age flush. |
| `quality.py` | per-sample quality bitset (clip/saturation/dropout). |
| `buffer/` | store-and-forward; `memory` (RAM-only) now, `sqlite_ssd` later. Swappable. |
| `uplink.py` | outbound HTTPS batch POST; idempotent on `(node_id, stream_id, seq)`. |
| `config_agent.py` | pulls runtime config from the server registry (stub for now). |
| `heartbeat.py` | health/online signal (CPU temp, disk, backlog, last-sample-time). |
| `contract/` | **vendored** wire schema (Segment/Event + `SCHEMA_VERSION`); source of truth is manuBeat. |
| `main.py` | wires it together; sampler in a thread, uplink + heartbeat in asyncio; sd_notify. |

## Quickstart — `./run` (the self-contained orchestrator)

`./run` is to manuEdge what `./run` (docker compose) is to manuBeat — one entry
point for the whole lifecycle. It builds its own venv on first use.

```bash
./run dev        # mock server + synthetic agent, together (Ctrl-C stops both)
./run test       # pytest (sampler + buffer logic)
./run mock 8999  # just the mock ingest server
./run agent cfg  # just the agent with a given config
./run clean      # remove venv + generated files
```

`./run dev` is the hardware-free end-to-end demo: a synthetic driver generates
ECG/ABP waveforms that flow sampler → buffer → uplink → a mock manuBeat server,
which prints every batch. Pull the mock down mid-run and watch the buffer backlog
grow, then drain on reconnect — the store-and-forward demo.

On the Pi, the same script fronts the service:

```bash
./run install    # provision + install the systemd service (sudo; Bookworm)
./run update     # git pull + restart
./run logs       # follow the service log
./run status     # service status
```

The package imports without `spidev`/`RPi.GPIO`; the ADS1256 driver only needs them
at `start()`.

## Provisioning a Pi from a blank SD — `./run flash`

One command bakes a ready-to-run card. Insert the SD card in your laptop, then:

```bash
./run flash            # interactive; --dry-run to preview, --refresh to re-pull the image
```

It will:
1. download Raspberry Pi OS **Lite 64-bit (Bookworm)** (cached in `.run/images/`),
2. prompt for the per-Pi specifics (**node_id/hostname, server URL, enrollment token,
   Wi-Fi**) — shared answers are remembered in `.run/flash-profile.env` so repeat cards
   only need node_id + token,
3. confirm the target device (type `ERASE`) and write the image,
4. inject everything onto the boot partition: your **SSH public key** (key-only login),
   **Wi-Fi** (with Ethernet preferred when a cable is present), **SPI enabled**, hostname,
   the per-device `agent.toml`, and a first-boot hook.

Then: **card → Pi → power up.** First boot configures the OS + Wi-Fi and reboots; the
second boot installs manuEdge over the network (`firstboot.sh`: SPI, SD-wear stopgaps,
clone, venv, systemd service) and starts it. After that:

```bash
ssh <user>@<node_id>.local
journalctl -u manuedge -f
```

> Secrets (enrollment token, Wi-Fi passphrase) are never written to the profile.
> The first-boot scripting mirrors Raspberry Pi Imager's `firstrun.sh` mechanism;
> validate it on your first real card and report anything that needs tuning.

## Updating an agent (git-pull + restart)

```bash
./run update        # on the Pi — wraps git pull + systemctl restart
```

## Hardware notes (Pi 4 + Waveshare ADS1256)

SPI mode 1, ~1 MHz. CS=GPIO22, DRDY=GPIO17, RST=GPIO18, on-board 2.5 V ref.
Bench sensors: AIN0 = potentiometer, AIN1 = photoresistor. A real-time clock
(DS3231/PCF8523) is recommended — trustworthy timestamps underpin the Index Table.
Get writes off the SD (log2ram, noatime, swap off) and never lose power dirtily (UPS).

## License

MIT
