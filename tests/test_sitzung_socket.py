"""Tests für den Ereignisstrom (Regel 5s) und den Sitzungs-Socket.

Echter Unix-Socket, echte Sitzung, nur der Agent ist ein Doppel.
Gegenprobe: ``--gegenprobe`` verfälscht die Verteilung; die Tests
müssen dann rot werden.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from chimera.agent.session import Session  # noqa: E402
from chimera import sitzung_socket  # noqa: E402

GEGENPROBE = "--gegenprobe" in sys.argv
PASS = FAIL = 0
def ok(m):
    global PASS; PASS += 1; print(f"  ok    {m}")
def bad(m):
    global FAIL; FAIL += 1; print(f"  FAIL  {m}")
def check(m, got, want):
    ok(m) if got == want else bad(f"{m} — erwartet {want!r}, bekam {got!r}")


class R:
    def __init__(self, t): self.text = t; self.provider = "p"; self.model = "m"


class Agent:
    def __init__(self): self.n = 0
    def run(self, prompt):
        self.n += 1
        return R(f"antwort-{self.n}")


if GEGENPROBE:
    # Fehler eingebaut: Ereignisse gehen nur an den ersten Abonnenten.
    _orig = Session.emit
    def nur_erster(self, art, tuer, text="", ref=""):
        subs = self._subs
        self._subs = subs[:1]
        try:
            return _orig(self, art, tuer, text, ref)
        finally:
            self._subs = subs
    Session.emit = nur_erster


class Client:
    def __init__(self, pfad):
        self.s = socket.socket(socket.AF_UNIX)
        self.s.settimeout(5)
        self.s.connect(pfad)
        self.f = self.s.makefile("rwb", buffering=0)

    def senden(self, **kw):
        self.f.write((json.dumps(kw) + "\n").encode())

    def lesen(self):
        try:
            z = self.f.readline()
        except OSError:
            return None
        return json.loads(z) if z else None

    def ereignisse(self, anzahl, art=None):
        out = []
        while len(out) < anzahl:
            try:
                o = self.lesen()
            except (socket.timeout, TimeoutError):
                break
            if o is None:
                break
            if "ereignis" in o and (art is None or o["ereignis"]["art"] == art):
                out.append(o["ereignis"])
        return out


print("== Strom in der Sitzung ==")
s = Session(Agent())
got = []
rest = s.subscribe(lambda e: got.append(e) or True)
check("leerer Strom, nichts nachzuliefern", rest, [])
s.ask("hallo", __import__("chimera.agent.session", fromlist=["x"]).DIRECT)
check("Eingabe, denkt, Antwort", [e["art"] for e in got],
      ["eingabe", "zustand", "antwort"])
check("laufende Nummern lückenlos", [e["nr"] for e in got], [1, 2, 3])
nach = s.subscribe(lambda e: True, seit=1)
check("Nachlieferung ab Nummer", [e["nr"] for e in nach], [2, 3])

print("== Socket: eine Frage, zwei Türen sehen alles ==")
d = tempfile.mkdtemp()
pfad = os.path.join(d, "sitzung.sock")
ag = Agent()
sess = Session(ag)
srv = sitzung_socket.SitzungsServer(sess, pfad=pfad).start()
time.sleep(0.1)

web = Client(pfad); tg = Client(pfad)
for c in (web, tg):
    c.senden(op="anmelden", seit=0)
    check("angemeldet", c.lesen()["ok"], True)

web.senden(op="frage", tuer="web", text="wie geht's")
check("Frage angenommen", web.lesen(), {"ok": True, "umgeleitet": False})
a = web.ereignisse(1, "antwort")
b = tg.ereignisse(1, "antwort")
check("Web sieht die Antwort", [e["text"] for e in a], ["antwort-1"])
check("Telegram sieht dieselbe Antwort", [e["text"] for e in b], ["antwort-1"])
check("Modell genau einmal gerufen", ag.n, 1)
check("Herkunft der Eingabe erhalten",
      [e["tuer"] for e in sess._strom if e["art"] == "eingabe"], ["web"])

print("== Klingel: Bezugsnummer bis zur Quittung ==")
web.senden(op="frage", tuer="briefkasten", text="Post Nr. 7 von X", ref="post-7")
web.lesen()
ev = [e for e in web.ereignisse(3) if e["ref"] == "post-7"]
check("alle Ereignisse des Umlaufs tragen die ref",
      [e["art"] for e in ev], ["eingabe", "zustand", "antwort"])
check("Telegram-Tür sieht die Klingel-Antwort auch",
      [e["tuer"] for e in tg.ereignisse(3) if e["ref"] == "post-7"],
      ["briefkasten"] * 3)

print("== Umleitung auf die Hauptsitzung ==")
tg.senden(op="frage", tuer="telegram", text="noch eine", sitzung="alt-1234")
# auf die Annahme warten (Ereignisse und Antwort können sich mischen)
ant = None
for _ in range(20):
    o = tg.lesen()
    if o and "ok" in o:
        ant = o; break
check("umgeleitet gemeldet", ant, {"ok": True, "umgeleitet": True})
time.sleep(0.3)
check("Eingabe landete in der Hauptsitzung", ag.n, 3)
check("Umleitung steht im Strom",
      any(e["art"] == "umgeleitet" for e in sess._strom), True)

print("== Nachlieferung beim späten Anmelden ==")
spaet = Client(pfad)
spaet.senden(op="anmelden", seit=0)
spaet.lesen()
alle = spaet.ereignisse(3, "antwort") if False else []
nrs = []
t0 = time.time()
while time.time() - t0 < 2:
    try:
        o = spaet.lesen()
    except (socket.timeout, TimeoutError):
        break
    if o and "ereignis" in o:
        nrs.append(o["ereignis"]["nr"])
    if len(nrs) >= sess.nr:
        break
check("alles nachgeliefert", nrs, list(range(1, sess.nr + 1)))

print("== Fehlerfälle ==")
x = Client(pfad)
x.senden(op="quatsch"); check("unbekannte op", x.lesen()["ok"], False)
x.f.write(b"kein json\n"); check("kaputte Zeile", x.lesen()["ok"], False)
x.senden(op="frage", tuer="", text="x"); check("Frage ohne Tür", x.lesen()["ok"], False)
x.senden(op="ping"); check("danach weiter bedienbar", x.lesen()["ok"], True)

print("== Besitz und Aufräumen ==")
check("Rechte 660", oct(os.stat(pfad).st_mode & 0o777), "0o660")
try:
    sitzung_socket.SitzungsServer(sess, pfad=pfad).start()
    bad("zweiter Server auf lebendem Socket")
except RuntimeError:
    ok("zweiter Server auf lebendem Socket abgewiesen")
srv.stop()
check("Socketdatei beim Stoppen entfernt", os.path.exists(pfad), False)

print()
print(f"Ergebnis: {PASS} ok, {FAIL} fehlgeschlagen")
sys.exit(1 if FAIL else 0)
