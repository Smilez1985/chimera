#!/usr/bin/env python3
"""Meldet den Ausgang eines Installer-Laufs an die LED des laufenden Dienstes.

Aufruf:  led.py <socket-pfad> <zustand> [sekunden]

Zweck: Hatte der Lauf nichts zu tun (kein neuer Stand, alles eingerichtet),
haelt der Dienst weiterhin die Leitungen -- der Installer kann das Panel also
nicht selbst anfassen. Er sagt es dem Dienst ueber den Sitzungs-Socket, und
der Renderer setzt die Farbe in seinem Takt (Vorgabe smilez, 3.11.).

Zustaende (Farbe und Muster stehen im Dienst, chimera.display.led):
  ok        eingerichtet, alles neu             gruen, fest
  nichts    geprueft, nichts zu tun             gruen, langsam blinkend
  befund    geschafft, etwas fehlt              gelb, fest
  neustart  eingerichtet, wirkt nach dem Start  blau, blinkend
  fehler    abgebrochen                         rot, SOS

Rueckgabe: 0 gemeldet, 1 nicht gemeldet (Begruendung auf stderr).
Kein Warten ohne Grenze: Der Installer darf an einem schweigenden Dienst
nicht haengen bleiben.
"""

from __future__ import annotations

import json
import socket
import sys

#: Anzeigedauer je Ausgang in Sekunden. Lang genug, dass ein Mensch es sieht,
#: kurz genug, dass die LED danach wieder den Grundzustand zeigt.
DAUER = {"ok": 3.0, "nichts": 6.0, "befund": 3.0, "neustart": 6.0, "fehler": 6.5}

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
        print("Aufruf: led.py <socket> <zustand> [sekunden]", file=sys.stderr)
        return 2
    pfad, zustand = argv[1], argv[2]
    sekunden = float(argv[3]) if len(argv) > 3 else DAUER.get(zustand, 3.0)

    antwort = sende(pfad, {"op": "led", "zustand": zustand, "sekunden": sekunden},
                    zeitgrenze=3.0)
    if not antwort.get("ok"):
        print(f"LED {zustand} nicht gemeldet: {antwort.get('fehler', '?')}",
              file=sys.stderr)
        return 1
    print(f"LED: {zustand} ({sekunden:g} s).")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
