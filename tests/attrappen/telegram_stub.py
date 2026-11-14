#!/usr/bin/env python3
"""Telegram-API-Attrappe fuer Tuer-Tests ohne echten Bot.

Beantwortet getMe, getUpdates, sendMessage und sendChatAction. Die
Nachrichten, die der Bot schickt, landen als JSON-Zeilen in --protokoll;
`--eingabe` ist die Liste der Updates, die einmalig ausgeliefert wird.

Aufruf:
  python3 telegram_stub.py --port 8999 --protokoll /tmp/tg.jsonl \
      --eingabe '{"update_id":1,"message":{"chat":{"id":42},"from":{"id":42},"text":"/modell"}}'

Wird der Bot mit CHIMERA_TELEGRAM_API=http://127.0.0.1:8999 gestartet,
spricht er mit dieser Attrappe statt mit api.telegram.org.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

EINGABE = []
GELIEFERT = False
PROTOKOLL = None


def protokollieren(zeile):
    if PROTOKOLL:
        with open(PROTOKOLL, "a", encoding="utf-8") as f:
            f.write(json.dumps(zeile, ensure_ascii=False) + "\n")


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

    def do_POST(self):
        global GELIEFERT
        n = int(self.headers.get("Content-Length") or 0)
        roh = self.rfile.read(n) if n else b"{}"
        try:
            daten = json.loads(roh or b"{}")
        except ValueError:
            daten = {}
        methode = self.path.rsplit("/", 1)[-1]
        if methode == "getMe":
            return self._json({"ok": True, "result": {"id": 1, "username": "stub_bot", "is_bot": True}})
        if methode == "getUpdates":
            if GELIEFERT:
                # Danach Stille -- der Bot fragt im Takt weiter.
                return self._json({"ok": True, "result": []})
            GELIEFERT = True
            return self._json({"ok": True, "result": EINGABE})
        if methode == "sendMessage":
            protokollieren({"art": "sendMessage", "chat": daten.get("chat_id"), "text": daten.get("text")})
            return self._json({"ok": True, "result": {"message_id": 1}})
        if methode == "sendChatAction":
            protokollieren({"art": "sendChatAction", "chat": daten.get("chat_id"), "was": daten.get("action")})
            return self._json({"ok": True, "result": True})
        return self._json({"ok": False, "description": f"unbekannte Methode {methode}"})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8999)
    p.add_argument("--protokoll", default=None)
    p.add_argument("--eingabe", action="append", default=[])
    a = p.parse_args()
    PROTOKOLL = a.protokoll
    EINGABE = [json.loads(x) for x in a.eingabe]
    print(f"Telegram-Attrappe auf 127.0.0.1:{a.port}", flush=True)
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()
