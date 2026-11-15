"""Avatar-Operationen über den Sitzungs-Socket (DESIGN, Regel „Avatar-…").

Drei Dinge, die schiefgehen können und die kein Einzeltest des Moduls fängt:

1. **Der Name der Operation.** Am 13.11.2026 schickte der Dienst
   `freigaben_lesen`, das Gateway kannte nur `freigabe_lesen` — die Erinnerung
   hätte nie geklingelt und alle Tests waren grün. Hier wird geprüft, dass
   **jede** Op-Zeichenkette, die `web.rs` an den Socket schickt, in
   `sitzung_socket.py` auch bedient wird — und umgekehrt für die neuen Ops.
2. **Die Verdrahtung.** Ein Socket, der die Op kennt, aber die Brücke nicht
   bekommt, muss einen benannten Grund liefern (kein stilles Nichts, keine
   Vorgabewerte, die wie Einstellungen aussehen).
3. **Der Weg durch die echte Sitzung.** Echter Unix-Socket, echte
   `SitzungsServer`-Schleife, nur die Brücke ist ein Doppel — gesetzt wird
   über `op: avatar_setzen`, gelesen über `op: avatar_lesen`, vorgeschaut über
   `op: vorschau`.

Aufruf: python3 tests/test_avatar_socket.py
Gegenprobe: python3 tests/gegenprobe_avatar_socket.py
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
    def __init__(self):
        self.n = 0

    def run(self, prompt):
        self.n += 1
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

class Bruecke:
    """Doppel der Chimera-Brücke: merkt sich, was gesetzt wurde."""

    def __init__(self):
        self.werte = {"frisur": "mochi", "farbe": "#8B5A2B", "kontrast": 0}
        self.vorschauen = []

    def avatar_lesen(self):
        return dict(self.werte, frisuren=["mochi", "zopf"], hinweise=[])

    def avatar_setzen(self, feld, wert):
        if feld not in self.werte:
            return (False, f"unbekanntes Feld {feld!r}")
        self.werte[feld] = wert
        return (True, f"{feld} = {wert}")

    def ausdruecke(self):
        return [{"name": "ROCK", "dauer_s": 0.0, "dauerzustand": True,
                 "vorschau_s": 30.0, "grund": "Dauerzustand — 30 s Vorschau"}]

    def vorschau(self, name):
        self.vorschauen.append(name)
        return {"ok": True, "gesetzt": name, "dauer_s": 30.0, "grund": "30 s"}

# --- 1. Namen: was das Gateway schickt, bedient der Dienst ----------------

print("== Op-Namen zwischen Gateway und Dienst ==")
web_rs = (ROOT / "rust/crates/tor/src/web.rs").read_text(encoding="utf-8")
socket_py = (ROOT / "src/chimera/sitzung_socket.py").read_text(encoding="utf-8")
# Nur die Ops, die ueber den SITZUNGS-Socket gehen: `web.rs` schickt auch
# Anfragen an den Gateway-Socket (tor.sock, bedient von dienst.rs) — die
# gehoeren nicht in diese Pruefung und waeren ein Fehlalarm.
# Zwei Formen: direkt im Aufruf und als vorbereitete Anfrage
# (`let anfrage = json!({"op": ...})`) — beides kommt vor.
geschickt = set(re.findall(
    r'sitzung::anfragen\([^;]{0,300}?"op":\s*"([a-z_]+)"', web_rs, re.S))
alle_ops = set(re.findall(r'"op":\s*"([a-z_]+)"', web_rs))
# Die Ops, um die es hier geht, muessen dabei sein -- sonst prueft die
# Schleife unten nichts Neues.
for op in ("avatar_lesen", "avatar_setzen", "ausdruecke", "vorschau"):
    check(f"das Gateway schickt {op}", op in alle_ops, True)
unbekannt = sorted(op for op in geschickt if op not in socket_py)
check("jede vom Gateway geschickte Op steht im Dienst", unbekannt, [])

# --- 2. Ohne Brücke: benannter Grund ------------------------------------

print("== Ohne Brücke ==")
d = tempfile.mkdtemp()
pfad = os.path.join(d, "sitzung.sock")
sess = Session(Agent())
srv = sitzung_socket.SitzungsServer(sess, pfad=pfad).start()
time.sleep(0.1)
c = Client(pfad)
for op in ("avatar_lesen", "ausdruecke"):
    a = c.fragen(op=op)
    check(f"{op} ohne Brücke: nicht ok", a.get("ok"), False)
    check(f"{op} ohne Brücke: Grund genannt",
          "Bruecke" in str(a.get("fehler", "")), True)

# --- 3. Mit Brücke: der ganze Weg --------------------------------------

print("== Mit Brücke ==")
b = Bruecke()
sess.avatar_bruecke = b
a = c.fragen(op="avatar_lesen")
check("lesen liefert die Werte", (a.get("ok"), a["avatar"]["frisur"]), (True, "mochi"))
a = c.fragen(op="avatar_setzen", feld="frisur", wert="zopf")
check("setzen wirkt", (a.get("ok"), b.werte["frisur"]), (True, "zopf"))
check("setzen antwortet mit dem neuen Stand", a["avatar"]["frisur"], "zopf")
a = c.fragen(op="avatar_setzen", feld="tempo", wert=3)
check("ungültiges Feld wird abgelehnt", a.get("ok"), False)
check("Ablehnung nennt den Grund", "tempo" in a.get("meldung", ""), True)
a = c.fragen(op="ausdruecke")
check("ausdruecke liefert die Liste", [x["name"] for x in a["ausdruecke"]], ["ROCK"])
a = c.fragen(op="vorschau", name="ROCK")
check("vorschau geht durch", (a.get("ok"), b.vorschauen), (True, ["ROCK"]))
a = c.fragen(op="vorschau")
check("vorschau ohne Namen: Grund, kein Absturz",
      (a.get("ok"), "name" in str(a.get("fehler"))), (False, True))
a = c.fragen(op="gibtsnicht")
check("unbekannte Op bleibt ein benannter Fehler",
      "unbekannte op" in str(a.get("fehler")), True)

srv.stop()
print(f"\n{PASS} ok, {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
