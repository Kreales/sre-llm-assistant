#!/usr/bin/env python3
"""Per-container RX/TX from the Docker API, for Prometheus."""
from __future__ import annotations

import json
import os
import socket
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote


SOCK = os.getenv("DOCKER_SOCK", "/var/run/docker.sock")
API = os.getenv("DOCKER_API_VERSION", "v1.41")
PORT = int(os.getenv("EXPORTER_PORT", "9101"))
PROJECT = os.getenv("COMPOSE_PROJECT", "").strip()


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, sock_path: str):
        super().__init__("localhost")
        self.sock_path = sock_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.sock_path)


def docker_get(path: str) -> dict | list:
    conn = UnixHTTPConnection(SOCK)
    try:
        conn.request("GET", f"/{API}{path}")
        resp = conn.getresponse()
        body = resp.read()
        if resp.status >= 400:
            raise RuntimeError(f"Docker API {resp.status}: {body[:200]!r}")
        return json.loads(body)
    finally:
        conn.close()


def collect() -> list[tuple[str, int, int]]:
    rows: list[tuple[str, int, int]] = []
    for c in docker_get("/containers/json"):
        labels = c.get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        project = labels.get("com.docker.compose.project", "")
        if not service:
            continue
        if PROJECT and project != PROJECT:
            continue
        name = (c.get("Names") or [f"/{service}"])[0].lstrip("/")
        stats = docker_get(f"/containers/{quote(c['Id'])}/stats?stream=false&one-shot=true")
        nets = stats.get("networks") or {}
        rx = tx = 0
        for iface, data in nets.items():
            if iface == "lo":
                continue
            rx += int(data.get("rx_bytes") or 0)
            tx += int(data.get("tx_bytes") or 0)
        rows.append((name, rx, tx))
    return rows


def render() -> bytes:
    lines = [
        "# HELP docker_container_network_receive_bytes_total Bytes received by the container",
        "# TYPE docker_container_network_receive_bytes_total counter",
        "# HELP docker_container_network_transmit_bytes_total Bytes sent by the container",
        "# TYPE docker_container_network_transmit_bytes_total counter",
    ]
    try:
        for name, rx, tx in collect():
            label = name.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'docker_container_network_receive_bytes_total{{container="{label}"}} {rx}')
            lines.append(f'docker_container_network_transmit_bytes_total{{container="{label}"}} {tx}')
    except Exception as exc:
        lines.append(f"# error {exc}")
    lines.append("")
    return ("\n".join(lines)).encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path != "/metrics":
            self.send_error(404)
            return
        body = render()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
