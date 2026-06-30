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

## Provisioning a Pi from a blank SD

1. **Flash** Raspberry Pi OS **Lite 64-bit (Bookworm)** with Raspberry Pi Imager.
   In Imager's customization: set hostname, **enable SSH with your key**, Wi-Fi/locale.
2. **Drop config**: copy [`config/agent.example.toml`](config/agent.example.toml) to the
   SD's boot partition as `agent.toml` (becomes `/boot/firmware/agent.toml`), fill in
   `node_id`, server URL, and the one-time enrollment token. *This is the per-device step —
   one image, one small file per Pi.*
3. **Boot + provision**: SSH in and run the bootstrap once:
   ```bash
   sudo bash firstboot.sh   # enables SPI, SD-wear stopgaps, clones, venv, installs service
   ```
   (Later this becomes a first-boot oneshot / a pre-baked image.)
4. The agent is now a systemd service:
   ```bash
   systemctl status manuedge
   journalctl -u manuedge -f
   ```

## Updating an agent (git-pull + restart)

```bash
sudo bash /opt/manuedge/scripts/deploy.sh
```

## Hardware notes (Pi 4 + Waveshare ADS1256)

SPI mode 1, ~1 MHz. CS=GPIO22, DRDY=GPIO17, RST=GPIO18, on-board 2.5 V ref.
Bench sensors: AIN0 = potentiometer, AIN1 = photoresistor. A real-time clock
(DS3231/PCF8523) is recommended — trustworthy timestamps underpin the Index Table.
Get writes off the SD (log2ram, noatime, swap off) and never lose power dirtily (UPS).

## License

MIT
