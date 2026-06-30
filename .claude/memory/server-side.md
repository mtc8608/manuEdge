---
name: server-side
description: manuBeat server-side design for telemetry — built in manuBeat, NOT in this repo
type: project
---

# Server side (lives in manuBeat, not manuEdge)

The counterpart to this agent is a new **`telemetry` domain in manuBeat**
(`init-scripts/02-init-telemetry.sql`, `routes/telemetry/`, `resolvers/telemetry/`,
`python/api/domains/telemetry/`, PWA pages). Full plan:
`../manuBeat/docs/telemetry-bedside-plan.md`.

**Core mental model:** a fleet of edge agents that buffer locally and dial home. The
server is a **registry + ingest + realtime fan-out**.

Pieces to build (in manuBeat):
- **Enrollment/registry API** — Pis register, get per-device credentials (token or mTLS,
  separate from human JWT/admin/user roles).
- **Ingest service (Node)** — accepts batches at `/api/telemetry/ingest`, validates the
  `SCHEMA_VERSION`, **dedupes on `(node_id, stream_id, seq)`** (idempotent backfill),
  persists. Per manuBeat's rule, **Python is computation-only, no DB writes** → ingest +
  persistence stay in **Node**.
- **HDF5 archiver (Python/h5py)** — consumes segments/events → datasets + Index/Quality
  tables (see [hdf5-format.md](hdf5-format.md)). Writing `.h5` to MinIO/disk is not a DB
  write, so it respects the rule. Also computes `summaries/`.
- **Data model** — `edge_nodes`, `devices`, `channels`, `patients`/`encounters`
  (patient↔bed↔Pi binding over time — hardest part; a bed/Pi is reused across patients),
  `readings`, `node_heartbeats`, audit log (PHI).
- **Realtime fan-out** — WS / GraphQL subscriptions (current `graphql-http` is
  request/response only; live view needs a WS transport).
- **Frontend** — Fleet page (online/offline from heartbeat at `/api/telemetry/heartbeat`,
  bound patient/bed, last-sample-time) + live monitor reusing manuBeat's `plot`/`plotGrid`
  components + config UI + alerts.

**Open decisions:** transport (HTTPS-batched MVP vs MQTT later), time-series storage
(Postgres partitions vs TimescaleDB vs raw→MinIO + downsampled summaries — driven by
sample rate), intended-use boundary (research/monitoring vs clinical → regulatory ceiling),
topology (assume server on-prem in hospital for PHI).

**This agent's contract to the server:** POST batches `{schema_version, node_id, records:[
{type:"segment"|"event", …}]}` to `/api/telemetry/ingest`; POST health to
`/api/telemetry/heartbeat`. See `src/manuedge/contract/records.py` for exact shapes.
