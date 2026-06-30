"""Agent configuration (loaded from agent.toml).

Per-device config lives at ``/boot/firmware/agent.toml`` (dropped on the SD's FAT
boot partition before first boot) and is copied to the install dir by
``firstboot.sh``. Secrets (enrollment token) never get committed — see .gitignore.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path("/etc/manuedge/agent.toml")


@dataclass(slots=True)
class ServerConfig:
    url: str = "https://localhost:3000"
    enrollment_token: str = ""
    verify_tls: bool = True


@dataclass(slots=True)
class UplinkConfig:
    batch_records: int = 200
    poll_interval_s: float = 1.0
    max_backoff_s: float = 30.0


@dataclass(slots=True)
class HeartbeatConfig:
    interval_s: float = 15.0


@dataclass(slots=True)
class AgentConfig:
    node_id: str
    server: ServerConfig = field(default_factory=ServerConfig)
    uplink: UplinkConfig = field(default_factory=UplinkConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    buffer: dict = field(default_factory=lambda: {"backend": "memory"})
    # segment assembler tuning: max_samples, max_seconds, gap_factor
    sampler: dict = field(default_factory=dict)
    # drivers: list of {name, ...driver-specific...}
    drivers: list[dict] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "AgentConfig":
        path = Path(path) if path else DEFAULT_PATH
        with open(path, "rb") as fh:
            raw = tomllib.load(fh)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "AgentConfig":
        server = ServerConfig(**raw.get("server", {}))
        uplink = UplinkConfig(**raw.get("uplink", {}))
        heartbeat = HeartbeatConfig(**raw.get("heartbeat", {}))
        return cls(
            node_id=raw["node_id"],
            server=server,
            uplink=uplink,
            heartbeat=heartbeat,
            buffer=raw.get("buffer", {"backend": "memory"}),
            sampler=raw.get("sampler", {}),
            drivers=raw.get("drivers", []),
        )
