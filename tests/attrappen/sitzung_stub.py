#!/usr/bin/env python3
"""Sitzungs-Attrappe fuer Browser-Tests der Chimera-Oberflaeche.

Spricht das Protokoll aus rust/crates/tor/src/sitzung.rs auf einem
Unix-Socket:

  {"op":"anmelden","seit":N}              -> {"ok":true,"nr":M}, dann {"ereignis":{..}}
  {"op":"frage","tuer":..,"text":..}      -> {"ok":true,"umgeleitet":false}
  {"op":"sitzungen"}                      -> {"ok":true,"haupt":..,"alt":..,"archiv":[..]}
  {"op":"lesen","sitzung":..,"max":..,"vor":..} -> {"ok":true,"eintraege":[..],"gesamt":N}

Jede `frage` wird zusaetzlich als JSON-Zeile in die Protokolldatei
geschrieben (--protokoll), damit ein Test pruefen kann, WAS ankam --
insbesondere ob anbieter/modell/denken mitgehen.

Der Stub antwortet auf eine Frage mit einer "antwort" im Strom, damit die
Oberflaeche etwas anzeigt.
"""
import argparse
import json
import os
import socket
import sys
import threading
import time

VERLAUF = []
for i in range(1, 241):
    VERLAUF.append({
        "art": "nachricht",
        "rolle": "user" if i % 2 else "assistent",
        "inhalt": f"Zeile {i}",
        "tuer": "web",
    })

_strom = []
_strom_sperre = threading.Lock()
_nr = 0


def naechste_nr():
    global _nr
    _nr += 1
    return _nr


def strom_senden(art, text, tuer="web"):
    with _strom_sperre:
        e = {"ereignis": {"nr": naechste_nr(), "art": art, "tuer": tuer, "text": text, "ref": ""}}
        for verb in list(_strom):
            try:
                verb.sendall((json.dumps(e) + "\n").encode())
            except OSError:
                _strom.remove(verb)


def frage_beantworten(anfrage, protokoll):
    text = anfrage.get("text", "")
    zeile = {
        "zeit": time.strftime("%H:%M:%S"),
        "text": text,
        "anbieter": anfrage.get("anbieter"),
        "modell": anfrage.get("modell"),
        "denken": anfrage.get("denken"),
        "sitzung": anfrage.get("sitzung"),
        "tuer": anfrage.get("tuer"),
    }
    if protokoll:
        with open(protokoll, "a", encoding="utf-8") as f:
            f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    strom_senden("eingabe", text, anfrage.get("tuer", "web"))
    wahl = "/".join(x for x in [zeile["anbieter"], zeile["modell"], zeile["denken"]] if x)
    strom_senden("antwort", f"Attrappe: '{text}'" + (f" (Wahl: {wahl})" if wahl else " (ohne Wahl)"))


def lesen(anfrage):
    max_n = max(1, int(anfrage.get("max") or 50))
    vor = max(0, int(anfrage.get("vor") or 0))
    ende = len(VERLAUF) - vor
    anfang = max(0, ende - max_n)
    stueck = VERLAUF[anfang:ende] if ende > 0 else []
    return {"ok": True, "eintraege": stueck, "gesamt": len(VERLAUF)}


def eine_verbindung(conn, protokoll):
    f = conn.makefile("rwb")
    try:
        roh = f.readline()
        if not roh:
            return
        anfrage = json.loads(roh.decode())
        op = anfrage.get("op")
        if op == "anmelden":
            with _strom_sperre:
                _strom.append(conn)
            f.write((json.dumps({"ok": True, "nr": _nr}) + "\n").encode())
            f.flush()
            # Verbindung offen halten, bis der Client schliesst.
            while True:
                time.sleep(0.5)
                with _strom_sperre:
                    if conn not in _strom:
                        return
        if op == "frage":
            frage_beantworten(anfrage, protokoll)
            antwort = {"ok": True, "umgeleitet": False}
        elif op == "sitzungen":
            antwort = {"ok": True, "haupt": "haupt", "alt": None, "archiv": []}
        elif op == "lesen":
            antwort = lesen(anfrage)
        else:
            antwort = {"ok": False, "fehler": f"unbekannte Op {op}"}
        f.write((json.dumps(antwort) + "\n").encode())
        f.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            f.close()
        except OSError:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True)
    p.add_argument("--protokoll", default=None)
    a = p.parse_args()
    if os.path.exists(a.socket):
        os.unlink(a.socket)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(a.socket)
    s.listen(16)
    print(f"Stub hoert auf {a.socket}", flush=True)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=eine_verbindung, args=(conn, a.protokoll), daemon=True).start()


if __name__ == "__main__":
    main()
