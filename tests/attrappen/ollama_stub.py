#!/usr/bin/env python3
"""Ollama-Attrappe fuer Browser-Tests: liefert /api/tags und /api/show.

Zwei Chat-Modelle (eines mit thinking), ein Spezialmodell (vision) und
eines, das auf /api/show nicht antwortet (bleibt "unbekannt").
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

CHAT = ["stub-chat:7b", "stub-denker:8b"]
SPEZIAL = {"stub-vision:3b": ["vision"]}
STUMM = ["stub-stumm:1b"]
FAEHIG = {
    "stub-denker:8b": ["completion", "tools", "thinking"],
    "stub-vision:3b": ["completion", "vision"],
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            modelle = [
                {"name": m, "details": {"parameter_size": "7B"}}
                for m in CHAT + list(SPEZIAL) + STUMM
            ]
            return self._json({"models": modelle})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        daten = json.loads(self.rfile.read(n) or b"{}")
        if self.path.startswith("/api/show"):
            name = daten.get("model")
            if name in STUMM:
                self.send_response(500)
                self.end_headers()
                return
            f = FAEHIG.get(name, ["completion", "tools"])
            return self._json({"capabilities": f, "model_info": {"stub.context_length": 8192}})
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=11555)
    a = p.parse_args()
    print(f"Ollama-Attrappe auf 127.0.0.1:{a.port}", flush=True)
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()
