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
    # Fehler eingebaut: das Blaettern ignoriert "vor" und liefert immer den
    # Schluss -- genau der Zustand, in dem man im Chat nicht zurueckscrollen
    # kann. Der Test muss dann rot werden.
    _seite_orig = sitzung_socket.seite
    def seite_ohne_vor(alle, max_n, vor):
        return _seite_orig(alle, max_n, 0)
    sitzung_socket.seite = seite_ohne_vor
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

print("== Verlauf seitenweise lesen (Hochscrollen) ==")
from chimera.ablage import Ablage  # noqa: E402
d2 = tempfile.mkdtemp()
abl = Ablage(Path(d2) / "sitzungen-ablage")
sid = ablage_id = abl.aktiv()
for i in range(120):
    abl.anhaengen({"art": "nachricht", "rolle": "user", "inhalt": f"zeile-{i:03d}"})
pfad2 = os.path.join(d2, "s2.sock")
sess2 = Session(Agent(), ablage=abl)
srv2 = sitzung_socket.SitzungsServer(sess2, pfad=pfad2).start()
time.sleep(0.1)
k = Client(pfad2)

def hole(**kw):
    k.senden(op="lesen", sitzung=sid, **kw)
    return k.lesen()

r = hole(max=50)
check("letzte Seite vollständig", len(r["eintraege"]), 50)
check("Gesamtzahl wird genannt", r["gesamt"], 120)
check("letzter Eintrag ist der neueste", r["eintraege"][-1]["inhalt"], "zeile-119")
check("erste Seite beginnt bei 70", r["eintraege"][0]["inhalt"], "zeile-070")

r2 = hole(max=50, vor=50)
check("zweite Seite endet vor der letzten", r2["eintraege"][-1]["inhalt"], "zeile-069")
check("zweite Seite beginnt bei 20", r2["eintraege"][0]["inhalt"], "zeile-020")

r3 = hole(max=50, vor=100)
check("dritte Seite reicht bis zum Anfang", r3["eintraege"][0]["inhalt"], "zeile-000")
check("dritte Seite hat nur noch 20", len(r3["eintraege"]), 20)

r4 = hole(max=50, vor=500)
check("über den Anfang hinaus ist leer, nicht kaputt", r4["eintraege"], [])

r5 = hole(max=0)
check("max=0 wird auf 1 gehoben, nicht als leerer Slice gedeutet",
      len(r5["eintraege"]), 1)
r6 = hole(max="quatsch")
check("unsinniges max fällt auf 200 zurück", len(r6["eintraege"]), 120)

print("== Fehlerfälle ==")
x = Client(pfad)
x.senden(op="quatsch"); check("unbekannte op", x.lesen()["ok"], False)
x.f.write(b"kein json\n"); check("kaputte Zeile", x.lesen()["ok"], False)
x.senden(op="frage", tuer="", text="x"); check("Frage ohne Tür", x.lesen()["ok"], False)
x.senden(op="ping"); check("danach weiter bedienbar", x.lesen()["ok"], True)

print("== Gesicht über den Socket (Update-Anzeige) ==")
gesehen = []
sess.gesicht_setzen = lambda name: (gesehen.append(name), True)[1]
y = Client(pfad)
y.senden(op="gesicht", name="UPDATE")
_a = y.lesen()
check("gesicht: bestaetigt", _a.get("ok"), True)
check("gesicht: Name kommt an", gesehen, ["UPDATE"])
y.senden(op="gesicht", name="")
check("gesicht: ohne Name ein Fehler", y.lesen().get("ok"), False)
sess.gesicht_setzen = None
y.senden(op="gesicht", name="UPDATE")
check("gesicht: ohne Bruecke ein Fehler", y.lesen().get("ok"), False)
sess.gesicht_setzen = lambda name: (None, False)[1]
y.senden(op="gesicht", name="GIBTSNICHT")
check("gesicht: unbekannter Name ein Fehler", y.lesen().get("ok"), False)
y.s.close()

print("== LED über den Socket (Abschluss des Installers) ==")
# Vorgabe smilez (3.11.): Auch ein Lauf, der nichts zu tun hatte, meldet
# seinen Ausgang -- der Dienst haelt die Pins, also setzt er die LED.
gemeldet = []
sess.led_melden = lambda zustand, sekunden=3.0: (gemeldet.append((zustand, sekunden)), True)[1]
z = Client(pfad)
z.senden(op="led", zustand="nichts")
_a = z.lesen()
check("led: bestaetigt", _a.get("ok"), True)
check("led: Ausgang kommt an", gemeldet, [("nichts", 3.0)])
z.senden(op="led", zustand="ok", sekunden=5)
check("led: Sekunden kommen an", z.lesen().get("ok"), True)
check("led: eigene Dauer", gemeldet[-1], ("ok", 5.0))
sess.led_melden = None
z.senden(op="led", zustand="ok")
check("led: ohne Bruecke ein Fehler", z.lesen().get("ok"), False)
sess.led_melden = lambda zustand, sekunden=3.0: False
z.senden(op="led", zustand="gibtsnicht")
check("led: unbekannter Ausgang ein Fehler", z.lesen().get("ok"), False)
z.s.close()

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
