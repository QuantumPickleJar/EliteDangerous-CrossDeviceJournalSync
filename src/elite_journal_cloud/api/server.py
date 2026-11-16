"""Versioned read-only HTTP integration. Loopback only; explicit opt-in."""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from elite_journal_cloud import __version__
from elite_journal_cloud.journal.snapshot import digest


def read_resource(root: Path, route: str) -> tuple[int, dict[str, Any]]:
    if route == "/v1/health":
        return 200, {"api_version": "v1", "version": __version__, "read_only": True}
    if route not in {"/v1/status", "/v1/sessions"}:
        return 404, {"error": "not_found"}
    # mode=ro never creates state, takes no worker lock, and observes committed transactions.
    db = sqlite3.connect((root / "state.sqlite3").resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if route == "/v1/sessions":
            sessions = []
            for row in db.execute("SELECT manifest FROM snapshots ORDER BY id"):
                m = json.loads(row[0])
                sessions.append(
                    {
                        "session": m["session"],
                        "snapshot": digest(bytes(row[0])),
                        "complete_hash": m["complete_hash"],
                        "complete_size": m["complete_size"],
                        "commander_count": len(m["commanders"]),
                    }
                )
            return 200, {"api_version": "v1", "snapshots": sessions}
        states = dict(db.execute("SELECT state,count(*) FROM transfers GROUP BY state"))
        count = db.execute("SELECT count(*) FROM snapshots").fetchone()[0]
        return 200, {
            "api_version": "v1",
            "snapshots": count,
            "transfers": states,
            "consumer_import": "unknown",
        }
    finally:
        db.close()


def make_server(root: Path, port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            # Reject browser-originated and DNS-rebinding requests, even on loopback.
            host = self.headers.get("Host", "")
            bound_port = cast(ThreadingHTTPServer, self.server).server_port
            if self.headers.get("Origin") or host not in {
                f"127.0.0.1:{bound_port}",
                f"localhost:{bound_port}",
            }:
                code, data = 403, {"error": "forbidden"}
            else:
                try:
                    code, data = read_resource(root, urlsplit(self.path).path)
                except (sqlite3.Error, OSError, ValueError):
                    code, data = 503, {"error": "state_unavailable"}
            body = json.dumps(data, sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return  # No request paths, headers, journal data, or credential logging.

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(root: Path, port: int = 8765) -> None:
    with make_server(root, port) as server:
        server.serve_forever()
