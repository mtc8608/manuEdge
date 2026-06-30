#!/usr/bin/env python3
"""Mock manuBeat ingest server for testing manuEdge end-to-end.

Stdlib only — runs on any Python 3. Accepts the agent's uplink + heartbeat and
prints a summary of every batch so you can see real segments arriving.

    python scripts/mock_server.py [port]      # default 3000
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_POST(self):  # noqa: N802
        body = self._body()
        if self.path.endswith("/ingest"):
            recs = body.get("records", [])
            segs = [r for r in recs if r.get("type") == "segment"]
            evs = [r for r in recs if r.get("type") == "event"]
            samples = sum(r.get("duration", 0) for r in segs)
            print(
                f"[ingest] node={body.get('node_id')} schema={body.get('schema_version')} "
                f"records={len(recs)} segments={len(segs)} samples={samples} events={len(evs)}"
            )
            for s in segs[:4]:
                print(
                    f"         {s['stream_id']:>24}  modality={s['modality']:<10} "
                    f"seq={s['seq']:<4} n={s['duration']:<5} hz={s['sampling_hz']} "
                    f"t0={s['start_time_us']} q={s.get('quality')}"
                )
        elif self.path.endswith("/heartbeat"):
            print(
                f"[heartbeat] node={body.get('node_id')} temp={body.get('cpu_temp_c')} "
                f"pending={body.get('buffer_pending')} last={body.get('last_sample_us')}"
            )
        else:
            print("[?]", self.path, body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_args):  # silence default access log
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"mock manuBeat ingest listening on http://0.0.0.0:{port}")
    print("  endpoints: /api/telemetry/ingest  /api/telemetry/heartbeat")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
