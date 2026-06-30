"""Config agent — pulls runtime config from the server registry.

The Pi dials OUT for its config (which channels, sample rates, and which
patient/bed this node is bound to). The server is the source of truth; this lets
the backoffice change a node's config without touching the device.

Stub for now: returns the local AgentConfig unchanged. Wire up the registry
endpoint in P3.
"""

from __future__ import annotations

import logging

from .config import AgentConfig

log = logging.getLogger(__name__)


class ConfigAgent:
    def __init__(self, config: AgentConfig):
        self.config = config

    async def pull(self) -> AgentConfig:
        """Fetch + merge remote config. TODO(P3): GET /api/telemetry/nodes/<id>/config."""
        log.debug("config_agent: using local config (remote pull not implemented)")
        return self.config
