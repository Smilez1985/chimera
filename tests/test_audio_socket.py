"""Audio-Einstellungen über den Sitzungs-Socket (Reiter „Einstellungen").

Drei Dinge, die kein Einzeltest des Schalters fängt — dieselben wie beim
Avatar (`tests/test_avatar_socket.py`), nur für Mikrofon und Tonausgabe:

1. **Der Name der Operation.** Das Gateway schickt `audio_lesen` und
   `audio_setzen`; der Dienst muss beide kennen. Am 13.11.2026 hätte ein
   solcher Namensfehler die Freigabe-Erinnerung stumm gemacht, ohne dass ein
   Test rot wurde.
2. **Ohne Brücke** gibt es einen benannten Grund — keine Vorgabewerte, die
   wie Einstellungen aussehen.
3. **Der Weg durch die echte Sitzung:** echter Unix-Socket, echte
   `SitzungsServer`-Schleife, nur der Schalter ist ein Doppel.

Aufruf: python3 tests/test_audio_socket.py
Gegenprobe: python3 tests/gegenprobe_audio_socket.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(os.environ.get("CHIMERA_ROOT_TEST") or
            Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.session import Session  # noqa: E402
from chimera import sitzung_socket  # noqa: E402

PASS = 0
FAIL = 0

def check(name, ist, soll):
    global PASS, FAIL
    if ist == soll:
        PASS += 1
        print(f"  ok    {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} -- erwartet {soll!r}, bekam {ist!r}")

class Antwort:
    text = "ok"
    provider = "p"
    model = "m"

class Agent:
    def run(self, prompt):
        return Antwort()

class Client:
    def __init__(self, pfad):
        self.s = socket.socket(socket.AF_UNIX)
        self.s.settimeout(5)
        self.s.connect(pfad)
        self.f = self.s.makefile("rwb", buffering=0)

    def fragen(self, **kw):
        self.f.write((json.dumps(kw) + "\n").encode())
        zeile = self.f.readline()
        if not zeile:
            raise RuntimeError("keine Antwort")
        return json.loads(zeile)

class Schalter:
    """Doppel des AudioSchalters: hält Zustand und Lautstärken."""

    def __init__(self):
        self.json = {"mikrofon_an": False, "lautsprecher_an": False,
                     "lautstaerke_mikrofon": 80, "lautstaerke_lautsprecher": 80,
                     "karte": "whisplaysound", "letzter_fehler": ""}
        self.aufrufe = []

    def als_json(self):
        return dict(self.json)

    def mikrofon(self, an):
        self.aufrufe.append(("mikrofon", an))
        self.json["mikrofon_an"] = bool(an)
        return bool(an)

    def lautsprecher(self, an):
        self.aufrufe.append(("lautsprecher", an))
        self.json["lautsprecher_an"] = bool(an)
        return bool(an)

    def lautstaerke_setzen(self, was, wert):
        self.aufrufe.append(("lautstaerke", was, wert))
        if not isinstance(wert, int) or isinstance(wert, bool) or not 0 <= wert <= 100:
            return (False, f"{was}: {wert!r} liegt außerhalb 0..100")
        self.json[f"lautstaerke_{was}"] = wert
        return (True, f"{was}: {wert}%")

class Bruecke:
    """Die Chimera-Brücke, wie `app.py` sie aufsetzt (ohne Gesicht)."""

    def __init__(self, schalter):
        self.audio = schalter

    def audio_lesen(self):
        return self.audio.als_json()

    def audio_setzen(self, feld, wert, was=""):
        if feld in ("mikrofon", "lautsprecher"):
            if not isinstance(wert, bool):
                return {"ok": False, "fehler": f"{feld}: erwartet an/aus"}
            gilt = (self.audio.mikrofon(wert) if feld == "mikrofon"
                    else self.audio.lautsprecher(wert))
            return {"ok": True, "meldung": f"{feld} {'an' if gilt else 'aus'}",
                    "audio": self.audio.als_json()}
        if feld == "lautstaerke":
            regler = str(was or "").strip().lower()
            if regler not in ("mikrofon", "lautsprecher"):
                return {"ok": False, "fehler": "lautstaerke braucht was=mikrofon "
                                               "oder was=lautsprecher"}
            ok, meldung = self.audio.lautstaerke_setzen(regler, wert)
            return {"ok": ok, "meldung": meldung, "audio": self.audio.als_json()}
        return {"ok": False, "fehler": f"unbekanntes Feld {feld!r}"}

# --- 1. Namen ------------------------------------------------------------

print("== Op-Namen zwischen Gateway und Dienst ==")
web_rs = (ROOT / "rust/crates/tor/src/web.rs").read_text(encoding="utf-8")
socket_py = (ROOT / "src/chimera/sitzung_socket.py").read_text(encoding="utf-8")
for op in ("audio_lesen", "audio_setzen"):
    check(f"das Gateway schickt {op}", f'"op": "{op}"' in web_rs, True)
    check(f"der Dienst kennt {op}", f'"{op}"' in socket_py, True)
# Und die Brücke wird auch verdrahtet -- sonst wäre alles oben nur Text.
app_py = (ROOT / "src/chimera/app.py").read_text(encoding="utf-8")
check("app.py verdrahtet session.audio_bruecke", "session.audio_bruecke = chi" in app_py, True)
check("app.py hat audio_lesen/audio_setzen",
      "def audio_lesen" in app_py and "def audio_setzen" in app_py, True)

# --- 2. Ohne Brücke ------------------------------------------------------

print("== Ohne Brücke ==")
d = tempfile.mkdtemp()
pfad = os.path.join(d, "sitzung.sock")
sess = Session(Agent())
srv = sitzung_socket.SitzungsServer(sess, pfad=pfad).start()
time.sleep(0.1)
c = Client(pfad)
for op in ("audio_lesen", "audio_setzen"):
    a = c.fragen(op=op)
    check(f"{op} ohne Brücke: nicht ok", a.get("ok"), False)
    check(f"{op} ohne Brücke: Grund genannt",
          "Bruecke" in str(a.get("fehler", "")), True)

# --- 3. Mit Brücke ------------------------------------------------------

print("== Mit Brücke ==")
schalter = Schalter()
sess.audio_bruecke = Bruecke(schalter)
a = c.fragen(op="audio_lesen")
check("lesen liefert den Zustand",
      (a.get("ok"), a["audio"]["mikrofon_an"], a["audio"]["lautstaerke_mikrofon"]),
      (True, False, 80))
a = c.fragen(op="audio_setzen", feld="mikrofon", wert=True)
check("einschalten wirkt", (a.get("ok"), schalter.json["mikrofon_an"]), (True, True))
check("Antwort nennt den neuen Stand", a["audio"]["mikrofon_an"], True)
a = c.fragen(op="audio_setzen", feld="mikrofon", wert="an")
check("kein Wahrheitswert: abgelehnt", a.get("ok"), False)
check("Ablehnung nennt den Grund", "an/aus" in str(a.get("fehler")), True)
a = c.fragen(op="audio_setzen", feld="lautstaerke", was="lautsprecher", wert=45)
check("Lautstärke setzen", (a.get("ok"), schalter.json["lautstaerke_lautsprecher"]),
      (True, 45))
a = c.fragen(op="audio_setzen", feld="lautstaerke", was="lautsprecher", wert=120)
check("außerhalb 0..100: abgelehnt", a.get("ok"), False)
a = c.fragen(op="audio_setzen", feld="lautstaerke", was="subwoofer", wert=50)
check("unbekannter Regler: abgelehnt", a.get("ok"), False)
a = c.fragen(op="audio_setzen", feld="licht", wert=True)
check("unbekanntes Feld: abgelehnt", a.get("ok"), False)
a = c.fragen(op="gibtsnicht")
check("unbekannte Op bleibt ein benannter Fehler",
      "unbekannte op" in str(a.get("fehler")), True)

srv.stop()
print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
