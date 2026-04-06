#!/usr/bin/env python3
"""Dashboard server for AgentLukas – reads activity.json and serves the UI."""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).parent.parent
ACTIVITY_FILE = BASE / "activity.json"
TOOL_CALLS_FILE = BASE / "tool_calls.json"
PORT = 8080


def load_data():
    data = {"stats": {}, "activities": [], "findings": [], "thoughts": [], "lastThought": "Noch keine Aktivität.", "tool_calls": []}
    if ACTIVITY_FILE.exists():
        try:
            data = json.loads(ACTIVITY_FILE.read_text())
        except Exception:
            pass
    # Merge latest tool_calls.json (current session) if exists
    if TOOL_CALLS_FILE.exists():
        try:
            tc = json.loads(TOOL_CALLS_FILE.read_text())
            existing = {str(t): True for t in data.get("tool_calls", [])}
            for t in tc:
                if str(t) not in existing:
                    data.setdefault("tool_calls", []).append(t)
        except Exception:
            pass
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # suppress logs

    def do_GET(self):
        if self.path == "/api/data":
            data = json.dumps(load_data()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)

        elif self.path in ("/", "/index.html"):
            html = (Path(__file__).parent / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Dashboard läuft auf http://0.0.0.0:{PORT}")
    server.serve_forever()
