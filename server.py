"""Rideguard demo server. Uses only the Python standard library."""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from rideguard.engine import Monitor
from rideguard.simulator import build_demo_monitor
from rideguard.storage import load_history, save_completed_trip

ROOT = Path(__file__).parent
STATIC = ROOT / "web"
monitor: Monitor = build_demo_monitor()


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        global monitor
        path = urlparse(self.path).path
        if path == "/api/state":
            self._json(monitor.snapshot())
            return
        if path == "/api/history":
            self._json({"history": load_history()})
            return
        if path.startswith("/api/replay/"):
            trip_id = path.rsplit("/", 1)[-1]
            trip = monitor.trips.get(trip_id)
            if not trip:
                self._json({"error": "Trip not found"}, 404)
            else:
                self._json({"trip_id": trip_id, "events": trip.events, "updates": trip.updates})
            return
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / relative).resolve()
        if STATIC.resolve() not in target.parents and target != STATIC.resolve():
            self._json({"error": "Not found"}, 404)
            return
        if not target.is_file():
            self._json({"error": "Not found"}, 404)
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:  # noqa: N802
        global monitor
        path = urlparse(self.path).path
        size = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "Request body must be valid JSON"}, 400)
            return
        if path == "/api/scenario":
            monitor = build_demo_monitor(body.get("scenario", "normal"))
            self._json(monitor.snapshot())
        elif path == "/api/advance":
            self._json(monitor.advance())
        elif path == "/api/reset":
            monitor = build_demo_monitor()
            self._json(monitor.snapshot())
        elif path.startswith("/api/finish/"):
            trip_id = path.rsplit("/", 1)[-1]
            record = monitor.finish_trip(trip_id)
            if record is None:
                self._json({"error": "Trip not found"}, 404)
            else:
                save_completed_trip(record)
                self._json({"state": monitor.snapshot(), "record": record})
        else:
            self._json({"error": "Not found"}, 404)

    def log_message(self, fmt: str, *args: object) -> None:
        print("[Rideguard] " + fmt % args)


if __name__ == "__main__":
    address = ("127.0.0.1", 8000)
    print(f"Rideguard is ready at http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, Handler).serve_forever()
