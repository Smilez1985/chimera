#!/usr/bin/env python3
"""Setzt ein Gesicht ueber den Sitzungs-Socket des laufenden Dienstes.

Aufruf:  gesicht.py <socket-pfad> <NAME> [wartezeit]

Zweck (Roadmap, "Updated"-Gesicht): Der Installer zeigt an, dass etwas
eingerichtet wird, **bevor** er die Dienste anhaelt. Das Bild bleibt stehen,
weil das Panel nicht geleert wird; nach dem Dienststart zeichnet der Dienst
selbst weiter.

Rueckgabe: 0 gesetzt, 1 nicht gesetzt (mit Begruendung auf stderr).
Kein Warten ohne Grenze: Der Installer darf an einem schweigenden Dienst
nicht haengen bleiben.
"""

from __future__ import annotations

import json
import socket
import sys
import time


def sende(pfad: str, auftrag: dict, zeitgrenze: float) -> dict:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(zeitgrenze)
    try:
        s.connect(pfad)
        s.sendall((json.dumps(auftrag, ensure_ascii=False) + "\n").encode())
        puffer = b""
        while b"\n" not in puffer:
            stueck = s.recv(65536)
            if not stueck:
                break
            puffer += stueck
    except OSError as exc:
        return {"ok": False, "fehler": str(exc)}
    finally:
        s.close()
    zeile = puffer.split(b"\n", 1)[0]
    try:
        return json.loads(zeile)
    except ValueError:
        return {"ok": False, "fehler": "keine Antwort"}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("Aufruf: gesicht.py <socket> <name> [wartezeit]", file=sys.stderr)
        return 2
    pfad, name = argv[1], argv[2]
    warte = float(argv[3]) if len(argv) > 3 else 0.4

    antwort = sende(pfad, {"op": "gesicht", "name": name}, zeitgrenze=3.0)
    if not antwort.get("ok"):
        print(f"Gesicht {name} nicht gesetzt: {antwort.get('fehler', '?')}",
              file=sys.stderr)
        return 1
    # Dem Renderer Zeit geben, das Bild zu zeichnen, bevor der Dienst geht.
    time.sleep(warte)
    print(f"Gesicht {name} gesetzt.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
